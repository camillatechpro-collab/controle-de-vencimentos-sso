"""Migrações aditivas e idempotentes do esquema (bancos criados por versões anteriores).

`create_all` cria tabelas novas, mas não acrescenta colunas em tabelas existentes.
Aqui só se ACRESCENTAM colunas anuláveis: nenhum dado é alterado ou removido.
Antes de alterar um banco SQLite em arquivo, é feita uma cópia de segurança em
<pasta do banco>/backups/sst-antes-migracao-<data>.db.

Observação: a coluna `cargos.cbo` saiu das telas, mas continua no banco, com os
dados preservados.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, inspect, text

from sst.logging_config import get_logger

log = get_logger(__name__)

# (tabela, coluna, definição SQL)
COLUNAS_NOVAS: list[tuple[str, str, str]] = [
    ("unidades", "razao_social", "VARCHAR(200)"),
    ("unidades", "nome_fantasia", "VARCHAR(200)"),
    ("unidades", "cep", "VARCHAR(8)"),
    ("unidades", "cnae", "VARCHAR(255)"),
    ("unidades", "situacao_cadastral", "VARCHAR(60)"),
    ("fornecedores", "nome_fantasia", "VARCHAR(200)"),
    ("fornecedores", "cep", "VARCHAR(8)"),
    ("fornecedores", "cnae", "VARCHAR(255)"),
    ("fornecedores", "situacao_cadastral", "VARCHAR(60)"),
    ("fornecedores", "endereco", "VARCHAR(255)"),
    ("fornecedores", "cidade", "VARCHAR(100)"),
    ("fornecedores", "uf", "VARCHAR(2)"),
    ("vencimentos", "turma_id", "INTEGER REFERENCES turmas_treinamento (id)"),
]

INDICES_NOVOS: list[tuple[str, str]] = [
    ("ix_vencimentos_turma_id", "CREATE INDEX IF NOT EXISTS ix_vencimentos_turma_id ON vencimentos (turma_id)"),
]


def pendentes(engine: Engine) -> list[tuple[str, str, str]]:
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    faltando = []
    for tabela, coluna, ddl in COLUNAS_NOVAS:
        if tabela in tabelas and coluna not in {c["name"] for c in insp.get_columns(tabela)}:
            faltando.append((tabela, coluna, ddl))
    return faltando


def _backup_sqlite(engine: Engine) -> Path | None:
    caminho = engine.url.database
    if engine.url.get_backend_name() != "sqlite" or not caminho or caminho == ":memory:":
        return None
    origem = Path(caminho)
    if not origem.exists():
        return None
    destino_dir = origem.parent / "backups"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"sst-antes-migracao-{datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(origem) as src, sqlite3.connect(destino) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Falha na verificação do backup antes da migração; nada foi alterado.")
    return destino


def aplicar(engine: Engine) -> list[str]:
    """Aplica as migrações pendentes. Retorna a lista do que foi feito."""
    faltando = pendentes(engine)
    feito: list[str] = []
    if faltando:
        copia = _backup_sqlite(engine)
        if copia:
            log.info("Backup antes da migração: %s", copia)
        with engine.begin() as con:
            for tabela, coluna, ddl in faltando:
                con.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {ddl}"))
                feito.append(f"{tabela}.{coluna}")
        log.info("Migração aplicada: %s", ", ".join(feito))
    with engine.begin() as con:
        for _, ddl in INDICES_NOVOS:
            con.execute(text(ddl))
    return feito
