"""Matriz de requisitos por cargo e cálculo de pendências/conformidade."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import delete, select

from sst.config import get_settings
from sst.domain import datas
from sst.domain.enums import (
    AcaoAuditoria,
    AlvoTipo,
    SituacaoColaborador,
    SituacaoVencimento,
    StatusVencimento,
)
from sst.domain.exceptions import RegraNegocioError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.domain.status import calcular_status
from sst.infra.db.engine import session_scope
from sst.infra.db.models import (
    Cargo,
    Colaborador,
    RequisitoCargo,
    TipoControle,
    Unidade,
    Vencimento,
)
from sst.services import auditoria_service as auditoria
from sst.services._util import df_de_resultado
from sst.services.base_crud import garantir_do_tenant


class ConformidadeService:
    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx

    # --------------------------------------------------------- matriz
    def matriz(self) -> pd.DataFrame:
        self.ctx.exigir(Permissao.LER)
        stmt = (
            select(
                RequisitoCargo.id,
                RequisitoCargo.cargo_id,
                Cargo.nome.label("cargo"),
                RequisitoCargo.tipo_controle_id,
                TipoControle.nome.label("tipo"),
                TipoControle.categoria,
            )
            .join(Cargo, Cargo.id == RequisitoCargo.cargo_id)
            .join(TipoControle, TipoControle.id == RequisitoCargo.tipo_controle_id)
            .where(
                RequisitoCargo.tenant_id == self.ctx.tenant_id,
                Cargo.excluido_em.is_(None),
                TipoControle.excluido_em.is_(None),
            )
            .order_by(Cargo.nome, TipoControle.nome)
        )
        with session_scope() as s:
            return df_de_resultado(s.execute(stmt))

    def requisitos_do_cargo(self, cargo_id: int) -> list[int]:
        df = self.matriz()
        return [] if df.empty else df.loc[df["cargo_id"] == cargo_id, "tipo_controle_id"].astype(int).tolist()

    def definir_requisitos(self, cargo_id: int, tipos_ids: list[int]) -> None:
        self.ctx.exigir(Permissao.GERENCIAR_CATALOGO)
        tipos_ids = sorted(set(int(t) for t in tipos_ids))
        with session_scope() as s:
            garantir_do_tenant(s, self.ctx, Cargo, cargo_id, "Cargo")
            for tid in tipos_ids:
                tipo = garantir_do_tenant(s, self.ctx, TipoControle, tid, "Tipo de controle")
                if tipo.alvo_tipo != AlvoTipo.COLABORADOR:
                    raise RegraNegocioError(
                        f"'{tipo.nome}' não se aplica a colaboradores e não pode ser exigido por cargo."
                    )
            antes = list(
                s.scalars(
                    select(RequisitoCargo.tipo_controle_id).where(
                        RequisitoCargo.tenant_id == self.ctx.tenant_id,
                        RequisitoCargo.cargo_id == cargo_id,
                    )
                )
            )
            s.execute(
                delete(RequisitoCargo).where(
                    RequisitoCargo.tenant_id == self.ctx.tenant_id, RequisitoCargo.cargo_id == cargo_id
                )
            )
            for tid in tipos_ids:
                s.add(
                    RequisitoCargo(
                        tenant_id=self.ctx.tenant_id,
                        cargo_id=cargo_id,
                        tipo_controle_id=tid,
                        criado_por_id=self.ctx.usuario_id,
                    )
                )
            auditoria.registrar(
                s, self.ctx, AcaoAuditoria.ALTERAR, "Requisitos do cargo", cargo_id,
                {"tipos": sorted(antes)}, {"tipos": tipos_ids},
            )

    # --------------------------------------------------------- pendências
    def situacao_exigencias(self, unidade_id: int | None = None) -> pd.DataFrame:
        """Uma linha por (colaborador ativo × tipo exigido pelo cargo) com a situação."""
        self.ctx.exigir(Permissao.LER)
        tid = self.ctx.tenant_id
        hoje = datas.hoje(get_settings().timezone)

        colab_stmt = (
            select(
                Colaborador.id.label("colaborador_id"),
                Colaborador.nome.label("colaborador"),
                Colaborador.matricula,
                Colaborador.cargo_id,
                Cargo.nome.label("cargo"),
                Colaborador.unidade_id,
                Unidade.nome.label("unidade"),
            )
            .join(Cargo, Cargo.id == Colaborador.cargo_id)
            .join(Unidade, Unidade.id == Colaborador.unidade_id)
            .where(
                Colaborador.tenant_id == tid,
                Colaborador.excluido_em.is_(None),
                Colaborador.situacao == SituacaoColaborador.ATIVO,
            )
        )
        if self.ctx.restrito_por_unidade:
            colab_stmt = colab_stmt.where(Colaborador.unidade_id.in_(self.ctx.unidades_ids))
        if unidade_id:
            colab_stmt = colab_stmt.where(Colaborador.unidade_id == unidade_id)

        req_stmt = (
            select(
                RequisitoCargo.cargo_id,
                RequisitoCargo.tipo_controle_id,
                TipoControle.nome.label("tipo"),
                TipoControle.categoria,
                TipoControle.antecedencia_dias,
            )
            .join(TipoControle, TipoControle.id == RequisitoCargo.tipo_controle_id)
            .where(
                RequisitoCargo.tenant_id == tid,
                RequisitoCargo.obrigatorio.is_(True),
                TipoControle.excluido_em.is_(None),
                TipoControle.ativo.is_(True),
            )
        )
        venc_stmt = select(
            Vencimento.colaborador_id,
            Vencimento.tipo_controle_id,
            Vencimento.id.label("vencimento_id"),
            Vencimento.data_vencimento,
        ).where(
            Vencimento.tenant_id == tid,
            Vencimento.excluido_em.is_(None),
            Vencimento.situacao == SituacaoVencimento.ATIVO,
            Vencimento.colaborador_id.is_not(None),
        )
        with session_scope() as s:
            colabs = df_de_resultado(s.execute(colab_stmt))
            reqs = df_de_resultado(s.execute(req_stmt))
            vencs = df_de_resultado(s.execute(venc_stmt))

        colunas = [
            "colaborador_id", "colaborador", "matricula", "unidade", "cargo", "tipo_controle_id",
            "tipo", "categoria", "vencimento_id", "data_vencimento", "status", "atendido",
        ]
        if colabs.empty or reqs.empty:
            return pd.DataFrame(columns=colunas)

        base = colabs.merge(reqs, on="cargo_id", how="inner")
        if vencs.empty:
            base["vencimento_id"] = None
            base["data_vencimento"] = None
        else:
            # Se houver mais de um ativo (não deveria), usa o de vencimento mais distante
            vencs = vencs.sort_values("data_vencimento", na_position="first").drop_duplicates(
                ["colaborador_id", "tipo_controle_id"], keep="last"
            )
            base = base.merge(vencs, on=["colaborador_id", "tipo_controle_id"], how="left")

        def _status(row) -> str:
            if pd.isna(row["vencimento_id"]):
                return "SEM_REGISTRO"
            dv = row["data_vencimento"]
            dv = None if dv is None or pd.isna(dv) else dv
            return calcular_status(dv, SituacaoVencimento.ATIVO, int(row["antecedencia_dias"]), hoje).value

        base["status"] = base.apply(_status, axis=1)
        base["atendido"] = ~base["status"].isin(["SEM_REGISTRO", StatusVencimento.VENCIDO.value])
        return base[colunas].sort_values(["atendido", "colaborador", "tipo"]).reset_index(drop=True)

    def pendencias(self, unidade_id: int | None = None) -> pd.DataFrame:
        df = self.situacao_exigencias(unidade_id)
        return df[~df["atendido"]].reset_index(drop=True) if not df.empty else df

    def indice_conformidade(self, unidade_id: int | None = None) -> tuple[float | None, int, int]:
        """(percentual, atendidas, total). None quando não há exigências cadastradas."""
        df = self.situacao_exigencias(unidade_id)
        total = len(df)
        if total == 0:
            return None, 0, 0
        atendidas = int(df["atendido"].sum())
        return round(100 * atendidas / total, 1), atendidas, total
