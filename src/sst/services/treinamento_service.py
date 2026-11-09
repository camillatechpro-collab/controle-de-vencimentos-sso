"""Treinamentos: catálogo (tipos de controle da categoria Treinamento), turmas
com vários colaboradores e consulta dos treinamentos realizados.

Cada participante de uma turma recebe o SEU registro em `vencimentos`
(vencimento, certificado/anexo e renovações individuais). Assim o treinamento
aparece no perfil do colaborador, no painel, nas pendências e nos relatórios,
sem cadastro duplicado: se o colaborador já tem o treinamento ativo, o novo
registro é lançado como RENOVAÇÃO do anterior (histórico preservado).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import func, select

from sst.domain.enums import AcaoAuditoria, AlvoTipo, Categoria, SituacaoVencimento
from sst.domain.exceptions import RegraNegocioError, ValidacaoError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.infra.db.engine import session_scope
from sst.infra.db.models import Colaborador, Fornecedor, TipoControle, TurmaTreinamento, Vencimento
from sst.infra.repositories.base import TenantRepository
from sst.logging_config import get_logger
from sst.schemas.base import validar
from sst.schemas.treinamento import TurmaIn
from sst.schemas.vencimento import VencimentoIn
from sst.services import auditoria_service as auditoria
from sst.services._util import df_de_resultado
from sst.services.base_crud import garantir_do_tenant
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService

log = get_logger(__name__)

TODAS_SITUACOES = [s.value for s in SituacaoVencimento]


class TreinamentoService:
    entidade = "Turma de treinamento"

    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx
        self.venc = VencimentoService(ctx)

    # ------------------------------------------------------------ catálogo
    def catalogo(self) -> pd.DataFrame:
        """Tipos de controle da categoria Treinamento (NRs e demais)."""
        self.ctx.exigir(Permissao.LER)
        stmt = (
            select(
                TipoControle.id, TipoControle.nome, TipoControle.norma_referencia.label("norma"),
                TipoControle.validade_valor, TipoControle.validade_unidade, TipoControle.carga_horaria_padrao,
                TipoControle.antecedencia_dias, TipoControle.exige_anexo, TipoControle.ativo,
            )
            .where(
                TipoControle.tenant_id == self.ctx.tenant_id,
                TipoControle.excluido_em.is_(None),
                TipoControle.categoria == Categoria.TREINAMENTO,
            )
            .order_by(TipoControle.norma_referencia.is_(None), TipoControle.norma_referencia, TipoControle.nome)
        )
        with session_scope() as s:
            return df_de_resultado(s.execute(stmt))

    def opcoes_treinamentos(self) -> dict[int, str]:
        df = self.catalogo()
        if df.empty:
            return {}
        df = df[df["ativo"].astype(bool)]
        return {int(r.id): (f"{r.norma} · " if r.norma else "") + r.nome for r in df.itertuples()}

    # ------------------------------------------------------------ turmas
    def listar_turmas(self, tipo_controle_id: int | None = None, norma: str | None = None) -> pd.DataFrame:
        self.ctx.exigir(Permissao.LER)
        participantes = (
            select(Vencimento.turma_id, func.count(Vencimento.id).label("participantes"))
            .where(
                Vencimento.tenant_id == self.ctx.tenant_id,
                Vencimento.excluido_em.is_(None),
                Vencimento.turma_id.is_not(None),
                Vencimento.situacao != SituacaoVencimento.CANCELADO,
            )
            .group_by(Vencimento.turma_id)
            .subquery()
        )
        stmt = (
            select(
                TurmaTreinamento.id, TurmaTreinamento.data_realizacao, TipoControle.nome.label("treinamento"),
                TipoControle.norma_referencia.label("norma"), TurmaTreinamento.tipo_controle_id,
                TurmaTreinamento.carga_horaria, TurmaTreinamento.instrutor, Fornecedor.razao_social.label("instituicao"),
                TurmaTreinamento.modalidade, TurmaTreinamento.local,
                func.coalesce(participantes.c.participantes, 0).label("participantes"),
            )
            .join(TipoControle, TipoControle.id == TurmaTreinamento.tipo_controle_id)
            .outerjoin(Fornecedor, Fornecedor.id == TurmaTreinamento.instituicao_fornecedor_id)
            .outerjoin(participantes, participantes.c.turma_id == TurmaTreinamento.id)
            .where(TurmaTreinamento.tenant_id == self.ctx.tenant_id, TurmaTreinamento.excluido_em.is_(None))
            .order_by(TurmaTreinamento.data_realizacao.desc(), TurmaTreinamento.id.desc())
        )
        if tipo_controle_id:
            stmt = stmt.where(TurmaTreinamento.tipo_controle_id == tipo_controle_id)
        if norma:
            stmt = stmt.where(TipoControle.norma_referencia.ilike(f"%{norma.strip()}%"))
        with session_scope() as s:
            df = df_de_resultado(s.execute(stmt))
        if self.ctx.restrito_por_unidade and not df.empty:
            # usuário restrito vê só turmas com participante da(s) sua(s) unidade(s)
            visiveis = set(self.listar_realizados()["turma_id"].dropna().astype(int))
            df = df[df["id"].isin(visiveis)].reset_index(drop=True)
        return df

    def participantes(self, turma_id: int) -> pd.DataFrame:
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            TenantRepository(s, TurmaTreinamento, self.ctx.tenant_id, self.entidade).obter_ou_erro(turma_id)
        return self.venc.listar(FiltroVencimentos(turma_id=turma_id, situacoes=TODAS_SITUACOES))

    def _payload(self, turma: dict[str, Any], colaborador_id: int) -> dict[str, Any]:
        return validar(VencimentoIn, {
            "tipo_controle_id": turma["tipo_controle_id"],
            "colaborador_id": colaborador_id,
            "data_emissao": turma["data_realizacao"],
            "numero_documento": turma.get("numero_certificado"),
            "tr_carga_horaria": turma.get("carga_horaria"),
            "tr_instrutor": turma.get("instrutor"),
            "tr_instituicao_fornecedor_id": turma.get("instituicao_fornecedor_id"),
            "tr_modalidade": turma.get("modalidade"),
        })

    def _incluir(self, s, turma: TurmaTreinamento, dados_turma: dict[str, Any], ids: list[int]) -> dict[str, int]:
        tipo = s.get(TipoControle, turma.tipo_controle_id)
        criados = renovados = 0
        duplicados: list[str] = []
        for cid in ids:
            colab = garantir_do_tenant(s, self.ctx, Colaborador, cid, "Colaborador")
            self.ctx.exigir_unidade(colab.unidade_id)
            ativo = s.scalars(
                select(Vencimento).where(
                    Vencimento.tenant_id == self.ctx.tenant_id, Vencimento.excluido_em.is_(None),
                    Vencimento.situacao == SituacaoVencimento.ATIVO,
                    Vencimento.tipo_controle_id == tipo.id, Vencimento.colaborador_id == cid,
                )
            ).first()
            if ativo is not None and (ativo.turma_id == turma.id or ativo.data_emissao == turma.data_realizacao):
                duplicados.append(colab.nome)
                continue
            v = self.venc._criar_interno(s, self._payload(dados_turma, cid), anterior=None, renovar_existente=True)
            v.turma_id = turma.id
            renovados += 1 if v.renovado_de_id else 0
            criados += 0 if v.renovado_de_id else 1
        if duplicados:
            raise RegraNegocioError(
                "Já possuem este treinamento registrado nesta data (evitando duplicidade): "
                + ", ".join(sorted(duplicados)) + ". Remova-os da seleção."
            )
        return {"criados": criados, "renovados": renovados}

    def registrar_turma(self, dados: dict[str, Any], colaboradores_ids: list[int]) -> tuple[int, dict[str, int]]:
        """Cria a turma e o registro individual de cada participante (tudo ou nada)."""
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        ids = sorted({int(i) for i in colaboradores_ids})
        if not ids:
            raise ValidacaoError("Selecione ao menos um colaborador.")
        dados = validar(TurmaIn, dados)
        with session_scope() as s:
            tipo = garantir_do_tenant(s, self.ctx, TipoControle, dados["tipo_controle_id"], "Treinamento")
            if Categoria(tipo.categoria) is not Categoria.TREINAMENTO or AlvoTipo(tipo.alvo_tipo) is not AlvoTipo.COLABORADOR:
                raise RegraNegocioError("Escolha um tipo de controle da categoria Treinamento aplicado a colaboradores.")
            if not tipo.ativo:
                raise RegraNegocioError("Este treinamento está inativo no catálogo.")
            garantir_do_tenant(s, self.ctx, Fornecedor, dados.get("instituicao_fornecedor_id"), "Instituição")
            if dados.get("carga_horaria") is None:
                dados["carga_horaria"] = tipo.carga_horaria_padrao
            turma = TurmaTreinamento(**{k: dados.get(k) for k in (
                "tipo_controle_id", "data_realizacao", "carga_horaria", "instrutor",
                "instituicao_fornecedor_id", "modalidade", "local", "observacoes")})
            TenantRepository(s, TurmaTreinamento, self.ctx.tenant_id).adicionar(turma, self.ctx.usuario_id)
            resultado = self._incluir(s, turma, dados, ids)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.CRIAR, self.entidade, turma.id, None,
                                {**turma.to_dict(), "participantes": ids})
            turma_id = turma.id
        log.info("Turma %s criada: %s por=%s", turma_id, resultado, self.ctx.usuario_id)
        return turma_id, resultado

    def adicionar_participantes(self, turma_id: int, colaboradores_ids: list[int]) -> dict[str, int]:
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        ids = sorted({int(i) for i in colaboradores_ids})
        if not ids:
            raise ValidacaoError("Selecione ao menos um colaborador.")
        with session_scope() as s:
            turma = TenantRepository(s, TurmaTreinamento, self.ctx.tenant_id, self.entidade).obter_ou_erro(turma_id)
            base = turma.to_dict()
            base["numero_certificado"] = None  # certificado é individual: anexe no registro do participante
            resultado = self._incluir(s, turma, base, ids)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.ALTERAR, self.entidade, turma.id, None,
                                {"participantes_adicionados": ids})
        return resultado

    # ------------------------------------------------------------ realizados
    def listar_realizados(self, norma: str | None = None, colaborador_id: int | None = None,
                          setor_id: int | None = None, status: list[str] | None = None,
                          incluir_historico: bool = False) -> pd.DataFrame:
        """Treinamentos por colaborador (vigentes; com histórico se pedido)."""
        situacoes = TODAS_SITUACOES if incluir_historico else [SituacaoVencimento.ATIVO.value]
        return self.venc.listar(FiltroVencimentos(
            categoria=Categoria.TREINAMENTO.value, norma=norma, colaborador_id=colaborador_id,
            setor_id=setor_id, status=status or None, situacoes=situacoes,
        ))

    @staticmethod
    def resumo_por(df: pd.DataFrame, coluna: str) -> pd.DataFrame:
        """Quantidade por status (relatório por NR ou setor)."""
        if df.empty:
            return pd.DataFrame(columns=[coluna, "VENCIDO", "A_VENCER", "VIGENTE", "SEM_VALIDADE", "total"])
        base = df.assign(**{coluna: df[coluna].fillna("(não informado)")})
        tab = pd.crosstab(base[coluna], base["status"])
        for c in ("VENCIDO", "A_VENCER", "VIGENTE", "SEM_VALIDADE"):
            if c not in tab.columns:
                tab[c] = 0
        tab = tab[["VENCIDO", "A_VENCER", "VIGENTE", "SEM_VALIDADE"]]
        tab["total"] = tab.sum(axis=1)
        return tab.reset_index().sort_values(["VENCIDO", "total"], ascending=False).reset_index(drop=True)
