"""Cloud LLM client used for proposal drafting.

Provider-agnostic on purpose: the app is configured with `LLM_PROVIDER` plus an
API key the user supplies later. Each provider is called through its own
official SDK — never a cross-provider compatibility shim.

With no key configured, `is_configured()` is False and the proposal service
falls back to a locally generated draft rather than failing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """No usable LLM is configured."""


class LLMError(RuntimeError):
    """The provider was called but did not return usable content."""


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str


def is_configured() -> bool:
    return bool(settings.llm_api_key) and settings.llm_provider != "none"


def provider_status() -> dict:
    """Surfaced in the UI so it is obvious whether drafts are AI-written."""
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "configured": is_configured(),
        "hint": (
            "Set LLM_API_KEY in your .env and restart the backend to enable "
            "AI-written proposals."
            if not is_configured()
            else None
        ),
    }


async def complete(system: str, user: str) -> LLMResponse:
    """Single-turn completion. Raises LLMUnavailable / LLMError."""
    if not is_configured():
        raise LLMUnavailable("No LLM API key configured")

    if settings.llm_provider == "anthropic":
        return await _complete_anthropic(system, user)
    if settings.llm_provider == "openai":
        return await _complete_openai(system, user)
    raise LLMUnavailable(f"Unsupported provider: {settings.llm_provider}")


async def _complete_anthropic(system: str, user: str) -> LLMResponse:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise LLMUnavailable("anthropic SDK is not installed") from exc

    client = anthropic.AsyncAnthropic(
        api_key=settings.llm_api_key, timeout=settings.llm_timeout_seconds
    )
    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as exc:
        raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc
    finally:
        await client.close()

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise LLMError("Anthropic returned no text content")
    return LLMResponse(text=text, model=response.model, provider="anthropic")


async def _complete_openai(system: str, user: str) -> LLMResponse:
    try:
        import openai
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("openai SDK is not installed") from exc

    client = openai.AsyncOpenAI(
        api_key=settings.llm_api_key, timeout=settings.llm_timeout_seconds
    )
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except openai.APIStatusError as exc:
        raise LLMError(f"OpenAI API error {exc.status_code}") from exc
    except openai.APIConnectionError as exc:
        raise LLMError(f"Could not reach the OpenAI API: {exc}") from exc
    finally:
        await client.close()

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise LLMError("OpenAI returned no text content")
    return LLMResponse(text=text, model=response.model, provider="openai")
