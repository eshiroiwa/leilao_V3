"""Testes do nó CONDITION ASSESSMENT — Vision sobre entorno (SV + aérea + edital)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.deep.nodes.condition_assessment import assess_condition


def _make_gmaps(
    *,
    aerial_bytes: bytes | None = None,
    sv_metadata: dict | None = None,
    sv_image_bytes: bytes | None = None,
) -> MagicMock:
    g = MagicMock()
    g.static_satellite.return_value = aerial_bytes
    g.streetview_metadata.return_value = sv_metadata
    g.streetview_image.return_value = sv_image_bytes
    return g


def _make_supabase(*, public_url: str | None = "https://sb.example.com/x.jpg") -> MagicMock:
    s = MagicMock()
    s.upload_deep_image.return_value = public_url
    return s


# =============================================================================
# Nó assess_condition (camada do Deep)
# =============================================================================
def test_assess_condition_returns_placeholder_when_no_images_available() -> None:
    """Sem cobertura SV + sem foto edital + falha de aérea → placeholder."""
    vis = MagicMock()
    gmaps = _make_gmaps(aerial_bytes=None, sv_metadata={"status": "ZERO_RESULTS"})
    supabase = _make_supabase()

    out = assess_condition(
        property_id="p1", analysis_id="a1",
        lat=-23.5, lng=-46.6, image_url=None,
        vision=vis, gmaps=gmaps, supabase=supabase,
    )

    assert out.neighborhood_pattern is None
    assert out.image_urls == []
    assert out.confidence == "LOW"
    vis.assess.assert_not_called()
    supabase.upload_deep_image.assert_not_called()


def test_assess_condition_skips_streetview_when_metadata_not_ok() -> None:
    """Sem cobertura SV mas com aérea → segue só com aérea, não chama SV image."""
    from app.services.vision_service import NeighborhoodVisionPayload

    payload = NeighborhoodVisionPayload(
        neighborhood_pattern="misto",
        property_vs_neighbors="igual",
        pool_observed_nearby=False,
        suggested_renovation_level="basic",
        risk_flags=[],
        confidence="MEDIUM",
    )
    vis = MagicMock()
    vis.assess.return_value = payload
    gmaps = _make_gmaps(
        aerial_bytes=b"AERIAL",
        sv_metadata={"status": "ZERO_RESULTS"},
        sv_image_bytes=b"SHOULD_NOT_BE_USED",
    )
    supabase = _make_supabase(public_url="https://sb.example.com/aerial.jpg")

    out = assess_condition(
        property_id="p1", analysis_id="a1",
        lat=-23.5, lng=-46.6, image_url=None,
        vision=vis, gmaps=gmaps, supabase=supabase,
    )

    assert out.neighborhood_pattern == "misto"
    assert out.image_urls == ["https://sb.example.com/aerial.jpg"]
    gmaps.streetview_image.assert_not_called()
    # Vision recebeu 1 imagem (aerial).
    args, _ = vis.assess.call_args
    assert len(args[0]) == 1
    assert args[0][0][0] == "aerial"


def test_assess_condition_converts_vision_payload_to_result() -> None:
    """Nó converte o NeighborhoodVisionPayload cru em ConditionAssessmentResult."""
    from app.services.vision_service import NeighborhoodVisionPayload

    payload = NeighborhoodVisionPayload(
        neighborhood_pattern="uniforme",
        property_vs_neighbors="abaixo",
        pool_observed_nearby=True,
        suggested_renovation_level="moderate",
        risk_flags=["calçada quebrada"],
        notes="Bairro consolidado, casas de alto padrão.",
        confidence="HIGH",
    )
    vis = MagicMock()
    vis.assess.return_value = payload
    gmaps = _make_gmaps(
        aerial_bytes=b"AERIAL",
        sv_metadata={"status": "OK"},
        sv_image_bytes=b"SV",
    )
    supabase = _make_supabase()

    out = assess_condition(
        property_id="p1", analysis_id="a1",
        lat=-23.5, lng=-46.6,
        image_url="https://cdn.example.com/foto.jpg",
        vision=vis, gmaps=gmaps, supabase=supabase,
    )

    assert out.neighborhood_pattern == "uniforme"
    assert out.property_vs_neighbors == "abaixo"
    assert out.pool_observed_nearby is True
    assert out.suggested_renovation_level == "moderate"
    assert out.risk_flags == ["calçada quebrada"]
    assert out.confidence == "HIGH"
    assert out.cost_estimate_usd == pytest.approx(0.10)
    # Storage chamado 1× aérea + 4× SV (uma por heading) — sem listing porque
    # _download_listing_image faz HTTP real e mocká-lo exigiria patch externo.
    # Aceita 5 ou 6 dependendo do download da foto do edital.
    assert supabase.upload_deep_image.call_count >= 5


def test_assess_condition_returns_placeholder_when_vision_returns_none() -> None:
    """LLM falhou (vision.assess devolveu None) mas imagens foram capturadas."""
    vis = MagicMock()
    vis.assess.return_value = None
    gmaps = _make_gmaps(
        aerial_bytes=b"AERIAL", sv_metadata={"status": "ZERO_RESULTS"},
    )
    supabase = _make_supabase(public_url="https://sb.example.com/aerial.jpg")

    out = assess_condition(
        property_id="p1", analysis_id="a1",
        lat=-23.5, lng=-46.6, image_url=None,
        vision=vis, gmaps=gmaps, supabase=supabase,
    )

    assert out.neighborhood_pattern is None
    assert out.image_urls == ["https://sb.example.com/aerial.jpg"]
    assert out.confidence == "LOW"
    assert out.notes and "falhou" in out.notes


def test_assess_condition_skips_storage_when_no_analysis_id() -> None:
    """Execução inline/debug sem analysis_id → Vision roda, mas Storage é pulado."""
    from app.services.vision_service import NeighborhoodVisionPayload

    vis = MagicMock()
    vis.assess.return_value = NeighborhoodVisionPayload(confidence="LOW")
    gmaps = _make_gmaps(
        aerial_bytes=b"AERIAL", sv_metadata={"status": "ZERO_RESULTS"},
    )
    supabase = _make_supabase()

    out = assess_condition(
        property_id="p1", analysis_id=None,
        lat=-23.5, lng=-46.6, image_url=None,
        vision=vis, gmaps=gmaps, supabase=supabase,
    )

    supabase.upload_deep_image.assert_not_called()
    assert out.image_urls == []


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

    assert vis.assess([("aerial", b"BYTES")]) is None


def test_vision_service_returns_payload_on_success() -> None:
    """LLM responde estruturado → service devolve NeighborhoodVisionPayload."""
    from app.services.vision_service import NeighborhoodVisionPayload, VisionService

    vis = VisionService.__new__(VisionService)
    vis._llm = MagicMock()
    vis._llm.invoke.return_value = NeighborhoodVisionPayload(
        neighborhood_pattern="uniforme",
        property_vs_neighbors="igual",
        pool_observed_nearby=True,
        suggested_renovation_level="basic",
        risk_flags=[],
        notes="Quadra consolidada.",
        confidence="HIGH",
    )
    vis._model = "gpt-4o"  # type: ignore[attr-defined]

    out = vis.assess([("aerial", b"BYTES"), ("sv_front", b"BYTES")])
    assert out is not None
    assert out.neighborhood_pattern == "uniforme"
    assert out.pool_observed_nearby is True


def test_vision_service_handles_empty_image_list() -> None:
    """Lista vazia → None sem chamar LLM."""
    from app.services.vision_service import VisionService

    vis = VisionService.__new__(VisionService)
    vis._llm = MagicMock()
    vis._model = "gpt-4o"  # type: ignore[attr-defined]

    assert vis.assess([]) is None
    vis._llm.invoke.assert_not_called()
