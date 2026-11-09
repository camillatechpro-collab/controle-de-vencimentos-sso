"""Núcleo do produto: vencimentos (CRUD, renovação, cancelamento, lote, histórico, anexos)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from sst.config import get_settings
from sst.domain import datas
from sst.domain.enums import (
    AcaoAuditoria,
    AlvoTipo,
    Categoria,
    SituacaoVencimento,
    ValidadeUnidade,
)
from sst.domain.exceptions import NaoEncontradoError, RegraNegocioError, ValidacaoError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.domain.status import ORDEM_STATUS, calcular_status, dias_restantes
from sst.infra import armazenamento
from sst.infra.db.engine import session_scope
from sst.infra.db.models import (
    Anexo,
    Colaborador,
    Equipamento,
    Fornecedor,
    Setor,
    TipoControle,
    Unidade,
    Usuario,
    VencContrato,
    VencEquipamento,
    VencExame,
    VencTreinamento,
    Vencimento,
)
from sst.infra.db.models.vencimento import COLUNAS_ALVO
from sst.infra.repositories.base import TenantRepository
from sst.logging_config import get_logger
from sst.schemas.base import validar
from sst.schemas.vencimento import CancelamentoIn, VencimentoIn
from sst.services import auditoria_service as auditoria
from sst.services._util import df_de_resultado
from sst.services.base_crud import garantir_do_tenant

log = get_logger(__name__)

# categoria → (prefixo do formulário, atributo de relacionamento, classe)
EXTENSOES: dict[Categoria, tuple[str, str, type]] = {
    Categoria.TREINAMENTO: ("tr_", "treinamento", VencTreinamento),
    Categoria.EXAME: ("ex_", "exame", VencExame),
    Categoria.CONTRATO: ("ct_", "contrato", VencContrato),
    Categoria.EQUIPAMENTO: ("eq_", "servico_equipamento", VencEquipamento),
}
# campos de extensão que referenciam fornecedores (validar tenant)
_FKS_FORNECEDOR_EXT = {"instituicao_fornecedor_id", "clinica_fornecedor_id", "executor_fornecedor_id"}

ALVO_MODELS: dict[AlvoTipo, tuple[type, str]] = {
    AlvoTipo.COLABORADOR: (Colaborador, "Colaborador"),
    AlvoTipo.EQUIPAMENTO: (Equipamento, "Equipamento"),
    AlvoTipo.UNIDADE: (Unidade, "Unidade"),
    AlvoTipo.FORNECEDOR: (Fornecedor, "Fornecedor"),
}


@dataclass
class FiltroVencimentos:
    categoria: str | None = None
    tipo_controle_id: int | None = None
    unidade_id: int | None = None
    alvo_tipo: str | None = None
    colaborador_id: int | None = None
    equipamento_id: int | None = None
    fornecedor_id: int | None = None
    situacoes: list[str] = field(default_factory=lambda: [SituacaoVencimento.ATIVO.value])
    vencimento_de: date | None = None
    vencimento_ate: date | None = None
    status: list[str] | None = None  # filtrado após o cálculo
    setor_id: int | None = None
    turma_id: int | None = None
    norma: str | None = None  # trecho da norma de referência (ex.: "NR-35")


class VencimentoService:
    entidade = "Vencimento"

    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx

    # ================================================================ helpers
    def _repo(self, s: Session) -> TenantRepository[Vencimento]:
        return TenantRepository(s, Vencimento, self.ctx.tenant_id, "Vencimento")

    def _hoje(self) -> date:
        return datas.hoje(get_settings().timezone)

    def _obter_visivel(self, s: Session, ident: int) -> Vencimento:
        v = self._repo(s).obter_ou_erro(ident)
        self.ctx.exigir_unidade(v.unidade_id)
        return v

    def _separar(self, dados: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        principais: dict[str, Any] = {}
        ext: dict[str, dict[str, Any]] = {p: {} for p, _, _ in EXTENSOES.values()}
        for k, v in dados.items():
            prefixo = k[:3]
            if prefixo in ext:
                ext[prefixo][k[3:]] = v
            else:
                principais[k] = v
        return principais, ext

    def _resolver_alvo(self, s: Session, tipo: TipoControle, dados: dict[str, Any]) -> dict[str, Any]:
        """Preenche apenas a FK de alvo correta, valida tenant e define unidade de escopo."""
        alvo = AlvoTipo(tipo.alvo_tipo)
        coluna = COLUNAS_ALVO[alvo]
        resultado: dict[str, Any] = {c: None for c in COLUNAS_ALVO.values() if c}
        resultado["alvo_tipo"] = alvo
        unidade_escopo: int | None = None
        if coluna:
            ident = dados.get(coluna)
            model, nome = ALVO_MODELS[alvo]
            if not ident:
                raise ValidacaoError(f"{nome}: campo obrigatório para este tipo de controle")
            obj = garantir_do_tenant(s, self.ctx, model, ident, nome)
            resultado[coluna] = ident
            if alvo is AlvoTipo.UNIDADE:
                unidade_escopo = obj.id
            elif alvo in (AlvoTipo.COLABORADOR, AlvoTipo.EQUIPAMENTO):
                unidade_escopo = obj.unidade_id
        resultado["unidade_id"] = unidade_escopo
        self.ctx.exigir_unidade(unidade_escopo)
        return resultado

    def _resolver_datas(self, tipo: TipoControle, dados: dict[str, Any]) -> dict[str, Any]:
        unidade = ValidadeUnidade(tipo.validade_unidade)
        emissao: date | None = dados.get("data_emissao")
        informado: date | None = dados.get("data_vencimento")
        justificativa = dados.get("justificativa_ajuste")

        if unidade is ValidadeUnidade.SEM_VALIDADE:
            return {"data_vencimento": None, "vencimento_ajustado_manual": False, "justificativa_ajuste": None}
        if unidade is ValidadeUnidade.MANUAL:
            if not informado:
                raise ValidacaoError("Data de vencimento: obrigatória para este tipo de controle")
            return {"data_vencimento": informado, "vencimento_ajustado_manual": False, "justificativa_ajuste": None}

        if not emissao:
            raise ValidacaoError("Data de emissão/realização: obrigatória para calcular o vencimento")
        calculado = datas.calcular_vencimento(emissao, tipo.validade_valor, unidade)
        if informado is None or informado == calculado:
            return {"data_vencimento": calculado, "vencimento_ajustado_manual": False, "justificativa_ajuste": None}
        if not justificativa or len(justificativa.strip()) < 5:
            raise ValidacaoError(
                f"Justificativa do ajuste: obrigatória, pois a data informada difere da calculada "
                f"({datas.formatar_data(calculado)})"
            )
        return {"data_vencimento": informado, "vencimento_ajustado_manual": True, "justificativa_ajuste": justificativa}

    def _validar_extensao(self, s: Session, ext: dict[str, Any]) -> None:
        for campo in _FKS_FORNECEDOR_EXT & set(ext):
            garantir_do_tenant(s, self.ctx, Fornecedor, ext.get(campo), "Fornecedor")

    def _ativo_existente(self, s: Session, tipo_id: int, alvo: dict[str, Any], ignorar_id: int | None = None):
        stmt = self._repo(s).select().where(
            Vencimento.tipo_controle_id == tipo_id,
            Vencimento.situacao == SituacaoVencimento.ATIVO,
        )
        for coluna in (c for c in COLUNAS_ALVO.values() if c):
            valor = alvo.get(coluna)
            stmt = stmt.where(getattr(Vencimento, coluna).is_(None) if valor is None else getattr(Vencimento, coluna) == valor)
        if ignorar_id:
            stmt = stmt.where(Vencimento.id != ignorar_id)
        return s.scalars(stmt.limit(1)).first()

    def _aplicar_extensao(self, s: Session, v: Vencimento, categoria: Categoria, ext_todas: dict) -> None:
        if categoria not in EXTENSOES:
            return
        prefixo, atributo, classe = EXTENSOES[categoria]
        ext = dict(ext_todas.get(prefixo, {}))
        self._validar_extensao(s, ext)
        atual = getattr(v, atributo)
        if categoria is Categoria.EXAME and not self.ctx.pode(Permissao.VER_DADOS_SAUDE):
            # sem permissão: nunca grava nem apaga o resultado
            ext.pop("resultado", None)
        if atual is None:
            setattr(v, atributo, classe(**ext))
        else:
            for k, val in ext.items():
                setattr(atual, k, val)

    def _snapshot(self, v: Vencimento) -> dict[str, Any]:
        dados = v.to_dict()
        for _cat, (prefixo, atributo, _cls) in EXTENSOES.items():
            ext = getattr(v, atributo)
            if ext is not None:
                for k, val in ext.to_dict(incluir_sensiveis=True).items():
                    if k != "vencimento_id":
                        dados[prefixo + k] = val
        return dados

    def _criar_interno(
        self, s: Session, dados: dict[str, Any], anterior: Vencimento | None, renovar_existente: bool
    ) -> Vencimento:
        principais, ext = self._separar(dados)
        tipo = garantir_do_tenant(s, self.ctx, TipoControle, principais["tipo_controle_id"], "Tipo de controle")
        if not tipo.ativo:
            raise RegraNegocioError("Este tipo de controle está inativo.")
        alvo = self._resolver_alvo(s, tipo, principais)
        datas_ = self._resolver_datas(tipo, principais)
        garantir_do_tenant(s, self.ctx, Usuario, principais.get("responsavel_usuario_id"), "Usuário")

        existente = anterior or self._ativo_existente(s, tipo.id, alvo)
        if existente is not None and anterior is None and not renovar_existente:
            raise RegraNegocioError(
                f"Já existe um registro ativo de '{tipo.nome}' para este alvo "
                f"(vencimento {datas.formatar_data(existente.data_vencimento) or 'sem data'}). "
                "Use a opção 'Renovar' para manter o histórico."
            )

        v = Vencimento(
            tipo_controle_id=tipo.id,
            numero_documento=principais.get("numero_documento"),
            emissor=principais.get("emissor"),
            data_emissao=principais.get("data_emissao"),
            responsavel_usuario_id=principais.get("responsavel_usuario_id"),
            observacoes=principais.get("observacoes"),
            situacao=SituacaoVencimento.ATIVO,
            renovado_de_id=existente.id if existente is not None else None,
            **alvo,
            **datas_,
        )
        self._aplicar_extensao(s, v, Categoria(tipo.categoria), ext)
        self._repo(s).adicionar(v, self.ctx.usuario_id)

        if existente is not None:
            antes = existente.to_dict()
            existente.situacao = SituacaoVencimento.RENOVADO
            existente.atualizado_por_id = self.ctx.usuario_id
            auditoria.registrar(s, self.ctx, AcaoAuditoria.RENOVAR, self.entidade, existente.id,
                                antes, existente.to_dict())
        auditoria.registrar(s, self.ctx, AcaoAuditoria.CRIAR, self.entidade, v.id, None, self._snapshot(v))
        return v

    # ================================================================ leitura
    def _select_listagem(self) -> Select:
        alvo_un = aliased(Unidade)
        esc_un = aliased(Unidade)
        anexos = (
            select(Anexo.vencimento_id, func.count(Anexo.id).label("qtd"))
            .where(Anexo.tenant_id == self.ctx.tenant_id, Anexo.excluido_em.is_(None))
            .group_by(Anexo.vencimento_id)
            .subquery()
        )
        return (
            select(
                Vencimento.id,
                TipoControle.categoria,
                TipoControle.nome.label("tipo"),
                Vencimento.tipo_controle_id,
                Vencimento.alvo_tipo,
                Colaborador.nome.label("colaborador"),
                Equipamento.descricao.label("equipamento"),
                Equipamento.patrimonio.label("patrimonio"),
                alvo_un.nome.label("alvo_unidade"),
                Fornecedor.razao_social.label("fornecedor"),
                Vencimento.unidade_id,
                esc_un.nome.label("unidade"),
                Vencimento.numero_documento,
                Vencimento.data_emissao,
                Vencimento.data_vencimento,
                Vencimento.situacao,
                Vencimento.renovado_de_id,
                Vencimento.turma_id,
                TipoControle.norma_referencia.label("norma"),
                Colaborador.setor_id,
                Setor.nome.label("setor"),
                TipoControle.antecedencia_dias,
                TipoControle.exige_anexo,
                func.coalesce(anexos.c.qtd, 0).label("anexos"),
            )
            .join(TipoControle, TipoControle.id == Vencimento.tipo_controle_id)
            .outerjoin(Colaborador, Colaborador.id == Vencimento.colaborador_id)
            .outerjoin(Setor, Setor.id == Colaborador.setor_id)
            .outerjoin(Equipamento, Equipamento.id == Vencimento.equipamento_id)
            .outerjoin(alvo_un, alvo_un.id == Vencimento.alvo_unidade_id)
            .outerjoin(Fornecedor, Fornecedor.id == Vencimento.fornecedor_id)
            .outerjoin(esc_un, esc_un.id == Vencimento.unidade_id)
            .outerjoin(anexos, anexos.c.vencimento_id == Vencimento.id)
        )

    def listar(self, filtro: FiltroVencimentos | None = None) -> pd.DataFrame:
        self.ctx.exigir(Permissao.LER)
        f = filtro or FiltroVencimentos()
        stmt = self._repo_select_filtrado(f)
        with session_scope() as s:
            df = df_de_resultado(s.execute(stmt))
        return self._enriquecer(df, f)

    def _repo_select_filtrado(self, f: FiltroVencimentos) -> Select:
        stmt = self._select_listagem().where(
            Vencimento.tenant_id == self.ctx.tenant_id, Vencimento.excluido_em.is_(None)
        )
        if self.ctx.restrito_por_unidade:
            stmt = stmt.where(
                Vencimento.unidade_id.in_(self.ctx.unidades_ids) | Vencimento.unidade_id.is_(None)
            )
        if f.situacoes:
            stmt = stmt.where(Vencimento.situacao.in_([SituacaoVencimento(x) for x in f.situacoes]))
        if f.categoria:
            stmt = stmt.where(TipoControle.categoria == Categoria(f.categoria))
        if f.tipo_controle_id:
            stmt = stmt.where(Vencimento.tipo_controle_id == f.tipo_controle_id)
        if f.unidade_id:
            stmt = stmt.where(Vencimento.unidade_id == f.unidade_id)
        if f.alvo_tipo:
            stmt = stmt.where(Vencimento.alvo_tipo == AlvoTipo(f.alvo_tipo))
        if f.colaborador_id:
            stmt = stmt.where(Vencimento.colaborador_id == f.colaborador_id)
        if f.equipamento_id:
            stmt = stmt.where(Vencimento.equipamento_id == f.equipamento_id)
        if f.fornecedor_id:
            stmt = stmt.where(Vencimento.fornecedor_id == f.fornecedor_id)
        if f.setor_id:
            stmt = stmt.where(Colaborador.setor_id == f.setor_id)
        if f.turma_id:
            stmt = stmt.where(Vencimento.turma_id == f.turma_id)
        if f.norma:
            stmt = stmt.where(TipoControle.norma_referencia.ilike(f"%{f.norma.strip()}%"))
        if f.vencimento_de:
            stmt = stmt.where(Vencimento.data_vencimento >= f.vencimento_de)
        if f.vencimento_ate:
            stmt = stmt.where(Vencimento.data_vencimento <= f.vencimento_ate)
        return stmt.order_by(Vencimento.data_vencimento.is_(None), Vencimento.data_vencimento)

    def _enriquecer(self, df: pd.DataFrame, f: FiltroVencimentos) -> pd.DataFrame:
        extras = ["alvo", "status", "dias_restantes", "pendente_anexo"]
        if df.empty:
            return df.reindex(columns=list(df.columns) + extras)
        hoje = self._hoje()

        def _alvo(r) -> str:
            alvo = r["alvo_tipo"]
            if alvo == AlvoTipo.COLABORADOR.value:
                return r["colaborador"] or ""
            if alvo == AlvoTipo.EQUIPAMENTO.value:
                pat = f" (Pat. {r['patrimonio']})" if r["patrimonio"] else ""
                return f"{r['equipamento'] or ''}{pat}"
            if alvo == AlvoTipo.UNIDADE.value:
                return r["alvo_unidade"] or ""
            if alvo == AlvoTipo.FORNECEDOR.value:
                return r["fornecedor"] or ""
            return "Empresa"

        def _dv(x):
            return None if x is None or (not isinstance(x, date) and pd.isna(x)) else x

        df["alvo"] = df.apply(_alvo, axis=1)
        df["status"] = [
            calcular_status(_dv(dv), sit, int(ant), hoje).value
            for dv, sit, ant in zip(df["data_vencimento"], df["situacao"], df["antecedencia_dias"], strict=True)
        ]
        df["dias_restantes"] = [dias_restantes(_dv(dv), hoje) for dv in df["data_vencimento"]]
        df["dias_restantes"] = df["dias_restantes"].astype("Int64")
        df["pendente_anexo"] = df["exige_anexo"].astype(bool) & (df["anexos"].astype(int) == 0)
        if f.status:
            df = df[df["status"].isin(f.status)]
        df["_ordem"] = df["status"].map(lambda st: ORDEM_STATUS.get(st, 9))
        df = df.sort_values(["_ordem", "data_vencimento"], na_position="last", kind="stable")
        return df.drop(columns=["_ordem"]).reset_index(drop=True)

    def obter(self, ident: int) -> dict[str, Any]:
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            v = self._obter_visivel(s, ident)
            tipo = s.get(TipoControle, v.tipo_controle_id)
            dados = self._snapshot(v)
            dados["categoria"] = tipo.categoria.value
            dados["tipo_nome"] = tipo.nome
            dados["status"] = calcular_status(v.data_vencimento, v.situacao, tipo.antecedencia_dias, self._hoje()).value
            dados["resultado_oculto"] = False
            if "ex_resultado" in dados and dados["ex_resultado"] is not None:
                if self.ctx.pode(Permissao.VER_DADOS_SAUDE):
                    auditoria.registrar(s, self.ctx, AcaoAuditoria.VISUALIZAR_SENSIVEL, self.entidade, v.id)
                else:
                    dados["ex_resultado"] = None
                    dados["resultado_oculto"] = True
            return dados

    def historico(self, ident: int) -> pd.DataFrame:
        """Cadeia completa de renovações do item (mais antigo → mais recente)."""
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            repo = self._repo(s)
            atual = self._obter_visivel(s, ident)
            # volta até a raiz
            cadeia = [atual]
            while cadeia[0].renovado_de_id:
                ant = repo.obter(cadeia[0].renovado_de_id, incluir_excluidos=True)
                if ant is None or ant in cadeia:
                    break
                cadeia.insert(0, ant)
            # avança até o mais recente
            while True:
                prox = s.scalars(
                    repo.select(incluir_excluidos=False).where(Vencimento.renovado_de_id == cadeia[-1].id)
                ).first()
                if prox is None or prox in cadeia:
                    break
                cadeia.append(prox)
            linhas = [
                {
                    "id": v.id,
                    "numero_documento": v.numero_documento,
                    "data_emissao": v.data_emissao,
                    "data_vencimento": v.data_vencimento,
                    "situacao": v.situacao.value,
                    "excluido": v.excluido_em is not None,
                    "motivo_cancelamento": v.motivo_cancelamento,
                }
                for v in cadeia
            ]
        return pd.DataFrame(linhas)

    # ================================================================ escrita
    def criar(self, dados: dict[str, Any], renovar_existente: bool = False) -> int:
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        dados = validar(VencimentoIn, dados)
        with session_scope() as s:
            v = self._criar_interno(s, dados, anterior=None, renovar_existente=renovar_existente)
            novo = v.id
        log.info("Vencimento criado id=%s tenant=%s por=%s", novo, self.ctx.tenant_id, self.ctx.usuario_id)
        return novo

    def renovar(self, ident: int, dados: dict[str, Any]) -> int:
        """Cria o novo registro e marca o atual como RENOVADO (histórico preservado)."""
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        with session_scope() as s:
            atual = self._obter_visivel(s, ident)
            if atual.situacao is not SituacaoVencimento.ATIVO:
                raise RegraNegocioError("Somente registros ativos podem ser renovados.")
            # tipo e alvo são herdados do registro renovado
            dados = dict(dados)
            dados["tipo_controle_id"] = atual.tipo_controle_id
            for coluna in (c for c in COLUNAS_ALVO.values() if c):
                dados[coluna] = getattr(atual, coluna)
            dados = validar(VencimentoIn, dados)
            novo = self._criar_interno(s, dados, anterior=atual, renovar_existente=True)
            novo_id = novo.id
        log.info("Vencimento %s renovado → %s por=%s", ident, novo_id, self.ctx.usuario_id)
        return novo_id

    def atualizar(self, ident: int, dados: dict[str, Any]) -> None:
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        with session_scope() as s:
            v = self._obter_visivel(s, ident)
            if v.situacao is not SituacaoVencimento.ATIVO:
                raise RegraNegocioError("Registros renovados ou cancelados não podem ser editados.")
            dados = dict(dados)
            if int(dados.get("tipo_controle_id") or v.tipo_controle_id) != v.tipo_controle_id:
                raise RegraNegocioError(
                    "Não é possível trocar o tipo de controle de um registro. Cancele-o e lance um novo."
                )
            dados["tipo_controle_id"] = v.tipo_controle_id
            for coluna in (c for c in COLUNAS_ALVO.values() if c):
                novo_valor = dados.get(coluna)
                if novo_valor not in (None, getattr(v, coluna)):
                    raise RegraNegocioError("Não é possível trocar o alvo de um registro. Cancele-o e lance um novo.")
                dados[coluna] = getattr(v, coluna)
            dados = validar(VencimentoIn, dados)
            principais, ext = self._separar(dados)
            tipo = s.get(TipoControle, v.tipo_controle_id)
            antes = self._snapshot(v)
            datas_ = self._resolver_datas(tipo, principais)
            garantir_do_tenant(s, self.ctx, Usuario, principais.get("responsavel_usuario_id"), "Usuário")
            for campo in ("numero_documento", "emissor", "data_emissao", "responsavel_usuario_id", "observacoes"):
                setattr(v, campo, principais.get(campo))
            for campo, valor in datas_.items():
                setattr(v, campo, valor)
            v.atualizado_por_id = self.ctx.usuario_id
            self._aplicar_extensao(s, v, Categoria(tipo.categoria), ext)
            s.flush()
            auditoria.registrar(s, self.ctx, AcaoAuditoria.ALTERAR, self.entidade, v.id, antes, self._snapshot(v))

    def _reativar_anterior(self, s: Session, v: Vencimento) -> None:
        """Ao cancelar/excluir uma renovação, o registro anterior volta a ser o vigente."""
        if not v.renovado_de_id:
            return
        anterior = self._repo(s).obter(v.renovado_de_id)
        if anterior is not None and anterior.situacao is SituacaoVencimento.RENOVADO:
            antes = anterior.to_dict()
            anterior.situacao = SituacaoVencimento.ATIVO
            auditoria.registrar(s, self.ctx, AcaoAuditoria.ALTERAR, self.entidade, anterior.id,
                                antes, anterior.to_dict())

    def cancelar(self, ident: int, motivo: str) -> None:
        self.ctx.exigir(Permissao.CANCELAR_VENCIMENTOS)
        motivo = validar(CancelamentoIn, {"motivo": motivo})["motivo"]
        with session_scope() as s:
            v = self._obter_visivel(s, ident)
            if v.situacao is not SituacaoVencimento.ATIVO:
                raise RegraNegocioError("Somente registros ativos podem ser cancelados.")
            antes = v.to_dict()
            v.situacao = SituacaoVencimento.CANCELADO
            v.motivo_cancelamento = motivo
            v.atualizado_por_id = self.ctx.usuario_id
            self._reativar_anterior(s, v)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.CANCELAR, self.entidade, v.id, antes, v.to_dict())

    def excluir(self, ident: int) -> None:
        self.ctx.exigir(Permissao.CANCELAR_VENCIMENTOS)
        with session_scope() as s:
            v = self._obter_visivel(s, ident)
            if v.situacao is SituacaoVencimento.RENOVADO:
                raise RegraNegocioError("Registros que já foram renovados fazem parte do histórico e não podem ser excluídos.")
            if v.situacao is SituacaoVencimento.ATIVO:
                self._reativar_anterior(s, v)
            self._repo(s).excluir_logico(v, self.ctx.usuario_id)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.EXCLUIR, self.entidade, v.id, v.to_dict(), None)

    def criar_lote(self, tipo_controle_id: int, colaboradores_ids: list[int], dados_comuns: dict[str, Any]) -> dict[str, int]:
        """Lança o mesmo treinamento/exame para vários colaboradores (tudo ou nada).
        Registros ativos existentes são renovados automaticamente."""
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        ids = sorted(set(int(i) for i in colaboradores_ids))
        if not ids:
            raise ValidacaoError("Selecione ao menos um colaborador.")
        criados = renovados = 0
        with session_scope() as s:
            tipo = garantir_do_tenant(s, self.ctx, TipoControle, tipo_controle_id, "Tipo de controle")
            if tipo.alvo_tipo != AlvoTipo.COLABORADOR:
                raise RegraNegocioError("Lançamento em lote disponível apenas para tipos aplicados a colaboradores.")
            for cid in ids:
                payload = dict(dados_comuns, tipo_controle_id=tipo_controle_id, colaborador_id=cid)
                payload = validar(VencimentoIn, payload)
                v = self._criar_interno(s, payload, anterior=None, renovar_existente=True)
                if v.renovado_de_id:
                    renovados += 1
                else:
                    criados += 1
        log.info("Lote tipo=%s: %s criados, %s renovados por=%s", tipo_controle_id, criados, renovados, self.ctx.usuario_id)
        return {"criados": criados, "renovados": renovados}

    # ================================================================ anexos
    def listar_anexos(self, vencimento_id: int) -> pd.DataFrame:
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            self._obter_visivel(s, vencimento_id)
            stmt = (
                select(Anexo.id, Anexo.nome_original, Anexo.mime_type, Anexo.tamanho_bytes, Anexo.criado_em)
                .where(
                    Anexo.tenant_id == self.ctx.tenant_id,
                    Anexo.vencimento_id == vencimento_id,
                    Anexo.excluido_em.is_(None),
                )
                .order_by(Anexo.id)
            )
            return df_de_resultado(s.execute(stmt))

    def anexar(self, vencimento_id: int, nome_original: str, conteudo: bytes) -> int:
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        nome = armazenamento.nome_seguro(nome_original)
        arquivo = None
        try:
            with session_scope() as s:
                self._obter_visivel(s, vencimento_id)
                arquivo = armazenamento.salvar(self.ctx.tenant_id, nome, conteudo)
                anexo = Anexo(
                    vencimento_id=vencimento_id,
                    nome_original=nome,
                    caminho_relativo=arquivo.caminho_relativo,
                    mime_type=arquivo.mime_type,
                    tamanho_bytes=arquivo.tamanho_bytes,
                    sha256=arquivo.sha256,
                )
                TenantRepository(s, Anexo, self.ctx.tenant_id).adicionar(anexo, self.ctx.usuario_id)
                auditoria.registrar(s, self.ctx, AcaoAuditoria.ANEXAR, "Anexo", anexo.id, None,
                                    {"vencimento_id": vencimento_id, "nome": nome, "sha256": arquivo.sha256})
                anexo_id = anexo.id
        except Exception:
            if arquivo is not None:  # banco falhou: não deixa arquivo órfão
                armazenamento.remover(arquivo.caminho_relativo)
            raise
        return anexo_id

    def baixar_anexo(self, anexo_id: int) -> tuple[str, str, bytes]:
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            anexo = TenantRepository(s, Anexo, self.ctx.tenant_id, "Anexo").obter_ou_erro(anexo_id)
            self._obter_visivel(s, anexo.vencimento_id)
            conteudo = armazenamento.ler(anexo.caminho_relativo, anexo.sha256)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.BAIXAR_ANEXO, "Anexo", anexo.id)
            return anexo.nome_original, anexo.mime_type, conteudo

    def excluir_anexo(self, anexo_id: int) -> None:
        self.ctx.exigir(Permissao.EDITAR_VENCIMENTOS)
        with session_scope() as s:
            repo = TenantRepository(s, Anexo, self.ctx.tenant_id, "Anexo")
            anexo = repo.obter_ou_erro(anexo_id)
            self._obter_visivel(s, anexo.vencimento_id)
            repo.excluir_logico(anexo, self.ctx.usuario_id)  # arquivo físico mantido (recuperável)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.EXCLUIR, "Anexo", anexo.id, anexo.to_dict(), None)

    # ================================================================ util
    def existe(self, ident: int) -> bool:
        try:
            self.obter(ident)
            return True
        except NaoEncontradoError:
            return False
