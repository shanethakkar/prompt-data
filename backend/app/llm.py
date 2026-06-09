"""LLM client seam.

The pipeline depends on the narrow LLMClient protocol, not on the Anthropic SDK
directly. This keeps SDK details (structured-output parsing, prompt caching,
thinking config) in one adapter and lets tests inject a deterministic fake that
spends no tokens. generate_structured returns a validated Pydantic object of the
requested type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    import anthropic

T = TypeVar("T", bound=BaseModel)

# SQL plus a one-line explanation is short; this is generous headroom.
_MAX_TOKENS = 2048


class LLMError(Exception):
    """Raised when the model returns no parsable structured output."""


class LLMClient(Protocol):
    """The single call the pipeline makes against a model."""

    def generate_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        output_format: type[T],
        temperature: float,
    ) -> T: ...


class AnthropicClient:
    """LLMClient backed by the Anthropic Messages API with structured outputs.

    The system text is sent as a single cache_control block so it is cached
    across self-correction retries and across requests (the schema card and
    semantic layer are byte-stable for a given database).
    """

    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def generate_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        output_format: type[T],
        temperature: float,
    ) -> T:
        response = self._client.messages.parse(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=output_format,
            temperature=temperature,
            thinking={"type": "disabled"},
        )
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("Model returned no parsable structured output.")
        return parsed


def build_client() -> AnthropicClient:
    """Construct the production client. Reads ANTHROPIC_API_KEY from the env."""
    import anthropic

    return AnthropicClient(anthropic.Anthropic())


def get_llm_client() -> LLMClient:
    """FastAPI dependency. Overridden in tests with a fake."""
    return build_client()
