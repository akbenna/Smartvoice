"""
SmartVoice Cloud API — LLM Service
====================================
Pluggable LLM met Mistral (EU, AVG-veilig), Anthropic Claude Haiku,
en Google Gemini Flash. Elke provider: generate(system, user) -> str.
"""

import json
import logging
from abc import ABC, abstractmethod

import httpx

from services.cloud_api.config import config

logger = logging.getLogger("smartvoice.llm")


class LLMProvider(ABC):
    """Basis-interface voor alle LLM providers."""

    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Genereer tekst op basis van system + user prompt."""
        ...


class MistralLLM(LLMProvider):
    """
    Mistral Small — EU-gevestigd (Parijs), beste keuze voor AVG.
    ~€0,001 per 1K tokens. Goede Nederlandse taalvaardigheid.
    """

    API_URL = "https://api.mistral.ai/v1/chat/completions"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        api_key = config.llm.mistral_api_key
        if not api_key:
            raise ValueError("MISTRAL_API_KEY niet geconfigureerd")

        payload = {
            "model": config.llm.mistral_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.15,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Mistral fout %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Mistral fout: {resp.status_code} — {resp.text}")

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info(
            "Mistral generatie voltooid: model=%s, tokens=%s",
            config.llm.mistral_model,
            data.get("usage", {}).get("total_tokens", "?"),
        )
        return content


class AnthropicLLM(LLMProvider):
    """
    Claude Haiku — snelste Anthropic model (~€0,00025 per 1K input).
    Zeer sterke instructie-opvolging, ideaal voor gestructureerde output.
    """

    API_URL = "https://api.anthropic.com/v1/messages"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        api_key = config.llm.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY niet geconfigureerd")

        payload = {
            "model": config.llm.anthropic_model,
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.15,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Anthropic fout %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Anthropic fout: {resp.status_code} — {resp.text}")

        data = resp.json()
        content = data["content"][0]["text"]
        logger.info(
            "Anthropic generatie voltooid: model=%s, input=%s output=%s tokens",
            config.llm.anthropic_model,
            data.get("usage", {}).get("input_tokens", "?"),
            data.get("usage", {}).get("output_tokens", "?"),
        )
        return content


class GeminiLLM(LLMProvider):
    """
    Google Gemini 2.0 Flash — goedkoopste optie (~€0,000075 per 1K tokens).
    Extreem snel, goed voor hoge volumes.
    """

    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        api_key = config.llm.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY niet geconfigureerd")

        model = config.llm.gemini_model
        url = f"{self.API_BASE}/{model}:generateContent?key={api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.15,
                "maxOutputTokens": 2048,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Gemini fout %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Gemini fout: {resp.status_code} — {resp.text}")

        data = resp.json()
        content = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        usage = data.get("usageMetadata", {})
        logger.info(
            "Gemini generatie voltooid: model=%s, prompt=%s output=%s tokens",
            model,
            usage.get("promptTokenCount", "?"),
            usage.get("candidatesTokenCount", "?"),
        )
        return content


# ── Provider registry ──────────────────────────────────────────────

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "mistral": MistralLLM,
    "anthropic": AnthropicLLM,
    "gemini": GeminiLLM,
}


def get_llm_provider(name: str | None = None) -> LLMProvider:
    """
    Haal een LLM provider op basis van naam.
    Zonder naam: gebruik de geconfigureerde default.
    """
    provider_name = (name or config.llm.default_provider).lower()
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Onbekende LLM provider: '{provider_name}'. "
            f"Kies uit: {', '.join(_PROVIDERS.keys())}"
        )
    return cls()
