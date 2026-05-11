"""Fixtures globais para a suíte de testes.

Em particular: isolamos chamadas HTTP externas que não fazem parte do
contrato de cada teste (BACEN SGS), garantindo determinismo e velocidade.
"""

from __future__ import annotations

import pytest

from app.services import bacen_service

# Guardamos a referência original do método em tempo de import — ANTES que
# qualquer fixture/teste possa substituí-lo. Testes que validam o
# comportamento real do método (test_bacen_service.py) podem restaurá-lo.
_ORIGINAL_GET_CDI_ANNUAL = bacen_service.BacenService.get_cdi_annual


@pytest.fixture(autouse=True)
def stub_bacen_cdi(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Por default, BACEN.get_cdi_annual retorna um valor determinístico.

    Excluído automaticamente dos testes em ``test_bacen_service.py``, que
    validam a implementação real (com httpx.get mockado nos próprios
    testes). Testes que precisam validar o caminho de falha do BACEN em
    outros módulos podem sobrescrever o stub localmente via monkeypatch.
    """
    if request.node.fspath.basename == "test_bacen_service.py":
        # Restaura o método original antes do teste rodar.
        monkeypatch.setattr(
            bacen_service.BacenService,
            "get_cdi_annual",
            _ORIGINAL_GET_CDI_ANNUAL,
        )
        bacen_service.get_bacen_service.cache_clear()
        return

    def _stub_cdi(self: bacen_service.BacenService) -> float:
        # Valor representativo de 2026 — qualquer mudança no número aqui
        # afeta apenas o spread esperado em testes que olham para ele.
        return 0.144

    monkeypatch.setattr(
        bacen_service.BacenService, "get_cdi_annual", _stub_cdi, raising=True
    )
    bacen_service.get_bacen_service.cache_clear()
