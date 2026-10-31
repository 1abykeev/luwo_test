from app.config import settings

from .claude_client import ClaudeClient
from .fake_client import FakeLLMClient
from .llm import LLMClient, LLMError, LLMRequest, LLMResponse
from .load_script import load_test_script


class UnconfiguredClient:
    """Stands in when there is no API key, so the server still starts and says honestly what is wrong."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMError("auth", "ANTHROPIC_API_KEY is not set")


def build_llm_client() -> LLMClient:
    """Pick the model client from settings. The only place that knows the provider names."""
    if settings.llm_provider == "claude":
        if not settings.anthropic_api_key:
            return UnconfiguredClient()
        return ClaudeClient(settings.anthropic_api_key, settings.llm_model, settings.llm_thinking)
    if settings.llm_provider == "fake":
        # For load tests and for trying the app without a key: calls read tools only, never changes data.
        return FakeLLMClient(load_test_script, delay=settings.fake_llm_delay, record=False)
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'")
