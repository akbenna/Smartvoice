"""
SmartVoice Cloud API - LLM Service

Pluggable LLM with support for:
  - Mistral Small (EU-based, AVG-friendly, default)
  - Anthropic Claude Haiku (best quality)
  - Google Gemini Flash (cheapest)

Compatible with Python 3.9+.
"""

from __future__ import annotations

import re
from typing import Optional

import httpx
import structlog

from .config import get_config

logger = structlog.get_logger()


async def complete(
    system_prompt: str,
    user_prompt: str,
    provider: str = None,
    json_mode: bool = False,
    max_tokens: int = None,
    cache_system: bool = False,
    quality: bool = False,
    json_schema: Optional[dict] = None,
) -> str:
    """Send a prompt to the LLM and return the response text.

    quality: use the stronger model for tasks that need medical reasoning
        (SOEP generation). Only affects Anthropic; other providers have one model.
    json_schema: JSON schema for structured output on models without prefill
        support (Claude Sonnet 5 and newer). Ignored by other providers.

    Args:
        max_tokens: Override the configured output budget for this single call.
            Tuning this per call type (kort voor decisief, ruimer voor SOEP)
            voorkomt onnodige output-tokens — de duurste tokensoort bij Claude.
        cache_system: Markeer de system-prompt als cachebaar (Anthropic prompt
            caching). Levert pas korting op zodra de system-prompt boven de
            modeldrempel komt (~2048 tokens voor Haiku); kleiner wordt genegeerd.
    """
    config = get_config()
    provider = provider or config.llm.default_provider
    max_tokens = max_tokens or config.llm.max_tokens

    logger.info(
        "llm.complete",
        provider=provider,
        json_mode=json_mode,
        max_tokens=max_tokens,
    )

    if provider == "mistral":
        return await _complete_mistral(
            system_prompt, user_prompt, json_mode, max_tokens, quality
        )
    elif provider == "anthropic":
        return await _complete_anthropic(
            system_prompt, user_prompt, json_mode, max_tokens, cache_system, quality,
            json_schema,
        )
    elif provider == "gemini":
        return await _complete_gemini(
            system_prompt, user_prompt, json_mode, max_tokens
        )
    else:
        raise ValueError(f"Onbekende LLM provider: {provider}")


async def _complete_mistral(
    system_prompt: str, user_prompt, json_mode: bool, max_tokens: int,
    quality: bool = False,
) -> str:
    """Complete using Mistral API (EU-based). user_prompt may be a list of
    content parts (text and image_url) for the multimodal model."""
    config = get_config()
    api_key = config.llm.mistral_api_key
    if not api_key:
        raise ValueError("MISTRAL_API_KEY niet geconfigureerd.")

    body = {
        "model": config.llm.mistral_quality_model if quality else config.llm.mistral_model,
        "temperature": config.llm.temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code >= 400:
            logger.error("llm.mistral.error", status=response.status_code, body=response.text[:300])
            if response.status_code == 429:
                raise ValueError("Mistral: limiet bereikt (429). Controleer het abonnement.")
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]


# Claude 4.6+ models (Sonnet 5, Opus, ...) reject assistant prefill and
# sampling parameters with a 400; they take structured outputs instead.
_MODERN_CLAUDE = re.compile(r"^claude-(sonnet-5|opus-5|opus-4-[6-9]|sonnet-4-[6-9]|fable|mythos)")

# Thinking counts towards max_tokens on modern models; leave room for it.
MODERN_MIN_MAX_TOKENS = 8000


def _anthropic_text(data: dict) -> str:
    """First text block; modern models may put thinking blocks before it."""
    for block in data.get("content", []):
        if block.get("type", "text") == "text":
            return block.get("text", "")
    return ""


async def _complete_anthropic(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool,
    max_tokens: int,
    cache_system: bool = False,
    quality: bool = False,
    json_schema: Optional[dict] = None,
) -> str:
    """Complete using Anthropic Claude API.

    Haiku 4.5 (default model):
      - JSON-prefill: bij json_mode starten we de assistant-beurt met "{" zodat
        Claude direct geldige JSON produceert. Bespaart output-tokens.
      - Lage temperatuur voor medische output.
    Sonnet 5 en nieuwer (SOEP-model):
      - Geen prefill/temperatuur (400); JSON via structured outputs
        (output_config.format met json_schema) wanneer een schema is gegeven.
      - Adaptief nadenken met instelbare effort; max_tokens ruimer.
    """
    config = get_config()
    api_key = config.llm.anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY niet geconfigureerd.")

    model = config.llm.anthropic_soep_model if quality else config.llm.anthropic_model
    modern = bool(_MODERN_CLAUDE.match(model))

    # System-prompt als content-block, eventueel met cache_control. Onder de
    # modeldrempel negeert Anthropic de cache; boven de drempel ~90% korting.
    system_block = {"type": "text", "text": system_prompt}
    if cache_system:
        system_block["cache_control"] = {"type": "ephemeral"}

    messages = [{"role": "user", "content": user_prompt}]
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [system_block],
        "messages": messages,
    }
    prefilled = False
    if modern:
        body["max_tokens"] = max(max_tokens, MODERN_MIN_MAX_TOKENS)
        output_config = {"effort": config.llm.anthropic_effort}
        if json_mode and json_schema:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
        body["output_config"] = output_config
    else:
        body["temperature"] = config.llm.temperature
        if json_mode:
            # Prefill dwingt geldige JSON af; we plakken de "{" later terug.
            messages.append({"role": "assistant", "content": "{"})
            prefilled = True

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code >= 400:
            logger.error("llm.anthropic.error", status=response.status_code, body=response.text[:500])
        response.raise_for_status()
        data = response.json()

    usage = data.get("usage", {})
    logger.info(
        "llm.anthropic.usage",
        model=model,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read=usage.get("cache_read_input_tokens"),
        cache_write=usage.get("cache_creation_input_tokens"),
    )

    if data.get("stop_reason") == "refusal":
        raise ValueError("Het taalmodel weigerde dit verzoek.")

    text = _anthropic_text(data)
    if prefilled:
        # De prefill "{" zit niet in de response; voeg terug toe.
        text = "{" + text
    return text


async def _complete_gemini(
    system_prompt: str, user_prompt: str, json_mode: bool, max_tokens: int,
) -> str:
    """Complete using Google Gemini API."""
    config = get_config()
    api_key = config.llm.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY niet geconfigureerd.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.llm.gemini_model}:generateContent?key={api_key}"
    )

    body = {
        "system_instruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]},
        ],
        "generationConfig": {
            "temperature": config.llm.temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=body)
        response.raise_for_status()
        data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Geen antwoord van Gemini.")

    parts = candidates[0].get("content", {}).get("parts", [])
    return parts[0].get("text", "") if parts else ""


async def stream_anthropic(
    system_prompt: str,
    user_content,
    max_tokens: int,
    quality: bool = False,
):
    """Stream Claude's answer as text deltas (letters: text appears while written).

    user_content: a string, or a list of content blocks (text and images).
    quality: the stronger model (letters to third parties, image reading);
    otherwise the fast model (referral letters).
    """
    config = get_config()
    api_key = config.llm.anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY niet geconfigureerd.")
    model = config.llm.anthropic_soep_model if quality else config.llm.anthropic_model
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": True,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    if _MODERN_CLAUDE.match(model):
        body["max_tokens"] = max(max_tokens, MODERN_MIN_MAX_TOKENS)
        body["output_config"] = {"effort": config.llm.anthropic_effort}
    else:
        body["temperature"] = config.llm.temperature
    logger.info("llm.anthropic.stream", model=model)

    import json as _json
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
        ) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:500]
                logger.error("llm.anthropic.error", status=response.status_code, body=detail)
                raise ValueError(f"Taalmodel gaf fout {response.status_code}.")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = _json.loads(line[6:])
                except ValueError:
                    continue
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield delta["text"]
                elif event.get("type") == "message_delta":
                    if event.get("delta", {}).get("stop_reason") == "refusal":
                        raise ValueError("Het taalmodel weigerde dit verzoek.")
                elif event.get("type") == "error":
                    raise ValueError(event.get("error", {}).get("message", "Onbekende fout"))


async def stream_mistral(system_prompt: str, user_content, max_tokens: int, quality: bool = False):
    """Stream Mistral's answer as text deltas (EU-hosted)."""
    config = get_config()
    api_key = config.llm.mistral_api_key
    if not api_key:
        raise ValueError("MISTRAL_API_KEY niet geconfigureerd.")
    body = {
        "model": config.llm.mistral_quality_model if quality else config.llm.mistral_model,
        "temperature": config.llm.temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    logger.info("llm.mistral.stream", model=body["model"])
    import json as _json
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        async with client.stream(
            "POST", "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        ) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:300]
                logger.error("llm.mistral.error", status=response.status_code, body=detail)
                raise ValueError(f"Taalmodel gaf fout {response.status_code}.")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    event = _json.loads(payload)
                except ValueError:
                    continue
                for choice in event.get("choices", []):
                    piece = (choice.get("delta") or {}).get("content")
                    if isinstance(piece, str) and piece:
                        yield piece


def image_part(provider: str, media_type: str, data_b64: str) -> dict:
    """An image content part in the format of the given provider."""
    if provider == "mistral":
        return {"type": "image_url", "image_url": f"data:{media_type};base64,{data_b64}"}
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data_b64}}


def text_part(provider: str, text: str) -> dict:
    return {"type": "text", "text": text}


def stream_llm(provider: str, system_prompt: str, user_content, max_tokens: int, quality: bool = False):
    """Stream from the chosen provider (mistral | anthropic)."""
    if provider == "mistral":
        return stream_mistral(system_prompt, user_content, max_tokens=max_tokens, quality=quality)
    if provider == "anthropic":
        return stream_anthropic(system_prompt, user_content, max_tokens=max_tokens, quality=quality)
    raise ValueError(f"Onbekende LLM provider: {provider}")
