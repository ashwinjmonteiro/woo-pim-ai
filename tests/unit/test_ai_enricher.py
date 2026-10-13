"""AI enrichment workflow tests using local fake clients only."""

import json

from src.agents.ai_enricher import AIEnricher
from src.llm.base import ChatResponse, ToolCall
from src.llm.mock_client import MockLLMClient
from src.llm.openai_compatible import LLMRateLimitError


class FixedClient:
    """Return one configured response or raise one configured exception."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        if self.error:
            raise self.error
        if callable(self.response):
            return self.response(messages, tools)
        return self.response


def test_mock_client_completes_mouse_enrichment_with_seo_description():
    result = AIEnricher(MockLLMClient()).enrich({"title": "Wireless Ergonomic Mouse"})
    assert result["status"] == "complete"
    assert 120 <= len(result["product"]["description"].split()) <= 160
    assert result["product"]["category"] == "Electronics > Accessories"
    assert {"wireless", "ergonomic", "mouse"}.issubset(result["product"]["tags"])
    assert len(result["trace"]) == 4


def test_no_tool_calls_returns_partial_result():
    client = FixedClient(ChatResponse())
    result = AIEnricher(client).enrich({"title": "A partial item"})
    assert result["status"] == "partial"
    assert "description" not in result["product"]


def test_malformed_arguments_degrade_to_partial():
    client = FixedClient(ChatResponse([ToolCall("1", "suggest_tags", "{" )]))
    result = AIEnricher(client).enrich({"title": "Mouse"})
    assert result["status"] == "partial"
    assert "Malformed arguments" in result["error"]


def test_unknown_tool_degrades_to_partial():
    client = FixedClient(ChatResponse([ToolCall("1", "not_registered", json.dumps({}))]))
    result = AIEnricher(client).enrich({"title": "Mouse"})
    assert result["status"] == "partial"
    assert "Unknown tool" in result["error"]


def test_iteration_cap_is_reported_without_crashing():
    result = AIEnricher(MockLLMClient(), max_iterations=0).enrich({"title": "Mouse"})
    assert result["status"] == "partial"
    assert "0 iterations" in result["error"]


def test_rate_limit_degrades_to_partial():
    result = AIEnricher(FixedClient(error=LLMRateLimitError("too many requests"))).enrich({"title": "Mouse"})
    assert result["status"] == "partial"
    assert result["error"] == "too many requests"
