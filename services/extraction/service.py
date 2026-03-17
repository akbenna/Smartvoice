"""
Extraction Service
==================
Medische informatie-extractie via lokaal LLM (Ollama).
Input: getranscribeerd consult -> Output: gestructureerde medische data (JSON).
"""

import json
import logging
import time
from pathlib import Path

import httpx
import jsonschema
import structlog

from shared.resilience import CircuitBreaker, CircuitBreakerConfig, RetryConfig, retry_async
from shared.metrics import metrics

logger = structlog.get_logger()

# Lokale imports
import sys
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from shared.prompts.templates import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    SOEP_SYSTEM_PROMPT,
    SOEP_USER_TEMPLATE,
    DETECTION_SYSTEM_PROMPT,
    DETECTION_USER_TEMPLATE,
    PATIENT_INSTRUCTION_PROMPT,
)

# Laad JSON schema's voor validatie
SCHEMA_DIR = Path(__file__).parent.parent.parent / "shared" / "schemas"

def _load_schema(name: str) -> dict:
    path = SCHEMA_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}

EXTRACTION_SCHEMA = _load_schema("medical_extraction")
SOEP_SCHEMA = _load_schema("soep_concept")
DETECTION_SCHEMA = _load_schema("detection_result")


class LLMClient:
    """Async client voor Ollama API."""

    def __init__(self, host: str, model: str, timeout: int = 120):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(
            "ollama",
            CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0)
        )
        self.retry_config = RetryConfig(
            max_retries=2,
            base_delay=2.0,
            retryable_exceptions=(httpx.TimeoutException, httpx.ConnectError, ConnectionError, OSError),
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        format_json: bool = True,
    ) -> dict | str:
        """
        Genereer een response van het lokale LLM.

        Args:
            system_prompt: Systeeminstructie
            user_prompt: Gebruikersprompt met data
            format_json: Als True, dwing JSON output af

        Returns:
            Geparsed JSON dict of raw string
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,    # Laag voor consistente medische output
                "top_p": 0.9,
                "num_predict": 4096,
            },
        }

        if format_json:
            payload["format"] = "json"

        async def _do_request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        start_time = time.monotonic()
        try:
            result = await retry_async(
                _do_request,
                config=self.retry_config,
                circuit_breaker=self.circuit_breaker,
            )
            duration = time.monotonic() - start_time
            metrics.record_llm_request("generate", self.model, duration)

            content = result.get("message", {}).get("content", "")
            if format_json:
                return self._parse_json(content)
            return content

        except httpx.TimeoutException:
            metrics.record_llm_error("generate", "timeout")
            logger.error("Ollama timeout", model=self.model, timeout=self.timeout)
            raise
        except httpx.HTTPStatusError as e:
            metrics.record_llm_error("generate", f"http_{e.response.status_code}")
            logger.error("Ollama HTTP error", status=e.response.status_code)
            raise
        except Exception as e:
            metrics.record_llm_error("generate", type(e).__name__)
            logger.error("Ollama request mislukt", error=str(e))
            raise

    def _parse_json(self, content: str) -> dict:
        """Parse JSON uit LLM response, met fallback voor common issues."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Probeer JSON te extraheren uit markdown code blocks
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                return json.loads(content[start:end])
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                return json.loads(content[start:end])
            else:
                logger.error("JSON parsing mislukt", content_preview=content[:200])
                raise


class ExtractionService:
    """
    Medische extractie uit consulttranscript.

    Gebruik:
        service = ExtractionService(config)
        extraction = await service.extract(transcript_result)
        soep = await service.generate_soep(extraction)
        detection = await service.detect_flags(extraction, soep)
    """

    def __init__(self, config):
        self.config = config
        self.llm = LLMClient(
            host=config.ollama.host,
            model=config.ollama.model,
            timeout=config.ollama.timeout,
        )

    async def extract(self, transcript_text: str) -> dict:
        """
        Extraheer gestructureerde medische informatie uit transcript.

        Args:
            transcript_text: Gelabeld transcript (arts:/patient: prefixes)

        Returns:
            dict conform medical_extraction.json schema
        """
        logger.info("Medische extractie gestart", text_length=len(transcript_text))

        user_prompt = EXTRACTION_USER_TEMPLATE.format(
            transcript=transcript_text
        )

        result = await self.llm.generate(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            format_json=True,
        )

        # Valideer tegen JSON schema
        if EXTRACTION_SCHEMA:
            try:
                jsonschema.validate(result, EXTRACTION_SCHEMA)
            except jsonschema.ValidationError as e:
                logger.warning("Extractie schema validatie mislukt",
                              error=e.message, path=list(e.absolute_path))

        logger.info("Medische extractie voltooid",
                     klachten=len(result.get("klachten", [])))
        return result

    async def generate_soep(self, extraction: dict) -> dict:
        """
        Genereer SOEP-concept uit medische extractie.

        Args:
            extraction: dict conform medical_extraction schema

        Returns:
            dict met S, O, E, P, icpc_code, icpc_titel
        """
        logger.info("SOEP-generatie gestart")

        user_prompt = SOEP_USER_TEMPLATE.format(
            extraction_json=json.dumps(extraction, ensure_ascii=False, indent=2)
        )

        result = await self.llm.generate(
            system_prompt=SOEP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            format_json=True,
        )

        # Valideer verplichte velden
        for field in ("S", "O", "E", "P"):
            if field not in result:
                result[field] = ""

        # Valideer tegen JSON schema
        if SOEP_SCHEMA:
            try:
                jsonschema.validate(result, SOEP_SCHEMA)
            except jsonschema.ValidationError as e:
                logger.warning("SOEP schema validatie mislukt",
                              error=e.message, path=list(e.absolute_path))

        logger.info("SOEP-generatie voltooid",
                     s_length=len(result.get("S", "")),
                     has_icpc=bool(result.get("icpc_code")))
        return result

    async def detect_flags(self, extraction: dict, soep: dict) -> dict:
        """
        Detecteer rode vlaggen en ontbrekende informatie.

        Args:
            extraction: Medische extractie
            soep: SOEP-concept

        Returns:
            dict met rode_vlaggen en ontbrekende_info lijsten
        """
        logger.info("Detectie gestart")

        user_prompt = DETECTION_USER_TEMPLATE.format(
            extraction_json=json.dumps(extraction, ensure_ascii=False, indent=2),
            soep_json=json.dumps(soep, ensure_ascii=False, indent=2),
        )

        result = await self.llm.generate(
            system_prompt=DETECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            format_json=True,
        )

        rode_vlaggen = result.get("rode_vlaggen", [])
        ontbrekend = result.get("ontbrekende_info", result.get("ontbrekend", []))

        detection_result = {
            "rode_vlaggen": rode_vlaggen,
            "ontbrekende_info": ontbrekend,
        }

        # Valideer tegen JSON schema
        if DETECTION_SCHEMA:
            try:
                jsonschema.validate(detection_result, DETECTION_SCHEMA)
            except jsonschema.ValidationError as e:
                logger.warning("Detectie schema validatie mislukt",
                              error=e.message, path=list(e.absolute_path))

        logger.info("Detectie voltooid",
                     red_flags=len(rode_vlaggen),
                     missing_info=len(ontbrekend))

        return detection_result

    async def generate_patient_instruction(self, soep: dict) -> str:
        """
        Genereer patientinstructie in gewone taal.

        Args:
            soep: SOEP-concept

        Returns:
            Instructietekst in eenvoudig Nederlands (B1 niveau)
        """
        prompt = PATIENT_INSTRUCTION_PROMPT.format(
            s_text=soep.get("S", ""),
            e_text=soep.get("E", ""),
            p_text=soep.get("P", ""),
        )

        result = await self.llm.generate(
            system_prompt="Je schrijft patientinstructies in eenvoudig Nederlands.",
            user_prompt=prompt,
            format_json=False,
        )

        return result.strip()


async def run_full_pipeline(config, transcript_text: str) -> dict:
    """
    Draai de volledige extractie-pipeline.

    Args:
        config: AppConfig
        transcript_text: Gelabeld transcript

    Returns:
        dict met extraction, soep, detection, patient_instruction
    """
    service = ExtractionService(config)

    # Stap 1: Medische extractie
    extraction = await service.extract(transcript_text)

    # Stap 2: SOEP-generatie
    soep = await service.generate_soep(extraction)

    # Stap 3: Rode vlaggen + missing info
    detection = await service.detect_flags(extraction, soep)

    # Stap 4: Patientinstructie
    instruction = await service.generate_patient_instruction(soep)

    return {
        "extraction": extraction,
        "soep": soep,
        "detection": detection,
        "patient_instruction": instruction,
    }
