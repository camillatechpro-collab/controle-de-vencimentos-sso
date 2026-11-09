"""Configuração de logs: arquivo rotativo + console.

Regra: logar IDs e eventos, nunca CPF, nomes, senhas ou resultados de exames.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from sst.config import get_settings

_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONFIGURADO = False


def setup_logging() -> None:
    """Idempotente: o Streamlit reexecuta o script a cada interação."""
    global _CONFIGURADO
    if _CONFIGURADO:
        return
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    raiz = logging.getLogger("sst")
    raiz.setLevel(settings.log_level)
    raiz.propagate = False

    if not any(isinstance(h, RotatingFileHandler) for h in raiz.handlers):
        arquivo = RotatingFileHandler(
            settings.log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf-8"
        )
        arquivo.setFormatter(logging.Formatter(_FORMATO))
        raiz.addHandler(arquivo)

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMATO))
        raiz.addHandler(console)

    _CONFIGURADO = True


def get_logger(nome: str) -> logging.Logger:
    if not nome.startswith("sst"):
        nome = f"sst.{nome}"
    return logging.getLogger(nome)
