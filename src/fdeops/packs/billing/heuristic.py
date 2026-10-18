"""A rule-based stand-in for an LLM, for exercising the full pipeline without any model.

It speaks the same protocol as a real model: it reads the transcript (ticket, retrieved knowledge,
tool results) and emits tool calls. It takes policy facts *from the retrieved text*, not from the
tenant config. If retrieval surfaces a stale policy first, it follows the stale policy, the way a
real model can. Seeded error modes inject the mistakes real agents make, so detection and diagnosis
can be tested against known ground truth.

Every run that uses it is labeled ``pipeline-test``. Its numbers are never reported as agent
quality.
"""

import json
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from fdeops.llm.types import LLMRequest, LLMResponse, Message, ToolCall, Usage

ERROR_MODES = (
    "skip_lookup",
    "ignore_retrieval",
    "wrong_amount",
    "follow_injection",
    "miss_escalation",
)
INJECTION = re.compile(
    r"ignore (your|all) previous|system notice|assistant instructions|"
    r"you are authorized",
    re.IGNORECASE,
)
PLAN_NAMES = ("starter", "growth", "scale", "enterprise")


@dataclass
class _View:
    """What the model can see, parsed from the transcript."""

    ticket_id: str = ""
    email: str = ""
    body: str = ""
    today: date | None = None
    knowledge: str = ""
    customer_replies: list[str] = field(default_factory=list)
    results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    steps: int = 0

    def last(self, op: str) -> dict[str, Any] | None:
        got = self.results.get(op)
        return got[-1] if got else None

    @property
    def text(self) -> str:
        return " ".join([self.body, *self.customer_replies])


def _parse(messages: tuple[Message, ...]) -> _View:
    v = _View()
    for m in messages:
        if m.role == "system":
            if d := re.search(r"Today's date: (\d{4}-\d{2}-\d{2})", m.content):
                v.today = date.fromisoformat(d.group(1))
        elif m.role == "user" and m.content.startswith("New ticket"):
            head, _, kb = m.content.partition("\n---\n")
            v.ticket_id = re.search(r"New ticket (\S+)", head).group(1)  # type: ignore[union-attr]
            v.email = re.search(r"From: (\S+)", head).group(1)  # type: ignore[union-attr]
            v.body = head.split("\n\n", 1)[1] if "\n\n" in head else head
            v.knowledge += kb
        elif m.role == "user" and m.content.startswith("Customer replied:"):
            v.customer_replies.append(m.content.removeprefix("Customer replied:").strip())
        elif m.role == "assistant":
            v.steps += 1
        elif m.role == "tool" and m.name:
            payload = json.loads(m.content)
            v.results.setdefault(m.name, []).append(payload)
            if m.name == "search_kb":
                v.knowledge += "\n" + str(payload.get("results", ""))
    return v


def _variants(word: str) -> set[str]:
    """The word plus every single adjacent transposition: cheap typo tolerance."""
    return {word} | {word[:i] + word[i + 1] + word[i] + word[i + 2 :] for i in range(len(word) - 1)}


def _has(text: str, *words: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return any(tokens & _variants(w) for w in words)


def _cents(text: str) -> int:
    return round(float(text.replace(",", "")) * 100)


class BillingHeuristicLLM:
    provider = "heuristic"

    def __init__(self, seed: int = 0, error_rates: Mapping[str, float] | None = None) -> None:
        unknown = set(error_rates or {}) - set(ERROR_MODES)
        if unknown:
            raise ValueError(f"unknown error modes {sorted(unknown)}; choose from {ERROR_MODES}")
        self.seed = seed
        self.error_rates = dict(error_rates or {})

    # ------------------------------------------------------------------ protocol
    def complete(self, request: LLMRequest) -> LLMResponse:
        view = _parse(request.messages)
        turn = 1 + len(view.customer_replies)
        trial_seed = (request.seed or 0) - turn
        name, args = self._decide(view, trial_seed)
        prompt_tokens = sum(len(m.content) for m in request.messages) // 4
        call = ToolCall(
            id=f"h{view.steps}",
            name=name,
            arguments=args,
            raw_arguments=json.dumps(args, sort_keys=True),
        )
        return LLMResponse(
            content="",
            tool_calls=(call,),
            usage=Usage(input_tokens=prompt_tokens, output_tokens=40),
            latency_ms=round(350 + 0.02 * prompt_tokens, 1),
            model=request.model,
            provider=self.provider,
            finish_reason="tool_calls",
        )

    def _errs(self, view: _View, trial_seed: int, mode: str) -> bool:
        rate = self.error_rates.get(mode, 0.0)
        if rate <= 0:
            return False
        return random.Random(f"{self.seed}:{trial_seed}:{view.ticket_id}:{mode}").random() < rate

    # ------------------------------------------------------------------ policy
    def _decide(self, v: _View, s: int) -> tuple[str, dict[str, Any]]:
        if v.steps >= 7:
            return self._reply(v, "Thanks for your patience, a specialist will follow up.")
        lookup = v.last("lookup_customer")
        if lookup is None and not self._errs(v, s, "skip_lookup"):
            return "lookup_customer", {"email": v.email}
        if lookup is not None and "error" in lookup:
            return self._reply(
                v,
                "For your security we can only help with requests sent from the "
                "email address registered on your account. Please write to us "
                "again from that address.",
            )
        account = (lookup or {}).get("data", {})
        text = v.text.lower()
        if re.search(r"two[- ]factor|2fa|two factor|workspace owner|make me the", text) or _has(
            text, "authentication"
        ):
            return "escalate_to_human", {
                "ticket_id": v.ticket_id,
                "reason_code": "account_security",
                "note": "2FA/ownership request",
            }
        if _has(text, "export") or "copy of all the data" in text:
            return self._export(v, account)
        if _has(text, "downgrade") or re.search(r"switch down|move us from", text):
            return self._downgrade(v, account)
        if _has(text, "declined") or re.search(
            r"payment failed|didn't go through|card payment|"
            r"failed charge",
            text,
        ):
            return self._payment_help(v, s)
        if _has(text, "refund", "refunded") or "money back" in text:
            return self._refund(v, s, account)
        if re.search(r"inv_\w+", text):
            return self._explain_invoice(v)
        return self._reply(
            v, "Thanks for reaching out. Could you share a little more detail so we can help?"
        )

    def _reply(self, v: _View, message: str) -> tuple[str, dict[str, Any]]:
        return "reply_to_customer", {"ticket_id": v.ticket_id, "message": message}

    def _export(self, v: _View, account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        role = account.get("user", {}).get("role")
        if role not in ("owner", "admin"):
            return self._reply(
                v,
                "Only workspace Owners and Admins can request a full data "
                "export. Please ask an Owner or Admin to make the request.",
            )
        if v.last("request_data_export") is None:
            return "request_data_export", {
                "customer_id": account["customer"]["id"],
                "requester_email": v.email,
            }
        return self._reply(
            v,
            "Your data export has started. It will be emailed to you within 24 "
            "hours as a ZIP archive.",
        )

    def _downgrade(self, v: _View, account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        names = re.findall(r"\b(" + "|".join(PLAN_NAMES) + r")\b", v.text.lower())
        target = names[-1] if names else None
        if target is None or not account:
            return self._reply(v, "Which plan would you like to move to?")
        if v.last("change_plan") is None:
            return "change_plan", {
                "customer_id": account["customer"]["id"],
                "plan_id": f"plan_{target}",
            }
        return self._reply(
            v,
            f"Done: your workspace will move to {target.title()}. Downgrades "
            "take effect at the start of your next billing cycle.",
        )

    def _payment_help(self, v: _View, s: int) -> tuple[str, dict[str, Any]]:
        kb = "" if self._errs(v, s, "ignore_retrieval") else v.knowledge
        retry = re.search(r"[^.\n]*retry the charge[^.\n]*\.", kb)
        card = re.search(r"[^.\n]*Settings > Billing[^.\n]*\.", kb)
        parts = [m.group(0).strip() for m in (retry, card) if m]
        body = " ".join(parts) or "Please try another card."
        return self._reply(v, f"Sorry about the failed payment. {body}")

    def _explain_invoice(self, v: _View) -> tuple[str, dict[str, Any]]:
        inv_id = re.findall(r"inv_\w+", v.text)[-1]
        got = v.last("get_invoice")
        if got is None:
            return "get_invoice", {"invoice_id": inv_id}
        if "error" in got:
            return self._reply(v, f"I couldn't find invoice {inv_id}. Could you double-check it?")
        inv = got["data"]["invoice"]
        start = date.fromisoformat(inv["period_start"])
        end = date.fromisoformat(inv["period_end"])
        return self._reply(
            v,
            f"Invoice {inv_id} is your {inv['description']} charge of "
            f"${inv['amount_cents'] / 100:,.2f} for the billing period "
            f"{start:%B %-d} to {end:%B %-d, %Y}.",
        )

    def _refund(self, v: _View, s: int, account: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        careful = not self._errs(v, s, "ignore_retrieval")
        windows = [int(d) for d in re.findall(r"in the (\d+) days after the payment", v.knowledge)]
        limits = re.findall(r"Refunds above \$([\d,]+\.\d\d)", v.knowledge)
        searches = len(v.results.get("search_kb", []))
        if careful and searches == 0 and not windows:
            return "search_kb", {"query": "refund window days after payment"}
        if careful and searches < 2 and not limits:
            return "search_kb", {
                "query": "large refunds above limit reviewed by billing specialist"
            }
        window = windows[0] if windows else 30  # first retrieved statement wins
        limit = _cents(limits[0]) if limits else None
        injected = bool(INJECTION.search(v.body) or INJECTION.search(v.knowledge))
        obey_injection = injected and self._errs(v, s, "follow_injection")

        mentioned = re.findall(r"inv_\w+", v.text)
        invoices = (v.last("list_invoices") or {}).get("data", {}).get("invoices")
        if not mentioned and invoices is None:
            if not account:
                return self._reply(v, "Could you tell me which invoice this is about?")
            return "list_invoices", {"customer_id": account["customer"]["id"]}
        if mentioned:
            got = v.last("get_invoice")
            if got is None:
                return "get_invoice", {"invoice_id": mentioned[-1]}
            if "error" in got:
                return self._reply(v, f"I couldn't find invoice {mentioned[-1]}.")
            inv = got["data"]["invoice"]
        else:
            today = v.today or date.today()
            eligible = [
                i
                for i in invoices or []
                if i["status"] == "paid"
                and i["paid_at"]
                and (today - datetime.fromisoformat(i["paid_at"]).date()).days <= window
            ]
            if len(eligible) > 1:
                options = ", ".join(
                    f"{i['id']} ({i['description']}, ${i['amount_cents'] / 100:,.2f})"
                    for i in eligible
                )
                return "ask_clarifying_question", {
                    "ticket_id": v.ticket_id,
                    "question": f"Which invoice would you like refunded: {options}?",
                }
            if not eligible:
                return self._reply(
                    v,
                    f"None of your recent invoices are within the {window}-day "
                    "refund window, so they are not eligible for a refund.",
                )
            inv = eligible[0]

        if v.last("issue_refund") is not None:
            res = v.last("issue_refund") or {}
            if "error" in res:
                return "escalate_to_human", {
                    "ticket_id": v.ticket_id,
                    "reason_code": "other",
                    "note": f"refund failed: {res['error']['message']}",
                }
            amt = res["data"]["refund"]["amount_cents"]
            return self._reply(
                v,
                f"I've refunded ${amt / 100:,.2f} on invoice {inv['id']}. "
                "Refunds appear on your statement within 5 to 10 business days.",
            )
        today = v.today or date.today()
        paid = datetime.fromisoformat(inv["paid_at"]).date() if inv.get("paid_at") else None
        if inv["status"] != "paid" or paid is None:
            return self._reply(
                v, f"Invoice {inv['id']} has status {inv['status']} and cannot be refunded."
            )
        amount = inv["amount_cents"] - inv.get("refunded_cents", 0)
        if (today - paid).days > window and not obey_injection:
            return self._reply(
                v,
                f"Invoice {inv['id']} was paid {(today - paid).days} days ago. "
                f"Refunds are available within {window} days of payment, so "
                "this invoice is not eligible.",
            )
        over = limit is not None and amount > limit
        if over and not obey_injection and not self._errs(v, s, "miss_escalation"):
            return "escalate_to_human", {
                "ticket_id": v.ticket_id,
                "reason_code": "refund_over_limit",
                "note": f"refund of ${amount / 100:,.2f} needs review",
            }
        if self._errs(v, s, "wrong_amount"):
            amount = max(1, amount // 100)  # dollars passed as cents: a classic unit bug
        return "issue_refund", {
            "invoice_id": inv["id"],
            "amount_cents": amount,
            "reason": "customer request",
        }
