"""
Extraction service tests with mocked LLM.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from services.extraction.service import LLMClient, ExtractionService


# === LLMClient JSON parsing tests ===

def test_llm_client_parse_json():
    """Test _parse_json with valid JSON."""
    client = LLMClient(host="http://localhost:11434", model="llama3.1:8b")
    valid_json = '{"key": "value", "number": 42}'
    result = client._parse_json(valid_json)
    assert result["key"] == "value"
    assert result["number"] == 42


def test_llm_client_parse_json_markdown_block():
    """Test _parse_json with ```json ... ``` wrapped."""
    client = LLMClient(host="http://localhost:11434", model="llama3.1:8b")
    markdown_json = '''Here is the JSON:
```json
{"klachten": ["Hoofdpijn"], "diagnose": "Migraine"}
```
That was the result.'''
    result = client._parse_json(markdown_json)
    assert result["diagnose"] == "Migraine"
    assert "Hoofdpijn" in result["klachten"]


def test_llm_client_parse_json_markdown_block_plain():
    """Test _parse_json with ``` (plain) wrapped."""
    client = LLMClient(host="http://localhost:11434", model="llama3.1:8b")
    markdown_json = '''```
{"status": "ok", "id": 123}
```'''
    result = client._parse_json(markdown_json)
    assert result["status"] == "ok"


def test_llm_client_parse_json_invalid():
    """Test _parse_json with non-JSON raises."""
    client = LLMClient(host="http://localhost:11434", model="llama3.1:8b")
    invalid = "This is not JSON at all!"
    with pytest.raises(json.JSONDecodeError):
        client._parse_json(invalid)


# === ExtractionService tests with mocked LLM ===

@pytest.mark.asyncio
async def test_extraction_service_extract():
    """Mock LLM to return valid extraction JSON."""
    config = AsyncMock()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout = 120

    service = ExtractionService(config)

    # Mock LLM response
    mock_response = {
        "klachten": ["Hoofdpijn", "Koorts"],
        "anamnese": {"duur": "3 dagen"},
        "lichamelijk_onderzoek": {"bloed_druk": "120/80"},
        "vitale_parameters": {"temp": 37.5},
        "medicatie": {"huidsig": ["Paracetamol"]},
        "allergieen": [],
        "voorgeschiedenis": [],
    }

    with patch.object(service.llm, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_response
        result = await service.extract("Arts: Goedemorgen. Patient: Ik heb hoofdpijn.")

    assert result["klachten"] == ["Hoofdpijn", "Koorts"]
    assert result["anamnese"]["duur"] == "3 dagen"
    mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_extraction_service_generate_soep():
    """Mock LLM, verify S/O/E/P fields present."""
    config = AsyncMock()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout = 120

    service = ExtractionService(config)

    extraction_data = {
        "klachten": ["Hoofdpijn"],
        "anamnese": {"duur": "3 dagen"},
    }

    mock_soep = {
        "S": "Patiënt meldt hoofdpijn sinds 3 dagen",
        "O": "Bloed druk 120/80, temperatuur normaal",
        "E": "Spanningstypische hoofdpijn",
        "P": "Paracetamol 500mg twee keer per dag",
        "icpc_code": "N01",
        "icpc_titel": "Hoofdpijn",
    }

    with patch.object(service.llm, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_soep
        result = await service.generate_soep(extraction_data)

    assert "S" in result
    assert "O" in result
    assert "E" in result
    assert "P" in result
    assert result["icpc_code"] == "N01"
    mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_extraction_service_detect_flags():
    """Mock LLM, verify rode_vlaggen and ontbrekende_info."""
    config = AsyncMock()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout = 120

    service = ExtractionService(config)

    extraction_data = {"klachten": ["Ernstige pijn"]}
    soep_data = {"S": "Test", "E": "Test diagnose"}

    mock_detection = {
        "rode_vlaggen": [
            {"flag": "Ernstige symptomen", "severity": "high"},
        ],
        "ontbrekende_info": [
            "Allergiën niet genoteerd",
            "Vorige medicatie niet vastgesteld",
        ],
    }

    with patch.object(service.llm, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_detection
        result = await service.detect_flags(extraction_data, soep_data)

    assert len(result["rode_vlaggen"]) == 1
    assert len(result["ontbrekende_info"]) == 2
    mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_extraction_service_patient_instruction():
    """Mock LLM, verify plain text response."""
    config = AsyncMock()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout = 120

    service = ExtractionService(config)

    soep_data = {
        "S": "Patiënt heeft hoofdpijn",
        "E": "Spanningstypische hoofdpijn",
        "P": "Paracetamol voorgeschreven",
    }

    mock_instruction = (
        "Neem één of twee paracetamoltabletten van 500 mg. "
        "Dit mag tot drie keer per dag. "
        "Drink veel water en zorg voor rust."
    )

    with patch.object(service.llm, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_instruction
        result = await service.generate_patient_instruction(soep_data)

    assert isinstance(result, str)
    assert "paracetamol" in result.lower()
    assert len(result) > 10
    mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_extraction_missing_soep_fields():
    """Verify defaults added for missing S/O/E/P."""
    config = AsyncMock()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout = 120

    service = ExtractionService(config)

    extraction_data = {"klachten": ["Test"]}

    # Mock response with missing fields
    incomplete_soep = {
        "S": "Subjectief deel",
        # Missing O, E, P
        "icpc_code": "N01",
    }

    with patch.object(service.llm, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = incomplete_soep
        result = await service.generate_soep(extraction_data)

    # Should have defaults
    assert "S" in result
    assert "O" in result
    assert "E" in result
    assert "P" in result
    assert result["S"] == "Subjectief deel"
    assert result["O"] == ""
    assert result["E"] == ""
    assert result["P"] == ""


# === Integration-like test with multiple steps ===

@pytest.mark.asyncio
async def test_extraction_full_workflow():
    """Simulate a full extraction workflow."""
    config = AsyncMock()
    config.ollama.host = "http://localhost:11434"
    config.ollama.model = "llama3.1:8b"
    config.ollama.timeout = 120

    service = ExtractionService(config)

    transcript = "arts: Goedemorgen. Patient: Hallo, ik heb al drie dagen hoofdpijn."

    # Mock extract
    extraction_response = {
        "klachten": ["Hoofdpijn"],
        "anamnese": {"duur": "3 dagen"},
        "lichamelijk_onderzoek": {},
        "medicatie": [],
        "allergieen": [],
        "voorgeschiedenis": [],
    }

    # Mock generate_soep
    soep_response = {
        "S": "Patiënt met hoofdpijn van 3 dagen",
        "O": "Geen afwijkingen",
        "E": "Spanningstypische hoofdpijn",
        "P": "Paracetamol voorgeschreven",
        "icpc_code": "N01",
        "icpc_titel": "Hoofdpijn",
    }

    # Mock detect_flags
    detection_response = {
        "rode_vlaggen": [],
        "ontbrekende_info": ["Allergiën niet vastgesteld"],
    }

    # Mock patient instruction
    instruction_response = "Neem paracetamol en rust uit."

    with patch.object(service.llm, 'generate', new_callable=AsyncMock) as mock_gen:
        # Set different returns for each call
        mock_gen.side_effect = [
            extraction_response,
            soep_response,
            detection_response,
            instruction_response,
        ]

        # Step 1: Extract
        extraction = await service.extract(transcript)
        assert extraction["klachten"] == ["Hoofdpijn"]

        # Step 2: Generate SOEP
        soep = await service.generate_soep(extraction)
        assert soep["S"] == "Patiënt met hoofdpijn van 3 dagen"

        # Step 3: Detect flags
        detection = await service.detect_flags(extraction, soep)
        assert len(detection["ontbrekende_info"]) == 1

        # Step 4: Patient instruction
        instruction = await service.generate_patient_instruction(soep)
        assert "paracetamol" in instruction.lower()

    assert mock_gen.call_count == 4
