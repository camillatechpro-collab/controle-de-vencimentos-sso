"""Cadastros: unidades, setores, cargos, fornecedores, colaboradores e equipamentos."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from sst.domain.enums import SituacaoColaborador, SituacaoVencimento
from sst.domain.exceptions import RegraNegocioError
from sst.domain.permissoes import Permissao
from sst.infra.db.engine import session_scope
from sst.infra.db.models import (
    Cargo,
    Colaborador,
    Equipamento,
    Fornecedor,
    Setor,
    Unidade,
    Vencimento,
)
from sst.schemas.cadastros import (
    CargoIn,
    ColaboradorIn,
    EquipamentoIn,
    FornecedorIn,
    SetorIn,
    UnidadeIn,
)
from sst.services.base_crud import CrudService, garantir_do_tenant


def _contar(s: Session, *condicoes: Any) -> int:
    stmt = select(func.count()).select_from(Vencimento)
    for c in condicoes:
        stmt = stmt.where(c)
    return s.scalar(stmt) or 0


def _vencimentos_ativos(s: Session, tenant_id: int, coluna, ident: int) -> int:
    return _contar(
        s,
        Vencimento.tenant_id == tenant_id,
        coluna == ident,
        Vencimento.excluido_em.is_(None),
        Vencimento.situacao == SituacaoVencimento.ATIVO,
    )


def _contar_model(s: Session, model, *condicoes: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.excluido_em.is_(None))
    for c in condicoes:
        stmt = stmt.where(c)
    return s.scalar(stmt) or 0


def consultar_cnpj_publico(ctx, cnpj: str) -> dict:
    """Consulta dados cadastrais públicos do CNPJ (só para quem edita cadastros)."""
    from sst.infra.consulta_cnpj import consultar_cnpj

    ctx.exigir(Permissao.EDITAR_CADASTROS)
    return consultar_cnpj(cnpj).como_dict()


# ============================================================== UNIDADES
class UnidadeService(CrudService[Unidade]):
    model = Unidade
    schema = UnidadeIn
    entidade = "Unidade"
    campo_unidade = "id"
    campos_unicos = {"nome": "nome"}

    def _validar_exclusao(self, s: Session, obj: Unidade) -> None:
        if _contar_model(s, Colaborador, Colaborador.unidade_id == obj.id):
            raise RegraNegocioError("Unidade possui colaboradores vinculados. Transfira-os antes de excluir.")
        if _contar_model(s, Equipamento, Equipamento.unidade_id == obj.id):
            raise RegraNegocioError("Unidade possui equipamentos vinculados.")
        if _vencimentos_ativos(s, self.ctx.tenant_id, Vencimento.alvo_unidade_id, obj.id):
            raise RegraNegocioError("Unidade possui vencimentos ativos.")


# ============================================================== SETORES
class SetorService(CrudService[Setor]):
    model = Setor
    schema = SetorIn
    entidade = "Setor"
    campo_unidade = "unidade_id"

    def _select_listagem(self) -> Select:
        return select(
            Setor.id, Setor.nome, Setor.unidade_id, Unidade.nome.label("unidade"), Setor.ativo
        ).join(Unidade, Unidade.id == Setor.unidade_id)

    def _validar_regras(self, s: Session, dados: dict[str, Any], atual: Setor | None) -> None:
        garantir_do_tenant(s, self.ctx, Unidade, dados["unidade_id"], "Unidade")
        repo = self._repo(s)
        if repo.existe(
            incluir_excluidos=True,
            excluir_id=atual.id if atual else None,
            unidade_id=dados["unidade_id"],
            nome=dados["nome"],
        ):
            raise RegraNegocioError("Já existe um setor com este nome nesta unidade.")

    def _validar_exclusao(self, s: Session, obj: Setor) -> None:
        if _contar_model(s, Colaborador, Colaborador.setor_id == obj.id):
            raise RegraNegocioError("Setor possui colaboradores vinculados.")


# ============================================================== CARGOS
class CargoService(CrudService[Cargo]):
    model = Cargo
    schema = CargoIn
    entidade = "Cargo"
    campos_unicos = {"nome": "nome"}

    def _validar_exclusao(self, s: Session, obj: Cargo) -> None:
        if _contar_model(s, Colaborador, Colaborador.cargo_id == obj.id):
            raise RegraNegocioError("Cargo possui colaboradores vinculados.")


# ============================================================== FORNECEDORES
class FornecedorService(CrudService[Fornecedor]):
    model = Fornecedor
    schema = FornecedorIn
    entidade = "Fornecedor"
    campo_rotulo = "razao_social"
    campos_unicos = {"cnpj": "CNPJ"}

    def _validar_exclusao(self, s: Session, obj: Fornecedor) -> None:
        if _vencimentos_ativos(s, self.ctx.tenant_id, Vencimento.fornecedor_id, obj.id):
            raise RegraNegocioError("Fornecedor possui vencimentos (contratos) ativos.")


# ============================================================== COLABORADORES
class ColaboradorService(CrudService[Colaborador]):
    model = Colaborador
    schema = ColaboradorIn
    entidade = "Colaborador"
    campo_unidade = "unidade_id"
    campos_unicos = {"cpf": "CPF"}

    def _select_listagem(self) -> Select:
        return (
            select(
                Colaborador.id,
                Colaborador.nome,
                Colaborador.cpf,
                Colaborador.matricula,
                Colaborador.unidade_id,
                Unidade.nome.label("unidade"),
                Colaborador.setor_id,
                Setor.nome.label("setor"),
                Cargo.nome.label("cargo"),
                Colaborador.data_admissao,
                Colaborador.situacao,
                Colaborador.email,
            )
            .join(Unidade, Unidade.id == Colaborador.unidade_id)
            .outerjoin(Setor, Setor.id == Colaborador.setor_id)
            .outerjoin(Cargo, Cargo.id == Colaborador.cargo_id)
        )

    def _validar_regras(self, s: Session, dados: dict[str, Any], atual: Colaborador | None) -> None:
        garantir_do_tenant(s, self.ctx, Unidade, dados["unidade_id"], "Unidade")
        setor = garantir_do_tenant(s, self.ctx, Setor, dados.get("setor_id"), "Setor")
        if setor and setor.unidade_id != dados["unidade_id"]:
            raise RegraNegocioError("O setor escolhido não pertence à unidade do colaborador.")
        garantir_do_tenant(s, self.ctx, Cargo, dados.get("cargo_id"), "Cargo")

    def _validar_exclusao(self, s: Session, obj: Colaborador) -> None:
        if _vencimentos_ativos(s, self.ctx.tenant_id, Vencimento.colaborador_id, obj.id):
            raise RegraNegocioError(
                "Colaborador possui vencimentos ativos. Para quem saiu da empresa, "
                "altere a situação para 'Desligado' (o histórico é preservado)."
            )

    def perfil(self, ident: int) -> dict[str, Any]:
        """Dados cadastrais com nomes de unidade/setor/cargo. CPF vem MASCARADO (LGPD);
        o número completo só por `revelar_cpf`, que fica registrado na auditoria."""
        from sst.domain.validadores import mascarar_cpf
        from sst.infra.db.models import Tenant

        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            obj = self._repo(s).obter_ou_erro(ident)
            self._checar_escopo(obj)
            dados = obj.to_dict()
            dados["empresa"] = s.get(Tenant, obj.tenant_id).nome
            dados["unidade"] = s.get(Unidade, obj.unidade_id).nome
            dados["setor"] = s.get(Setor, obj.setor_id).nome if obj.setor_id else None
            dados["cargo"] = s.get(Cargo, obj.cargo_id).nome if obj.cargo_id else None
        dados["cpf_mascarado"] = mascarar_cpf(dados.pop("cpf"))
        return dados

    def revelar_cpf(self, ident: int) -> str:
        from sst.domain.enums import AcaoAuditoria
        from sst.domain.validadores import formatar_cpf
        from sst.services import auditoria_service as auditoria

        self.ctx.exigir(Permissao.EDITAR_CADASTROS)
        with session_scope() as s:
            obj = self._repo(s).obter_ou_erro(ident)
            self._checar_escopo(obj)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.VISUALIZAR_SENSIVEL, self.entidade, obj.id,
                                None, {"campo": "cpf"})
            return formatar_cpf(obj.cpf)

    def opcoes(self, apenas_ativos: bool = True, **filtros: Any) -> dict[int, str]:
        # Colaborador não tem coluna 'ativo': filtra por situação
        df = self.listar()
        if apenas_ativos and not df.empty:
            df = df[df["situacao"] != SituacaoColaborador.DESLIGADO.value]
        for campo, valor in filtros.items():
            if valor is not None and campo in df.columns:
                df = df[df[campo] == valor]
        return {
            int(r.id): f"{r.nome}" + (f" - Mat. {r.matricula}" if r.matricula else "")
            for r in df.itertuples()
        }


# ============================================================== EQUIPAMENTOS
class EquipamentoService(CrudService[Equipamento]):
    model = Equipamento
    schema = EquipamentoIn
    entidade = "Equipamento"
    campo_rotulo = "descricao"
    campo_unidade = "unidade_id"
    campos_unicos = {"patrimonio": "patrimônio"}

    def _select_listagem(self) -> Select:
        resp = aliased(Colaborador)
        return (
            select(
                Equipamento.id,
                Equipamento.descricao,
                Equipamento.tipo,
                Equipamento.patrimonio,
                Equipamento.numero_serie,
                Equipamento.ca_numero,
                Equipamento.unidade_id,
                Unidade.nome.label("unidade"),
                Equipamento.localizacao,
                resp.nome.label("responsavel"),
                Equipamento.situacao,
            )
            .join(Unidade, Unidade.id == Equipamento.unidade_id)
            .outerjoin(resp, resp.id == Equipamento.responsavel_colaborador_id)
        )

    def _validar_regras(self, s: Session, dados: dict[str, Any], atual: Equipamento | None) -> None:
        garantir_do_tenant(s, self.ctx, Unidade, dados["unidade_id"], "Unidade")
        garantir_do_tenant(s, self.ctx, Colaborador, dados.get("responsavel_colaborador_id"), "Colaborador")

    def _validar_exclusao(self, s: Session, obj: Equipamento) -> None:
        if _vencimentos_ativos(s, self.ctx.tenant_id, Vencimento.equipamento_id, obj.id):
            raise RegraNegocioError(
                "Equipamento possui vencimentos ativos. Para equipamento fora de uso, "
                "altere a situação para 'Baixado'."
            )

    def opcoes(self, apenas_ativos: bool = True, **filtros: Any) -> dict[int, str]:
        df = self.listar()
        if apenas_ativos and not df.empty:
            df = df[df["situacao"] != "BAIXADO"]
        for campo, valor in filtros.items():
            if valor is not None and campo in df.columns:
                df = df[df[campo] == valor]
        return {
            int(r.id): f"{r.descricao}" + (f" (Pat. {r.patrimonio})" if r.patrimonio else "")
            for r in df.itertuples()
        }
