import re

from fdeops.world.cases import Case


class LogisticsUserSimulator:
    """Answers only what the agent asks, from the hidden facts of the case."""

    def respond(self, case: Case, agent_message: str) -> str | None:
        text = agent_message.lower()
        if "?" not in text and not re.search(r"\b(please|which|confirm|let me know)\b", text):
            return None
        if (
            re.search(r"tracking|which (shipment|parcel)", text)
            and "tracking_number" in case.hidden_facts
        ):
            return f"It is tracking number {case.hidden_facts['tracking_number']}."
        if "address" in text and "new_address" in case.hidden_facts:
            return f"The new address is {case.hidden_facts['new_address']}."
        return None
