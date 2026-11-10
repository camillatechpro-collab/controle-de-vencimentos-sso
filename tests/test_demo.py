"""Modo demonstração (SST_DEMO): configuração e proteções da vitrine pública."""

from __future__ import annotations

import pytest

from sst import config, demo
from sst.domain.exceptions import RegraNegocioError
from sst.infra import armazenamento

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def modo_demo(monkeypatch):
    monkeypatch.setattr(demo, "ativo", lambda: True)


def test_flag_lida_do_ambiente(monkeypatch):
    monkeypatch.setenv("SST_DEMO", "1")
    config.get_settings.cache_clear()
    try:
        s = config.get_settings()
        assert s.demo is True
        assert s.login_max_tentativas >= 10**6  # visitantes não bloqueiam a conta compartilhada
    finally:
        monkeypatch.delenv("SST_DEMO")
        config.get_settings.cache_clear()
    assert config.get_settings().demo is False


def test_fora_da_demo_nada_e_bloqueado():
    demo.bloquear()
    demo.proteger_conta_demo(demo.EMAIL)


def test_bloqueios_na_demo(modo_demo):
    with pytest.raises(RegraNegocioError):
        demo.bloquear()
    with pytest.raises(RegraNegocioError):
        demo.proteger_conta_demo("  DEMO@exemplo.com.br ")
    demo.proteger_conta_demo("outra.pessoa@exemplo.com.br")


def test_anexo_recusado_na_demo(modo_demo):
    with pytest.raises(RegraNegocioError, match="anexos"):
        armazenamento.salvar(1, "laudo.pdf", PDF)
