"""Testes do nó CONDITION ASSESSMENT — Vision sobre foto do edital."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.deep.nodes.condition_assessment import assess_condition


def _vision_mock_payload(payload) -> MagicMock:  # type: ignore[no-untyped-def]
    vis = MagicMock()
    vis.assess.return_value = payload
    return vis


# =============================================================================
# Nó assess_condition (camada do Deep)
# =============================================================================
def test_assess_condition_returns_placeholder_when_image_missing() -> None:
    """Sem image_url → não chama o LLM e devolve placeholder explicativo."""
    vis = MagicMock()
    out = assess_condition(image_url=None, vision=vis)
    assert out.conservation_level is None
    assert out.confidence == "LOW"
    assert "image_url" in (out.notes or "")
    vis.assess.assert_not_called()


def test_assess_condition_returns_placeholder_for_empty_string() -> None:
    vis = MagicMock()
    out = assess_condition(image_url="", vision=vis)
    assert out.conservation_level is None
    vis.assess.assert_not_called()


def test_assess_condition_converts_vision_payload_to_result() -> None:
    """Nó converte o VisionPayload cru em ConditionAssessmentResult."""
    from app.services.vision_service import VisionPayload

    payload = VisionPayload(
        conservation_level="regular",
        suggested_renovation_level="moderate",
        risk_flags=["mancha de umidade no teto"],
        notes="Foto do banheiro mostra umidade.",
        confidence="MEDIUM",
    )
    vis = _vision_mock_payload(payload)
    out = assess_condition(image_url="https://cdn.example.com/foto.jpg", vision=vis)
    assert out.conservation_level == "regular"
    assert out.suggested_renovation_level == "moderate"
    assert out.risk_flags == ["mancha de umidade no teto"]
    assert out.confidence == "MEDIUM"
    assert out.cost_estimate_usd == pytest.approx(0.03)
    vis.assess.assert_called_once_with("https://cdn.example.com/foto.jpg")


def test_assess_condition_returns_placeholder_when_vision_returns_none() -> None:
    """LLM falhou (vision.assess devolveu None) → placeholder com nota."""
    vis = _vision_mock_payload(None)
    out = assess_condition(image_url="https://cdn.example.com/foto.jpg", vision=vis)
    assert out.conservation_level is None
    assert out.confidence == "LOW"
    assert out.notes and "falhou" in out.notes


# =============================================================================
# VisionService (camada de I/O ao LLM)
# =============================================================================
def test_vision_service_returns_none_on_llm_exception() -> None:
    """O service absorve exceções e devolve None — não levanta."""
    from app.services.vision_service import VisionService

    vis = VisionService.__new__(VisionService)  # bypass do __init__
    vis._llm = MagicMock()
    vis._llm.invoke.side_effect = RuntimeError("openai 429")
    vis._model = "gpt-4o"  # type: ignore[attr-defined]

    assert vis.assess("https://cdn.example.com/foto.jpg") is None


def test_vision_service_returns_payload_on_success() -> None:
    """LLM responde estruturado → service devolve VisionPayload."""
    from app.services.vision_service import VisionService, VisionPayload

    vis = VisionService.__new__(VisionService)
    vis._llm = MagicMock()
    vis._llm.invoke.return_value = VisionPayload(
        conservation_level="bom",
        suggested_renovation_level="basic",
        risk_flags=["fiação aparente"],
        notes="Foto do interior, sala bem iluminada.",
        confidence="HIGH",
    )
    vis._model = "gpt-4o"  # type: ignore[attr-defined]

    out = vis.assess("https://cdn.example.com/foto.jpg")
    assert out is not None
    assert out.conservation_level == "bom"
    assert out.risk_flags == ["fiação aparente"]


def test_vision_service_handles_empty_image_url() -> None:
    """URL vazia → None sem chamar LLM."""
    from app.services.vision_service import VisionService

    vis = VisionService.__new__(VisionService)
    vis._llm = MagicMock()
    vis._model = "gpt-4o"  # type: ignore[attr-defined]

    assert vis.assess("") is None
    vis._llm.invoke.assert_not_called()
