"""Trilha de auditoria (gravação na mesma transação da operação)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from sst.domain.enums import AcaoAuditoria
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.infra.db.base import serializar
from sst.infra.db.engine import session_scope
from sst.infra.db.models import Auditoria
from sst.services._util import df_de_resultado

CAMPOS_IGNORADOS = {"atualizado_em", "criado_em", "atualizado_por_id", "criado_por_id", "senha_hash"}
CAMPOS_MASCARADOS = {"resultado", "ex_resultado"}  # dado de saúde


def _limpar(dados: dict[str, Any] | None) -> dict[str, Any] | None:
    if dados is None:
        return None
    limpo = {}
    for k, v in dados.items():
        if k in CAMPOS_IGNORADOS:
            continue
        limpo[k] = "***" if (k in CAMPOS_MASCARADOS and v is not None) else serializar(v)
    return limpo


def diferenca(antes: dict[str, Any], depois: dict[str, Any]) -> tuple[dict, dict]:
    a, d = _limpar(antes) or {}, _limpar(depois) or {}
    chaves = {k for k in set(a) | set(d) if a.get(k) != d.get(k)}
    return {k: a.get(k) for k in chaves}, {k: d.get(k) for k in chaves}


def registrar(
    s: Session,
    ctx: UsuarioContexto | None,
    acao: AcaoAuditoria,
    entidade: str,
    entidade_id: int | None = None,
    antes: dict[str, Any] | None = None,
    depois: dict[str, Any] | None = None,
    *,
    tenant_id: int | None = None,
    usuario_email: str | None = None,
    usuario_id: int | None = None,
) -> None:
    if acao is AcaoAuditoria.ALTERAR and antes is not None and depois is not None:
        antes, depois = diferenca(antes, depois)
        if not antes and not depois:
            return  # nada mudou
    else:
        antes, depois = _limpar(antes), _limpar(depois)
    s.add(
        Auditoria(
            tenant_id=ctx.tenant_id if ctx else tenant_id,
            usuario_id=ctx.usuario_id if ctx else usuario_id,
            usuario_email=ctx.email if ctx else usuario_email,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            dados_antes=antes,
            dados_depois=depois,
        )
    )


class AuditoriaService:
    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx

    def listar(
        self,
        data_de: date | None = None,
        data_ate: date | None = None,
        entidade: str | None = None,
        acao: str | None = None,
        limite: int = 5000,
    ) -> pd.DataFrame:
        self.ctx.exigir(Permissao.ADMINISTRAR)
        stmt = (
            select(
                Auditoria.id,
                Auditoria.criado_em,
                Auditoria.usuario_email,
                Auditoria.acao,
                Auditoria.entidade,
                Auditoria.entidade_id,
                Auditoria.dados_antes,
                Auditoria.dados_depois,
            )
            .where(Auditoria.tenant_id == self.ctx.tenant_id)
            .order_by(Auditoria.id.desc())
            .limit(limite)
        )
        if data_de:
            stmt = stmt.where(Auditoria.criado_em >= datetime.combine(data_de, time.min))
        if data_ate:
            stmt = stmt.where(Auditoria.criado_em <= datetime.combine(data_ate, time.max))
        if entidade:
            stmt = stmt.where(Auditoria.entidade == entidade)
        if acao:
            stmt = stmt.where(Auditoria.acao == AcaoAuditoria(acao))
        with session_scope() as s:
            df = df_de_resultado(s.execute(stmt))
        if not df.empty:
            df["dados_antes"] = df["dados_antes"].map(lambda d: "" if not d else str(d))
            df["dados_depois"] = df["dados_depois"].map(lambda d: "" if not d else str(d))
        return df
