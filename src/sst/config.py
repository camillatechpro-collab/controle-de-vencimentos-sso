"""Configuração central da aplicação (lida de variáveis de ambiente / .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto: .../controle_vencimentos_sst
BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


def _int(nome: str, padrao: int) -> int:
    valor = os.getenv(nome)
    if valor is None or valor.strip() == "":
        return padrao
    try:
        return int(valor)
    except ValueError as exc:  # configuração inválida deve falhar cedo
        raise RuntimeError(f"Variável {nome} deve ser um número inteiro (valor: {valor!r}).") from exc


def _path(nome: str, padrao: str) -> Path:
    p = Path(os.getenv(nome, padrao))
    return p if p.is_absolute() else BASE_DIR / p


def _database_url() -> str:
    url = os.getenv("SST_DATABASE_URL", "sqlite:///data/sst.db")
    # Caminho relativo de SQLite é resolvido a partir da raiz do projeto,
    # não do diretório onde o comando foi executado.
    prefixo = "sqlite:///"
    if url.startswith(prefixo) and not url.startswith("sqlite:////") and ":memory:" not in url:
        caminho = Path(url[len(prefixo):])
        if not caminho.is_absolute():
            url = prefixo + str((BASE_DIR / caminho).resolve())
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    anexos_dir: Path
    log_dir: Path
    log_level: str
    timezone: str
    sessao_timeout_min: int
    login_max_tentativas: int
    login_bloqueio_min: int
    anexo_max_mb: int
    cnpj_api_url: str = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    cnpj_api_timeout: int = 8
    cpf_provedor: str = ""

    @property
    def anexo_max_bytes(self) -> int:
        return self.anexo_max_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=_database_url(),
        anexos_dir=_path("SST_ANEXOS_DIR", "data/anexos"),
        log_dir=_path("SST_LOG_DIR", "logs"),
        log_level=os.getenv("SST_LOG_LEVEL", "INFO").upper(),
        timezone=os.getenv("SST_TIMEZONE", "America/Sao_Paulo"),
        sessao_timeout_min=_int("SST_SESSAO_TIMEOUT_MIN", 30),
        login_max_tentativas=_int("SST_LOGIN_MAX_TENTATIVAS", 5),
        login_bloqueio_min=_int("SST_LOGIN_BLOQUEIO_MIN", 15),
        anexo_max_mb=_int("SST_ANEXO_MAX_MB", 10),
        cnpj_api_url=os.getenv("SST_CNPJ_API_URL", "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"),
        cnpj_api_timeout=_int("SST_CNPJ_API_TIMEOUT", 8),
        cpf_provedor=os.getenv("SST_CPF_PROVEDOR", "").strip(),
    )
