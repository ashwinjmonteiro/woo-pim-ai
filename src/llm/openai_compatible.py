"""OpenAI SDK client configured for compatible free/local providers."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from openai import APIStatusError, APITimeoutError, OpenAI, OpenAIError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from src.llm.base import ChatResponse, ToolCall


class LLMRateLimitError(Exception):
    """Provider rate limit remained after bounded retries."""


class LLMProviderError(Exception):
    """Provider returned an unusable response or failed permanently."""


_fallback_wait = wait_random_exponential(multiplier=0.5, max=8)


def _wait_for_retry(retry_state: Any) -> float:
    """Honor numeric Retry-After headers before applying exponential jitter."""
    outcome = retry_state.outcome
    error = outcome.exception() if outcome else None
    response = getattr(error, "response", None)
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
                return max(0.0, (retry_time - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError):
                pass
    return _fallback_wait(retry_state)


class OpenAICompatibleClient:
    """Call Groq or Ollama through the OpenAI Python SDK."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key or "ollama", timeout=timeout, max_retries=0)
        self.model = model

    @retry(
        retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
        wait=_wait_for_retry,
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Perform a bounded request retry for rate limits and timeouts."""
        return self.client.chat.completions.create(
            model=self.model, messages=messages, tools=tools, tool_choice="auto"
        )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResponse:
        """Return normalized function calls or raise a clear provider exception."""
        try:
            result = self._request(messages, tools)
        except RateLimitError as error:
            raise LLMRateLimitError("LLM provider rate limit persisted after retries") from error
        except APITimeoutError as error:
            raise LLMProviderError("LLM provider request timed out") from error
        except APIStatusError as error:
            raise LLMProviderError(f"LLM provider returned HTTP {error.status_code}") from error
        except OpenAIError as error:
            raise LLMProviderError(f"LLM provider request failed: {error}") from error
        if not result.choices:
            raise LLMProviderError("LLM provider returned an empty response")
        message = result.choices[0].message
        calls = [ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments) for call in (message.tool_calls or [])]
        return ChatResponse(tool_calls=calls, content=message.content)
