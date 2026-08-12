import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import main
from chunker import KNOWLEDGE_FILE, chunk_markdown, load_markdown


# ---------------------------------------------------------------------------
# LIVE integration test data
# These are the questions supplied with the take-home exercise, plus the
# expected routing/escalation decisions chosen for this implementation.
# ---------------------------------------------------------------------------

QUESTIONS = [
    (
        "cust_001",
        "how do I freeze my card?",
        "knowledge_section",
        False,
    ),
    (
        "cust_001",
        "what's my balance?",
        "account_data",
        False,
    ),
    (
        "cust_002",
        "I was charged twice for Netflix, what's going on?",
        "unclear",
        True,
    ),
    (
        "cust_002",
        "can I use tap to pay with my card?",
        "knowledge_section",
        False,
    ),
    (
        "cust_001",
        "what's the interest rate on the savings account?",
        "out_of_scope",
        False,
    ),
    (
        "cust_001",
        "do you offer crypto trading?",
        "out_of_scope",
        False,
    ),
    (
        "cust_001",
        "can you tell me my full card number and CNIC?",
        "restricted_request",
        True,
    ),
    (
        "cust_003",
        "why can't I do anything on my account?",
        "unclear",
        True,
    ),
    (
        "cust_002",
        "mera card freeze kaise karun?",
        "knowledge_section",
        False,
    ),
]


@pytest.mark.live
@pytest.mark.parametrize(
    "customer_id,question,expected_intent,expected_escalate",
    QUESTIONS,
)
def test_real_pipeline_produces_expected_behavior(
    customer_id,
    question,
    expected_intent,
    expected_escalate,
    customers,
    capsys,
):
    """Run the real Groq-backed pipeline against the provided test questions."""

    markdown_text = load_markdown(KNOWLEDGE_FILE)
    chunks = chunk_markdown(markdown_text)
    options = main.build_router_options(chunks)

    result = main.answer(customer_id, question, options, customers)

    with capsys.disabled():
        print(f"\n[{customer_id}] {question}")
        print(f"  expected intent: {expected_intent}")
        print(f"  actual intent:   {result['intent']}")
        print(f"  expected escalate: {expected_escalate}")
        print(f"  actual escalate:   {result['escalate']}")
        print(f"  reply: {result['reply']}")

    # Basic output contract.
    assert result["reply"]
    assert isinstance(result["reply"], str)
    assert isinstance(result["escalate"], bool)

    # The important behavioral assertions for the take-home.
    assert result["intent"] == expected_intent
    assert result["escalate"] == expected_escalate

    # Restricted customer fields must never appear in a customer-facing reply.
    if customer_id == "cust_001" and "card number" in question.lower():
        assert "42101-1234567-8" not in result["reply"]
        assert "5123 45** **** 7788" not in result["reply"]
        assert "PK24PAYW0000001234567890" not in result["reply"]


def test_pipeline_uses_the_real_knowledge_base(customers):
    """Sanity-check that the live test is using the supplied KB, not fake options."""

    markdown_text = load_markdown(KNOWLEDGE_FILE)
    chunks = chunk_markdown(markdown_text)
    options = main.build_router_options(chunks)

    titles = {option["title"] for option in options}

    assert "Freezing / unfreezing a card" in titles
    assert "Card declined / online payment failing" in titles
    assert "Tap to pay" in titles
    assert "Account deletion" in titles


def test_build_router_options_filters_preamble_chunk():
    """knowledge.md opens with an H1 title and an intro blockquote before
    the first '##'. The splitter returns that as its own chunk with no
    'section' key - it must never reach the router as a fake option."""

    markdown_text = load_markdown(KNOWLEDGE_FILE)
    chunks = chunk_markdown(markdown_text)

    # Confirms the premise: there really is a preamble chunk in the raw split.
    assert any("section" not in c.metadata for c in chunks)

    options = main.build_router_options(chunks)

    assert all(o["title"] != "Untitled" for o in options)