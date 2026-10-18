"""A simple baseline without an LLM: a FAQ responder.

It sends the best help-center section to the customer and does no other task. The LLM agent must
be better than this baseline, or the LLM is not worth its cost. The platform runs it as an external
agent, thus its numbers are measured with the same rules as the agent.
"""

from fdeops.agent.episode import ToolBox


def faq_agent(box: ToolBox) -> None:
    t = box.ticket
    chunks = [c.model_dump(mode="json") for c in box.knowledge] or box.search_kb(
        f"{t.subject} {t.body}"
    )
    if chunks:
        best = chunks[0]
        message = f"This article from our help center can help: {best['title']}. {best['text']}"
    else:
        message = "Thank you for your message. A member of our team will reply soon."
    box.call("reply_to_customer", ticket_id=t.ticket_id, message=message)
