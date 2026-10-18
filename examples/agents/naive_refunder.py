"""An example external agent for the Ledgerloop tenant.

Run it with:

    uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic.yaml \
        --dataset data/datasets/ledgerloop/support-core@v1 --split dev \
        --external examples/agents/naive_refunder.py:agent

The agent refunds the invoice that the ticket names. It does not read the policy. The platform
evaluates it with the same connector stack and the same rules as the reference agent, thus the
report shows its policy violations.
"""

import re

from fdeops.agent.episode import ToolBox


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
    ids = re.findall(r"inv_\w+", box.ticket.body + " " + " ".join(box.customer_replies))
    if not ids:
        box.call("ask_clarifying_question", ticket_id=tid, question="Which invoice is it?")
        return
    got = box.call("get_invoice", invoice_id=ids[-1])
    if "error" in got:
        box.call("escalate_to_human", ticket_id=tid, reason_code="other", note="no invoice")
        return
    inv = got["data"]["invoice"]
    box.call(
        "issue_refund",
        invoice_id=inv["id"],
        amount_cents=inv["amount_cents"],
        reason="customer request",
    )
    box.call(
        "reply_to_customer",
        ticket_id=tid,
        message=f"We refunded ${inv['amount_cents'] / 100:,.2f}.",
    )
