"""Engine, configuração do SQLite e unidade de trabalho (session_scope)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sst.config import get_settings
from sst.domain.exceptions import RegraNegocioError
from sst.logging_config import get_logger

log = get_logger(__name__)


def _configurar_sqlite(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    # SQLite vem com chaves estrangeiras DESLIGADAS por padrão.
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def criar_engine(url: str | None = None, echo: bool = False) -> Engine:
    url = url or get_settings().database_url
    kwargs: dict = {"echo": echo, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" not in url:
            from pathlib import Path

            Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configurar_sqlite)
    return engine


_engine_override: Engine | None = None


@lru_cache(maxsize=1)
def _engine_padrao() -> Engine:
    return criar_engine()


def get_engine() -> Engine:
    return _engine_override or _engine_padrao()


def definir_engine(engine: Engine | None) -> None:
    """Usado por testes para apontar para um banco temporário."""
    global _engine_override, _SessionFactory
    _engine_override = engine
    _SessionFactory = None


_SessionFactory: sessionmaker[Session] | None = None


def _factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        # expire_on_commit=False: objetos continuam legíveis após o commit
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Uma transação por operação de negócio: commit no sucesso, rollback no erro."""
    session = _factory()()
    try:
        yield session
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        log.warning("Violação de integridade: %s", exc.orig)
        raise RegraNegocioError(_traduzir_integridade(str(exc.orig))) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _traduzir_integridade(msg: str) -> str:
    m = msg.lower()
    if "unique" in m:
        return "Já existe um registro com estes dados (valor duplicado)."
    if "foreign key" in m:
        return "Registro vinculado a outros dados: operação não permitida."
    if "check constraint" in m:
        return "Dados inconsistentes para esta operação."
    if "not null" in m:
        return "Campo obrigatório não informado."
    return "Não foi possível gravar os dados (integridade)."


def criar_tabelas(engine: Engine | None = None) -> None:
    from sst.infra.db import migracoes, models  # noqa: F401  (registra os models)
    from sst.infra.db.base import Base

    alvo = engine or get_engine()
    Base.metadata.create_all(alvo)
    migracoes.aplicar(alvo)  # colunas novas em bancos antigos (com backup antes)
