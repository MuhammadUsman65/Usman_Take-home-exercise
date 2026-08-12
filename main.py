import json
from pathlib import Path

from chunker import chunk_markdown, load_markdown, KNOWLEDGE_FILE
from llm import classify, generate, GenerationError
from rules import get_safe_fields, should_escalate, is_restricted_request, customer_exists, REFUSAL_MESSAGE

DATA_DIR = Path("data/")
CUSTOMERS_FILE = DATA_DIR / "customers.json"
QUESTIONS_FILE = DATA_DIR / "questions.txt"

OUT_OF_SCOPE_MESSAGE = (
    "That's not something I have approved information on here — I'd suggest "
    "checking the app or our website for the latest on that."
)

GENERATION_FAILURE_MESSAGE = (
    "Sorry, I'm having trouble putting together a reply right now. "
    "I'm connecting you with a human agent so this doesn't get dropped."
)

UNKNOWN_CUSTOMER_MESSAGE = (
    "Sorry I am unable to locate your account - I'm connecting you with one of our "
    "agents to sort this out."
)

def build_router_options(chunks) -> list[dict]:
    # Only the '##' sections are approved, addressable content. The
    # preamble above the first '##' (H1 title and intro blockquote) comes
    # back from the splitter as its own chunk with no "section" key.
    # Without this filter it shows up as a junk numbered option in the
    # router prompt.
    sectioned = [c for c in chunks if "section" in c.metadata]
    return [
        {"id": i, "title": c.metadata.get("section", "Untitled"), "content": c.page_content.strip()}
        for i, c in enumerate(sectioned)
    ]


def load_customers() -> dict:
    return json.loads(CUSTOMERS_FILE.read_text(encoding="utf-8"))


def parse_questions() -> list[tuple[str, str]]:
    pairs = []
    for line in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        customer_id, _, question = line.partition("|")
        pairs.append((customer_id.strip(), question.strip()))
    return pairs


def answer(customer_id: str, question: str, options: list[dict], customers: dict) -> dict:

    if not customer_exists(customer_id, customers):
        return {                
            "reply": UNKNOWN_CUSTOMER_MESSAGE,
            "intent": "unknown_customer",
            "escalate": True,
            "escalation_reason": "customer_id not found in account data — possible bad session/lookup, needs human verification.",
            }
    

    # Restricted-field requests are checked before anything else, with a
    # plain keyword rule instead of the LLM classifier.
    if is_restricted_request(question):
        return {
            "reply": REFUSAL_MESSAGE,
            "intent": "restricted_request",
            "escalate": True,
            "escalation_reason": "Customer asked for a restricted field directly — needs identity verification by a human agent.",
        }

    routed = classify(question, options)
    intent = routed.get("intent") if isinstance(routed, dict) else None

    try:
        if intent == "knowledge_section":
            section_id = routed.get("section_id")
            if section_id is not None and 0 <= section_id < len(options):
                section = options[section_id]
                reply = generate(question, intent, content=section["content"])
                return {"reply": reply, "intent": intent, "escalate": False}
            # Defense in depth: classify() validates this, but an unusable
            # section_id is a system error, not an out_of_scope question.
            return {
                "reply": GENERATION_FAILURE_MESSAGE,
                "intent": "system_error",
                "escalate": True,
                "escalation_reason": "Classifier returned an invalid knowledge section.",
            }

        if intent == "account_data":
            safe_data = get_safe_fields(customer_id, customers)
            reply = generate(question, intent, safe_data=safe_data)
            return {"reply": reply, "intent": intent, "escalate": False}

        if intent == "unclear":
            safe_data = get_safe_fields(customer_id, customers)
            reply = generate(question, intent, safe_data=safe_data)
            escalate, reason = should_escalate("unclear")
            return {"reply": reply, "intent": intent, "escalate": escalate, "escalation_reason": reason}

    except GenerationError:
        return {
            "reply": GENERATION_FAILURE_MESSAGE,
            "intent": intent,
            "escalate": True,
            "escalation_reason": "Reply generation failed (system/network error).",
        }

    # out_of_scope — decline, no generation call, no escalation
    return {"reply": OUT_OF_SCOPE_MESSAGE, "intent": "out_of_scope", "escalate": False}


def main():
    markdown_text = load_markdown(KNOWLEDGE_FILE)
    chunks = chunk_markdown(markdown_text)
    options = build_router_options(chunks)
    customers = load_customers()

    for customer_id, question in parse_questions():
        result = answer(customer_id, question, options, customers)
        print(f"[{customer_id}] {question}")
        print(f"  -> intent: {result['intent']}, escalate: {result['escalate']}")
        print(f"  -> reply: {result['reply']}\n")


if __name__ == "__main__":
    main()