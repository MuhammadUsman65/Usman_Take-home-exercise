"""
Tests the two fail-safe paths in llm.py by mocking the Groq client, so
they run without a network call or an API key. These paths are hard to
trigger against the real API on demand, but they're exactly the kind of
thing that needs proof it actually works, not just a comment saying it
should.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import llm
import main


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [MagicMock(message=MagicMock(content=content))]


@pytest.fixture(autouse=True)
def _reset_cached_client(monkeypatch):
    # llm.py caches the client in a module-level global. Reset it so no
    # test's fake client leaks into the next test.
    monkeypatch.setattr(llm, "_client", None)


def _install_fake_client(monkeypatch, create_fn):
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_fn
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)


def test_classify_fails_safe_on_malformed_json(monkeypatch):
    _install_fake_client(monkeypatch, lambda **kwargs: _FakeResponse("not json at all"))

    result = llm.classify("some question", options=[])

    assert result["intent"] == "unclear"
    assert result["section_id"] is None


def test_classify_fails_safe_on_network_error(monkeypatch):
    def _raise(**kwargs):
        raise TimeoutError("simulated network failure")

    _install_fake_client(monkeypatch, _raise)

    result = llm.classify("some question", options=[])

    assert result["intent"] == "unclear"
    assert "TimeoutError" in result["reasoning"]


def test_generate_raises_generation_error_on_network_failure(monkeypatch):
    def _raise(**kwargs):
        raise TimeoutError("simulated network failure")

    _install_fake_client(monkeypatch, _raise)

    with pytest.raises(llm.GenerationError):
        llm.generate("some question", "knowledge_section", content="approved text")


def test_answer_escalates_when_generation_fails(monkeypatch, customers):
    options = [
        {"id": 0, "title": "Freezing / unfreezing a card", "content": "Approved text."}
    ]

    monkeypatch.setattr(
        main, "classify",
        lambda question, options: {"intent": "knowledge_section", "section_id": 0, "reasoning": ""},
    )

    def _raise_generation_error(*args, **kwargs):
        raise main.GenerationError("simulated failure")

    monkeypatch.setattr(main, "generate", _raise_generation_error)

    result = main.answer("cust_001", "how do I freeze my card?", options, customers)

    assert result["escalate"] is True
    assert result["reply"] == main.GENERATION_FAILURE_MESSAGE