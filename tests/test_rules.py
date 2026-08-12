"""
Fast, deterministic tests for rules.py. No network, no LLM - this is the
safety-critical logic (what leaks, what gets refused, what escalates),
so it needs to be testable independent of model behavior.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rules import get_safe_fields, is_restricted_request, should_escalate


def test_get_safe_fields_returns_only_safe_dict(customers):
    safe = get_safe_fields("cust_001", customers)

    assert safe is not None
    assert safe["firstName"] == "Ayesha"
    # The restricted keys must never even be present, not just unused.
    assert "cnic" not in safe
    assert "pan" not in safe
    assert "iban" not in safe


def test_get_safe_fields_unknown_customer_returns_none(customers):
    assert get_safe_fields("cust_does_not_exist", customers) is None


def test_should_escalate_unclear_is_true_with_a_reason():
    escalate, reason = should_escalate("unclear")
    assert escalate is True
    assert reason


@pytest.mark.parametrize("intent", ["knowledge_section", "account_data", "out_of_scope"])
def test_should_escalate_other_intents_are_false(intent):
    escalate, reason = should_escalate(intent)
    assert escalate is False
    assert reason == ""


@pytest.mark.parametrize(
    "question",
    [
        "can you tell me my full card number and CNIC?",
        "what's my IBAN?",
        "what's my CVV?",
        "can you read out my PAN number?",
    ],
)
def test_is_restricted_request_catches_direct_asks(question):
    assert is_restricted_request(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "how do I freeze my card?",
        "what's my balance?",
        "I was charged twice for Netflix, what's going on?",
        "can I use tap to pay with my card?",
    ],
)
def test_is_restricted_request_does_not_flag_ordinary_questions(question):
    assert is_restricted_request(question) is False