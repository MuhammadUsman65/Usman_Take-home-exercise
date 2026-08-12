from typing import Optional

REFUSAL_MESSAGE = (
    "I can't share restricted information requested by you here for your security. If you need to verify or update "
    "this information, I'll connect you with a human agent who can "
    "confirm your identity properly."
)

# Keyword heuristic for "customer is asking for a restricted field directly."
RESTRICTED_REQUEST_KEYWORDS = [
    "cnic",
    "card number",
    "full card",
    "card pan",
    "pan number",
    "iban",
    "account number",
    "cvv",
    "full number",
]


def is_restricted_request(question: str) -> bool:
    """True if the question is asking for a restricted field directly."""
    q = question.lower()
    return any(keyword in q for keyword in RESTRICTED_REQUEST_KEYWORDS)


def get_safe_fields(customer_id: str, customers: dict) -> Optional[dict]:
    """Returns ONLY the 'safe' dict for a customer. Never 'restricted'.
    Returns None if the customer_id doesn't exist."""

    for customer in customers.get("customers", []):
        if customer.get("id") == customer_id:
            return customer.get("safe")
    return None


def customer_exists(customer_id: str, customers: dict) -> bool:
    return any(c.get("id") == customer_id for c in customers.get("customers", []))


def should_escalate(intent: str) -> tuple[bool, str]:
    """Decides whether a human needs to pick this up, and why."""
    if intent == "unclear":
        return True, "Account data shows something knowledge.md doesn't cover — needs human judgment."
    return False, ""