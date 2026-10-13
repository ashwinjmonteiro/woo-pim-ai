"""HTTP adapter tests using a mocked OpenAI-compatible endpoint."""

import respx
from httpx import Response

from src.llm.openai_compatible import (
    LLMProviderError,
    LLMRateLimitError,
    OpenAICompatibleClient,
)

LLM_URL = "https://llm.test/v1"


def _completion():
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "suggest_tags", "arguments": '{"tags":["mouse"]}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def _client():
    return OpenAICompatibleClient(LLM_URL, "test-key", "test-model", 2)


def test_adapter_parses_openai_tool_calls():
    with respx.mock(base_url=LLM_URL) as router:
        route = router.post("/chat/completions").mock(return_value=Response(200, json=_completion()))
        response = _client().chat([{"role": "user", "content": "mouse"}], [])
    assert route.called
    assert response.tool_calls[0].name == "suggest_tags"
    assert response.tool_calls[0].arguments == '{"tags":["mouse"]}'


def test_adapter_retries_429_and_honors_zero_retry_after():
    with respx.mock(base_url=LLM_URL) as router:
        route = router.post("/chat/completions").mock(side_effect=[Response(429, headers={"Retry-After": "0"}), Response(200, json=_completion())])
        response = _client().chat([{"role": "user", "content": "mouse"}], [])
    assert route.call_count == 2
    assert response.tool_calls[0].name == "suggest_tags"


def test_adapter_does_not_retry_other_client_errors():
    with respx.mock(base_url=LLM_URL) as router:
        route = router.post("/chat/completions").mock(return_value=Response(400, json={"error": {"message": "bad request"}}))
        try:
            _client().chat([], [])
        except LLMProviderError as error:
            assert "HTTP 400" in str(error)
        else:
            raise AssertionError("expected provider error")
    assert route.call_count == 1


def test_adapter_exhausted_rate_limit_has_custom_exception():
    original_sleep = OpenAICompatibleClient._request.retry.sleep
    OpenAICompatibleClient._request.retry.sleep = lambda _: None
    try:
        with respx.mock(base_url=LLM_URL) as router:
            route = router.post("/chat/completions").mock(return_value=Response(429, headers={"Retry-After": "0"}))
            try:
                _client().chat([], [])
            except LLMRateLimitError as error:
                assert "persisted" in str(error)
            else:
                raise AssertionError("expected rate-limit error")
        assert route.call_count == 3
    finally:
        OpenAICompatibleClient._request.retry.sleep = original_sleep
