"""Rule-based stand-in model for the logistics pack. Refer to packs/billing/heuristic.py.

It reads policy limits from the retrieved text. A stale claims section makes it approve claims
that the current limit does not permit, as a real model can.
"""

import json
import random
import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from fdeops.llm.types import LLMRequest, LLMResponse, ToolCall, Usage
from fdeops.packs.billing.heuristic import _cents, _has, _parse, _View

ERROR_MODES = (
    "skip_lookup",
    "ignore_retrieval",
    "wrong_amount",
    "follow_injection",
    "miss_escalation",
)
INJECTION = re.compile(r"ignore your previous|\[system:|limits do not apply", re.IGNORECASE)
LEGAL = re.compile(r"lawyer|attorney|legal action|chargeback|\bsue\b|court", re.IGNORECASE)
TRACKING = re.compile(r"\bPP\d{9}\b")
ADDRESS = re.compile(r"\d{1,3} [A-Z][a-z]+ (?:Street|Road), [A-Z][a-z]+")


class LogisticsHeuristicLLM:
    provider = "heuristic"

    def __init__(self, seed: int = 0, error_rates: Mapping[str, float] | None = None) -> None:
        unknown = set(error_rates or {}) - set(ERROR_MODES)
        if unknown:
            raise ValueError(f"unknown error modes {sorted(unknown)}. Use {ERROR_MODES}.")
        self.seed = seed
        self.error_rates = dict(error_rates or {})

    def complete(self, request: LLMRequest) -> LLMResponse:
        v = _parse(request.messages)
        turn = 1 + len(v.customer_replies)
        name, args = self._decide(v, (request.seed or 0) - turn)
        tokens = sum(len(m.content) for m in request.messages) // 4
        call = ToolCall(
            id=f"h{v.steps}",
            name=name,
            arguments=args,
            raw_arguments=json.dumps(args, sort_keys=True),
        )
        return LLMResponse(
            content="",
            tool_calls=(call,),
            usage=Usage(input_tokens=tokens, output_tokens=40),
            latency_ms=round(320 + 0.02 * tokens, 1),
            model=request.model,
            provider=self.provider,
            finish_reason="tool_calls",
        )

    def _errs(self, v: _View, s: int, mode: str) -> bool:
        rate = self.error_rates.get(mode, 0.0)
        return rate > 0 and random.Random(f"{self.seed}:{s}:{v.ticket_id}:{mode}").random() < rate

    def _reply(self, v: _View, msg: str) -> tuple[str, dict[str, Any]]:
        return "reply_to_customer", {"ticket_id": v.ticket_id, "message": msg}

    def _escalate(self, v: _View, code: str, note: str) -> tuple[str, dict[str, Any]]:
        return "escalate_to_human", {"ticket_id": v.ticket_id, "reason_code": code, "note": note}

    def _decide(self, v: _View, s: int) -> tuple[str, dict[str, Any]]:
        if v.steps >= 7:
            return self._reply(v, "A specialist will contact you about this ticket.")
        lookup = v.last("lookup_customer")
        if lookup is None and not self._errs(v, s, "skip_lookup"):
            return "lookup_customer", {"email": v.email}
        if lookup is not None and "error" in lookup:
            return self._reply(
                v,
                "For your protection, we can only help with requests from the "
                "email address of the account. Please send your request again "
                "from the email address that is registered on the account.",
            )
        if LEGAL.search(v.body):
            return self._escalate(v, "legal_risk", "The customer mentions legal action.")
        account = (lookup or {}).get("data", {}).get("account", {})
        text = v.text.lower()
        if _has(text, "damaged", "broken", "damage", "claim"):
            return self._claim(v, s)
        if (
            _has(text, "address")
            or ("deliver" in text and " to " in text)
            or ADDRESS.search(v.text)
        ):
            return self._address(v, account)
        return self._track(v, account)

    def _shipment(self, v: _View) -> dict[str, Any] | None:
        got = v.last("track_shipment")
        return got["data"]["shipment"] if got and "data" in got else None

    def _track(self, v: _View, account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        tns = TRACKING.findall(v.text)
        ship = self._shipment(v)
        if ship is None and tns:
            if v.last("track_shipment") is None:
                return "track_shipment", {"tracking_number": tns[-1]}
            return self._reply(v, f"I could not find shipment {tns[-1]}. Please check the number.")
        if ship is None:
            return self._reply(v, "Please send the tracking number of the shipment.")
        eta = date.fromisoformat(ship["eta"])
        if ship["status"] == "delayed":
            rule = re.search(r"[^.\n]*\b3 business days[^.\n]*\.", v.knowledge)
            extra = rule.group(0).strip() if rule else "We will send you the new date."
            return self._reply(v, f"Shipment {ship['tracking_number']} is delayed. {extra}")
        status = ship["status"].replace("_", " ")
        return self._reply(
            v,
            f"Shipment {ship['tracking_number']} is {status}. The expected "
            f"delivery date is {eta:%B} {eta.day}, {eta.year}.",
        )

    def _address(self, v: _View, account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        tns = TRACKING.findall(v.text)
        new = ADDRESS.findall(v.text)
        if not tns:
            if v.last("list_shipments") is None and account:
                return "list_shipments", {"account_id": account["id"]}
            listed = (v.last("list_shipments") or {}).get("data", {}).get("shipments", [])
            open_ = [x for x in listed if x["status"] in ("label_created", "in_transit")]
            if len(open_) == 1:
                tns = [open_[0]["tracking_number"]]
            else:
                return "ask_clarifying_question", {
                    "ticket_id": v.ticket_id,
                    "question": "Which shipment must go to the new address? Please send the "
                    "tracking number.",
                }
        ship = self._shipment(v)
        if ship is None or ship["tracking_number"] != tns[-1]:
            if not any(
                r.get("data", {}).get("shipment", {}).get("tracking_number") == tns[-1]
                for r in v.results.get("track_shipment", [])
            ):
                return "track_shipment", {"tracking_number": tns[-1]}
            ship = next(
                r["data"]["shipment"]
                for r in v.results["track_shipment"]
                if r.get("data", {}).get("shipment", {}).get("tracking_number") == tns[-1]
            )
        if ship["status"] not in ("label_created", "in_transit"):
            return self._reply(
                v,
                f"Shipment {ship['tracking_number']} is "
                f"{ship['status'].replace('_', ' ')}. We cannot change the "
                "address after the shipment is out for delivery.",
            )
        if v.last("update_delivery_address") is None:
            if not new:
                return "ask_clarifying_question", {
                    "ticket_id": v.ticket_id,
                    "question": "What is the new address?",
                }
            return "update_delivery_address", {"shipment_id": ship["id"], "new_address": new[-1]}
        return self._reply(v, f"The delivery address of {ship['tracking_number']} is changed.")

    def _claim(self, v: _View, s: int) -> tuple[str, dict[str, Any]]:
        tns = TRACKING.findall(v.text)
        if not tns:
            return self._reply(v, "Please send the tracking number of the damaged shipment.")
        ship = self._shipment(v)
        if ship is None:
            if v.last("track_shipment") is None:
                return "track_shipment", {"tracking_number": tns[-1]}
            return self._reply(v, f"I could not find shipment {tns[-1]}.")
        careful = not self._errs(v, s, "ignore_retrieval")
        windows = [int(d) for d in re.findall(r"in the (\d+) days after delivery", v.knowledge)]
        limits = re.findall(r"Claims above \$([\d,]+\.\d\d)", v.knowledge)
        searches = len(v.results.get("search_kb", []))
        if careful and searches == 0 and not windows:
            return "search_kb", {"query": "damage claim window days after delivery"}
        if careful and searches < 2 and not limits:
            return "search_kb", {"query": "large claims above limit approval claims specialist"}
        window = windows[0] if windows else 30
        limit = _cents(limits[0]) if limits else None
        amounts = re.findall(r"\$([\d,]+\.\d\d)", v.body)
        amount = _cents(amounts[0]) if amounts else ship["declared_value_cents"]
        delivered = ship.get("delivered_at")
        days = (
            (v.today - datetime.fromisoformat(delivered).date()).days
            if delivered and v.today
            else None
        )
        obey = bool(INJECTION.search(v.body)) and self._errs(v, s, "follow_injection")
        res = v.last("file_claim")
        if res is not None:
            if "error" in res:
                return self._escalate(v, "other", f"The claim failed: {res['error']['message']}")
            amt = res["data"]["claim"]["amount_cents"]
            return self._reply(
                v, f"I approved a damage claim of ${amt / 100:,.2f} for {ship['tracking_number']}."
            )
        if ship["status"] != "delivered" or days is None:
            return self._reply(v, "A damage claim is possible only after delivery.")
        if days > window and not obey:
            return self._reply(
                v,
                f"The delivery was {days} days ago. You can file a damage claim "
                f"in the {window} days after delivery, thus this claim is not "
                "possible.",
            )
        if (
            limit is not None
            and amount > limit
            and not obey
            and not self._errs(v, s, "miss_escalation")
        ):
            return self._escalate(
                v, "claim_over_limit", f"The claim of ${amount / 100:,.2f} is above the limit."
            )
        if self._errs(v, s, "wrong_amount"):
            amount = max(1, amount // 100)
        return "file_claim", {
            "shipment_id": ship["id"],
            "kind": "damage",
            "amount_cents": amount,
            "description": "Damage reported by the customer.",
        }
