import re

from fdeops.world.cases import Case


class BillingUserSimulator:
    """Deterministic customer: answers only what it is asked, only from the case's hidden facts."""

    def respond(self, case: Case, agent_message: str) -> str | None:
        text = agent_message.lower()
        asks = "?" in text or re.search(r"\b(could|can|please|which|confirm|let me know)\b", text)
        if not asks:
            return None
        if "invoice" in text and "invoice_id" in case.hidden_facts:
            return f"It's invoice {case.hidden_facts['invoice_id']}."
        if "plan" in text and "plan_id" in case.hidden_facts:
            return f"The plan id is {case.hidden_facts['plan_id']}."
        return None
