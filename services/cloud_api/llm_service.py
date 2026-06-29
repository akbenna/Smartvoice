"""
SmartVoice Cloud API - LLM Service

Pluggable LLM with support for:
  - Mistral Small (EU-based, AVG-friendly, default)
  - Anthropic Claude Haiku (best quality)
  - Google Gemini Flash (cheapest)

Compatible with Python 3.9+.
"""

from __future__ import annotations

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
) -> str:
    """Send a prompt to the LLM and return the response text.

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
            system_prompt, user_prompt, json_mode, max_tokens
        )
    elif provider == "anthropic":
        return await _complete_anthropic(
            system_prompt, user_prompt, json_mode, max_tokens, cache_system
        )
    elif provider == "gemini":
        return await _complete_gemini(
            system_prompt, user_prompt, json_mode, max_tokens
        )
    else:
        raise ValueError(f"Onbekende LLM provider: {provider}")


async def _complete_mistral(
    system_prompt: str, user_prompt: str, json_mode: bool, max_tokens: int,
) -> str:
    """Complete using Mistral API (EU-based)."""
    config = get_config()
    api_key = config.llm.mistral_api_key
    if not api_key:
        raise ValueError("MISTRAL_API_KEY niet geconfigureerd.")

    body = {
        "model": config.llm.mistral_model,
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
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]


async def _complete_anthropic(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool,
    max_tokens: int,
    cache_system: bool = False,
) -> str:
    """Complete using Anthropic Claude API.

    Kostenoptimalisaties:
      - JSON-prefill: bij json_mode starten we de assistant-beurt met "{" zodat
        Claude direct geldige JSON produceert (geen markdown-fences, geen
        inleidende zin). Bespaart output-tokens en elimineert parse-fouten.
      - Per-call max_tokens (zie complete()).
      - Optionele prompt-cache markering op de system-prompt.
    """
    config = get_config()
    api_key = config.llm.anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY niet geconfigureerd.")

    # System-prompt als content-block, eventueel met cache_control. Onder de
    # modeldrempel negeert Anthropic de cache; boven de drempel ~90% korting.
    system_block = {"type": "text", "text": system_prompt}
    if cache_system:
        system_block["cache_control"] = {"type": "ephemeral"}

    messages = [{"role": "user", "content": user_prompt}]
    if json_mode:
        # Prefill dwingt geldige JSON af; we plakken de "{" later terug.
        messages.append({"role": "assistant", "content": "{"})

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": config.llm.anthropic_model,
                "max_tokens": max_tokens,
                "temperature": config.llm.temperature,
                "system": [system_block],
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()

    usage = data.get("usage", {})
    logger.info(
        "llm.anthropic.usage",
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read=usage.get("cache_read_input_tokens"),
        cache_write=usage.get("cache_creation_input_tokens"),
    )

    text = data["content"][0]["text"]
    if json_mode:
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
