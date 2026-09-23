"""
SmartVoice Cloud API - Live Dictation

Relays microphone audio from the side panel to Deepgram's streaming API and
sends transcript text back while the doctor is still speaking.

Client protocol (WebSocket /api/v1/dictation/stream):
  client -> server  {"type": "auth", "api_key": "...", "keyterms": [...]}
                                                          first message; keyterms
                                                          are optional user words
  client -> server  <binary audio chunks, webm/opus>
  client -> server  {"type": "stop"}                     flush and close
  server -> client  {"type": "ready"}
  server -> client  {"type": "transcript", "text": "...", "is_final": bool,
                     "speech_final": bool}
  server -> client  {"type": "error", "message": "..."}
  server -> client  {"type": "closed"}

The Deepgram key never leaves the server; audio is not stored.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from .auth import is_valid_api_key
from .config import AppConfig, get_config
from .medical_vocabulary import MEDICATION_CORRECTIONS, correct_transcript_full

logger = structlog.get_logger()

# Deepgram accepts at most 100 keyterms per request.
MAX_KEYTERMS = 100
MAX_USER_KEYTERMS = 50
MAX_KEYTERM_LENGTH = 50
AUTH_TIMEOUT_SECS = 10.0
UPSTREAM_CLOSE_TIMEOUT_SECS = 5.0

_SPOKEN_COMMANDS = [
    (re.compile(r"[\s,.]*\bnieuwe alinea\b[\s,.]*", re.IGNORECASE), "\n\n"),
    (re.compile(r"[\s,.]*\bnieuwe regel\b[\s,.]*", re.IGNORECASE), "\n"),
]


def sanitize_user_keyterms(raw: Any) -> List[str]:
    """Accept only short strings from the client, deduplicated, capped."""
    if not isinstance(raw, list):
        return []
    terms: List[str] = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        term = " ".join(item.split())
        if not term or len(term) > MAX_KEYTERM_LENGTH or term.lower() in seen:
            continue
        seen.add(term.lower())
        terms.append(term)
        if len(terms) >= MAX_USER_KEYTERMS:
            break
    return terms


def build_keyterms(user_terms: Optional[List[str]] = None) -> List[str]:
    """The doctor's own words first, then medication names, capped at Deepgram's limit."""
    terms = list(user_terms or [])
    seen = {t.lower() for t in terms}
    for name in sorted({name for name in MEDICATION_CORRECTIONS.values() if name}):
        if name.lower() not in seen:
            terms.append(name)
            seen.add(name.lower())
    return terms[:MAX_KEYTERMS]


def build_deepgram_url(cfg: AppConfig, user_terms: Optional[List[str]] = None) -> str:
    """Streaming URL with low-latency settings for single-speaker dictation."""
    params: List[tuple] = [
        ("model", cfg.dictation.deepgram_model),
        ("language", cfg.dictation.deepgram_language),
        ("punctuate", "true"),
        ("smart_format", "true"),
        ("interim_results", "true"),
        ("endpointing", str(cfg.dictation.endpointing_ms)),
    ]
    # Keyterm prompting is a Nova-3 feature and billed as an add-on.
    if cfg.dictation.keyterms_enabled and cfg.dictation.deepgram_model.startswith("nova-3"):
        params.extend(("keyterm", term) for term in build_keyterms(user_terms))
    return f"{cfg.dictation.deepgram_url}?{urlencode(params)}"


def apply_spoken_commands(text: str) -> str:
    """Turn spoken layout commands ("nieuwe regel") into line breaks."""
    for pattern, replacement in _SPOKEN_COMMANDS:
        text = pattern.sub(replacement, text)
    return text


def parse_deepgram_message(raw: str) -> Optional[Dict[str, Any]]:
    """Convert a Deepgram streaming message into a client transcript event.

    Returns None for messages the client doesn't need (metadata, empty results).
    Final segments get vocabulary correction and spoken-command handling;
    interim segments are passed through raw to keep latency minimal.
    """
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if data.get("type") != "Results":
        return None

    alternatives = data.get("channel", {}).get("alternatives") or [{}]
    text = (alternatives[0].get("transcript") or "").strip()
    if not text:
        return None

    is_final = bool(data.get("is_final"))
    if is_final:
        text, _stats = correct_transcript_full(text)
        text = apply_spoken_commands(text)

    return {
        "type": "transcript",
        "text": text,
        "is_final": is_final,
        "speech_final": bool(data.get("speech_final")),
    }


async def _default_connect(url: str, api_key: str):
    from websockets.asyncio.client import connect

    return await connect(
        url,
        additional_headers={"Authorization": f"Token {api_key}"},
        open_timeout=10,
        max_size=None,
    )


async def _authenticate(ws: WebSocket) -> Optional[Dict[str, Any]]:
    """Return the auth message if the key is valid, else None."""
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECS)
        message = json.loads(first)
    except (asyncio.TimeoutError, ValueError, KeyError, WebSocketDisconnect):
        return None
    if not isinstance(message, dict) or message.get("type") != "auth":
        return None
    if not is_valid_api_key(str(message.get("api_key") or "")):
        return None
    return message


async def _send_json(ws: WebSocket, payload: Dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
    except (RuntimeError, WebSocketDisconnect):
        pass


async def relay_dictation(
    ws: WebSocket,
    connect: Callable[[str, str], Any] = _default_connect,
) -> None:
    """Relay one dictation session between the client and Deepgram."""
    await ws.accept()
    cfg = get_config()

    auth = await _authenticate(ws)
    if auth is None:
        await _send_json(ws, {"type": "error", "message": "Ongeldige of ontbrekende API-sleutel."})
        await ws.close(code=4401)
        return

    if not cfg.stt.deepgram_api_key:
        await _send_json(ws, {"type": "error", "message": "DEEPGRAM_API_KEY niet geconfigureerd op de server."})
        await ws.close(code=4500)
        return

    try:
        user_terms = sanitize_user_keyterms(auth.get("keyterms"))
        upstream = await connect(build_deepgram_url(cfg, user_terms), cfg.stt.deepgram_api_key)
    except Exception as exc:  # handshake rejected, network, bad model/language
        logger.error("dictation.upstream_connect_failed", error=str(exc))
        await _send_json(ws, {"type": "error", "message": f"Kan spraakherkenning niet bereiken: {exc}"})
        await ws.close(code=4502)
        return

    logger.info("dictation.start", model=cfg.dictation.deepgram_model)
    await _send_json(ws, {"type": "ready"})

    async def client_to_upstream() -> None:
        # Ends on "stop", client disconnect or the session time limit.
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes"):
                    await upstream.send(message["bytes"])
                elif message.get("text"):
                    try:
                        control = json.loads(message["text"])
                    except ValueError:
                        continue
                    if control.get("type") == "stop":
                        break
        except WebSocketDisconnect:
            pass
        # Ask Deepgram to flush remaining finals, then close.
        try:
            await upstream.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass

    async def upstream_to_client() -> None:
        try:
            async for raw in upstream:
                if isinstance(raw, bytes):
                    continue
                event = parse_deepgram_message(raw)
                if event:
                    await _send_json(ws, event)
        except Exception as exc:
            logger.warning("dictation.upstream_closed", error=str(exc))

    sender = asyncio.create_task(client_to_upstream())
    receiver = asyncio.create_task(upstream_to_client())
    try:
        try:
            await asyncio.wait_for(asyncio.shield(sender), timeout=cfg.dictation.max_seconds)
        except asyncio.TimeoutError:
            # Cost guard: a forgotten open microphone must not stream for hours.
            await _send_json(ws, {"type": "error", "message": "Maximale dicteerduur bereikt; opname gestopt."})
            sender.cancel()
            try:
                await upstream.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
        try:
            await asyncio.wait_for(receiver, timeout=UPSTREAM_CLOSE_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            receiver.cancel()
    finally:
        try:
            await upstream.close()
        except Exception:
            pass
        await _send_json(ws, {"type": "closed"})
        try:
            await ws.close()
        except RuntimeError:
            pass
        logger.info("dictation.end")
