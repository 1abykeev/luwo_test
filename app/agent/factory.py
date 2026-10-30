from app.config import settings

from .claude_client import ClaudeClient
from .fake_client import FakeLLMClient, text_response
from .llm import LLMClient, LLMError, LLMRequest, LLMResponse


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
        # Only useful to start the server without a key; tests and load tests build their own script.
        return FakeLLMClient(lambda request: text_response("This is the fake model speaking."))
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'")
