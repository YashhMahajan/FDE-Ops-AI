"""An example external agent that reads the policy before it moves money.

Copy this file to start your own agent. Run it with:

    uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic.yaml \
        --dataset data/datasets/ledgerloop/support-core@v1 --split dev \
        --external examples/agents/careful_refunder.py:agent

The agent does these steps:

1. It finds the customer from the email address of the ticket.
2. It reads the refund window from the current knowledge-base article. It ignores superseded text.
3. It refunds only an invoice that is inside the window and below the auto-refund limit.
4. It escalates a large refund, and it refuses a refund that is outside the window.

On the 51 dev cases of Ledgerloop, this agent has 78.4% success (naive agent: 21.6%) and 0 critical
violations (naive agent: 33 trials). It does refund tickets only, so it scores 0% on the other
scenarios. The result label is measured-in-simulation.
"""

import re
from datetime import datetime

from fdeops.agent.episode import ToolBox

DEFAULT_WINDOW_DAYS = 14
AUTO_REFUND_LIMIT_CENTS = 20_000


def refund_window_days(box: ToolBox) -> int:
    """Read the window in days from the newest refund article. Use a default if it is missing."""
    for chunk in box.search_kb("refund window days after the payment date"):
        if chunk["stale"] or "refund" not in chunk["section_key"]:
            continue
        found = re.search(r"in the (\d+) days", chunk["text"])
        if found:
            return int(found.group(1))
    return DEFAULT_WINDOW_DAYS


def agent(box: ToolBox) -> None:
    tid = box.ticket.ticket_id
    found = box.call("lookup_customer", email=box.ticket.requester_email)
    if "error" in found:
        box.call(
            "reply_to_customer",
            ticket_id=tid,
            message="Please write to us from the email address of your account.",
        )
        return
    text = box.ticket.body + " " + " ".join(box.customer_replies)
    ids = re.findall(r"inv_\w+", text)
    if "refund" not in text.lower() or not ids:
        box.call("ask_clarifying_question", ticket_id=tid, question="Which invoice is it?")
        return
    got = box.call("get_invoice", invoice_id=ids[-1])
    if "error" in got:
        box.call("escalate_to_human", ticket_id=tid, reason_code="other", note="invoice not found")
        return
    inv = got["data"]["invoice"]
    paid_at = inv.get("paid_at")
    days = (box.today - datetime.fromisoformat(paid_at).date()).days if paid_at else None
    if days is None or days > refund_window_days(box):
        box.call(
            "reply_to_customer",
            ticket_id=tid,
            message="This invoice is outside the refund window, so we cannot refund it. "
            "You can cancel your plan to stop future charges.",
        )
        return
    if inv["amount_cents"] > AUTO_REFUND_LIMIT_CENTS:
        box.call(
            "escalate_to_human",
            ticket_id=tid,
            reason_code="refund_over_limit",
            note="The refund is above the auto-refund limit.",
        )
        return
    box.call(
        "issue_refund",
        invoice_id=inv["id"],
        amount_cents=inv["amount_cents"],
        reason="customer request inside the refund window",
    )
    box.call(
        "reply_to_customer",
        ticket_id=tid,
        message=f"We refunded ${inv['amount_cents'] / 100:,.2f}.",
    )
