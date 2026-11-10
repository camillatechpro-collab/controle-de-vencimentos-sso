"""Modo demonstração (variável SST_DEMO=1).

Pensado para publicar uma vitrine pública do sistema (ex.: Streamlit Community Cloud):
- cria automaticamente a "Empresa Demonstração" com dados fictícios na primeira execução;
- mostra o acesso de demonstração na tela de login (com botão de entrada direta);
- impede que um visitante quebre a demonstração para os demais
  (troca/reset de senha e alteração da conta demo, bloqueio por tentativas, envio de anexos).

Fora do modo demonstração nada disso é ativado.
"""

from __future__ import annotations

import importlib.util

from sst.config import BASE_DIR, get_settings
from sst.domain.exceptions import RegraNegocioError

EMAIL = "demo@exemplo.com.br"
SENHA = "Demo2026senha"
MSG_BLOQUEADO = "Ação desativada na demonstração pública."


def ativo() -> bool:
    return get_settings().demo


def preparar_dados() -> None:
    """Cria (uma única vez) a empresa e os dados fictícios usando scripts/dados_demo.py."""
    caminho = BASE_DIR / "scripts" / "dados_demo.py"
    spec = importlib.util.spec_from_file_location("dados_demo", caminho)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Script de demonstração não encontrado: {caminho}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo.main()


def bloquear(motivo: str = MSG_BLOQUEADO) -> None:
    """Interrompe a ação quando o modo demonstração está ativo."""
    if ativo():
        raise RegraNegocioError(motivo)


def proteger_conta_demo(email: str | None) -> None:
    """Impede alterar a conta de demonstração (o acesso precisa continuar funcionando para todos)."""
    if ativo() and (email or "").strip().lower() == EMAIL:
        raise RegraNegocioError("A conta de demonstração não pode ser alterada.")
