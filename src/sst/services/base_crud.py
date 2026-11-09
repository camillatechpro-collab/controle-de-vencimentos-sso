"""CRUD genérico com: permissão, filtro de tenant, escopo por unidade,
validação (Pydantic), soft delete, lixeira e auditoria."""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

import pandas as pd
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from sst.domain.enums import AcaoAuditoria
from sst.domain.exceptions import PermissaoNegadaError, RegraNegocioError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.infra.db.base import Base
from sst.infra.db.engine import session_scope
from sst.infra.repositories.base import TenantRepository, filtro_tenant
from sst.logging_config import get_logger
from sst.schemas.base import Entrada, validar
from sst.services import auditoria_service as auditoria
from sst.services._util import df_de_resultado

M = TypeVar("M", bound=Base)
T = TypeVar("T", bound=Base)

log = get_logger(__name__)


def garantir_do_tenant(
    s: Session, ctx: UsuarioContexto, model: type[T], ident: int | None, nome: str
) -> T | None:
    """Garante que um id referenciado (FK) pertence ao tenant do usuário."""
    if ident is None:
        return None
    return TenantRepository(s, model, ctx.tenant_id, nome).obter_ou_erro(ident)


class CrudService(Generic[M]):
    model: ClassVar[type[Base]]
    schema: ClassVar[type[Entrada]]
    entidade: ClassVar[str]
    campo_rotulo: ClassVar[str] = "nome"
    campo_unidade: ClassVar[str | None] = None  # coluna usada no escopo por unidade
    campos_unicos: ClassVar[dict[str, str]] = {}  # campo → rótulo (unicidade no tenant)
    perm_escrita: ClassVar[Permissao] = Permissao.EDITAR_CADASTROS

    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx

    # ------------------------------------------------------------------ helpers
    def _repo(self, s: Session) -> TenantRepository:
        return TenantRepository(s, self.model, self.ctx.tenant_id, self.entidade)

    def _aplicar_escopo(self, stmt: Select) -> Select:
        if self.campo_unidade and self.ctx.restrito_por_unidade:
            stmt = stmt.where(getattr(self.model, self.campo_unidade).in_(self.ctx.unidades_ids))
        return stmt

    def _checar_escopo(self, obj_ou_dados: Any) -> None:
        if not self.campo_unidade:
            return
        valor = (
            obj_ou_dados.get(self.campo_unidade)
            if isinstance(obj_ou_dados, dict)
            else getattr(obj_ou_dados, self.campo_unidade)
        )
        if self.ctx.restrito_por_unidade and valor not in self.ctx.unidades_ids:
            raise PermissaoNegadaError("Você não tem acesso a esta unidade.")

    def _checar_unicos(self, s: Session, dados: dict[str, Any], excluir_id: int | None) -> None:
        repo = self._repo(s)
        for campo, rotulo in self.campos_unicos.items():
            valor = dados.get(campo)
            if valor is None:
                continue
            if repo.existe(incluir_excluidos=False, excluir_id=excluir_id, **{campo: valor}):
                raise RegraNegocioError(f"Já existe {self.entidade.lower()} com este {rotulo}.")
            if repo.existe(incluir_excluidos=True, excluir_id=excluir_id, **{campo: valor}):
                raise RegraNegocioError(
                    f"Já existe {self.entidade.lower()} com este {rotulo} na lixeira. "
                    "Peça a um administrador para restaurá-lo(a)."
                )

    # ------------------------------------------------------------------ hooks
    def _select_listagem(self) -> Select:
        """Sobrescreva para incluir joins/colunas descritivas."""
        return select(*self.model.__table__.columns)

    def _validar_regras(self, s: Session, dados: dict[str, Any], atual: M | None) -> None:
        """Validações que dependem do banco (FKs do tenant, coerências)."""

    def _validar_exclusao(self, s: Session, obj: M) -> None:
        """Bloqueia exclusão quando houver vínculos."""

    def _ordem(self) -> Any:
        return getattr(self.model, self.campo_rotulo)

    # ------------------------------------------------------------------ leitura
    def listar(self, incluir_inativos: bool = True) -> pd.DataFrame:
        self.ctx.exigir(Permissao.LER)
        stmt = filtro_tenant(self._select_listagem(), self.model, self.ctx.tenant_id)
        stmt = self._aplicar_escopo(stmt)
        if not incluir_inativos and hasattr(self.model, "ativo"):
            stmt = stmt.where(self.model.ativo.is_(True))
        ordem = self._ordem()
        stmt = stmt.order_by(*(ordem if isinstance(ordem, tuple) else (ordem,)))
        with session_scope() as s:
            return df_de_resultado(s.execute(stmt))

    def obter(self, ident: int) -> dict[str, Any]:
        self.ctx.exigir(Permissao.LER)
        with session_scope() as s:
            obj = self._repo(s).obter_ou_erro(ident)
            self._checar_escopo(obj)
            return obj.to_dict()

    def opcoes(self, apenas_ativos: bool = True, **filtros: Any) -> dict[int, str]:
        """{id: rótulo} para caixas de seleção."""
        self.ctx.exigir(Permissao.LER)
        col_rotulo = getattr(self.model, self.campo_rotulo)
        stmt = filtro_tenant(select(self.model.id, col_rotulo), self.model, self.ctx.tenant_id)
        stmt = self._aplicar_escopo(stmt)
        if apenas_ativos and hasattr(self.model, "ativo"):
            stmt = stmt.where(self.model.ativo.is_(True))
        for campo, valor in filtros.items():
            if valor is not None:
                stmt = stmt.where(getattr(self.model, campo) == valor)
        with session_scope() as s:
            return {i: r for i, r in s.execute(stmt.order_by(col_rotulo)).all()}

    # ------------------------------------------------------------------ escrita
    def _para_model(self, dados: dict[str, Any]) -> dict[str, Any]:
        return dados

    def criar(self, dados: dict[str, Any]) -> int:
        self.ctx.exigir(self.perm_escrita)
        dados = validar(self.schema, dados)
        self._checar_escopo(dados)
        with session_scope() as s:
            self._checar_unicos(s, dados, None)
            self._validar_regras(s, dados, None)
            obj = self.model(**self._para_model(dados))
            self._repo(s).adicionar(obj, self.ctx.usuario_id)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.CRIAR, self.entidade, obj.id, None, obj.to_dict())
            novo_id = obj.id
        log.info("%s criado id=%s tenant=%s por=%s", self.entidade, novo_id, self.ctx.tenant_id, self.ctx.usuario_id)
        return novo_id

    def atualizar(self, ident: int, dados: dict[str, Any]) -> None:
        self.ctx.exigir(self.perm_escrita)
        dados = validar(self.schema, dados)
        with session_scope() as s:
            repo = self._repo(s)
            obj = repo.obter_ou_erro(ident)
            self._checar_escopo(obj)
            self._checar_escopo(dados)
            antes = obj.to_dict()
            self._checar_unicos(s, dados, ident)
            self._validar_regras(s, dados, obj)
            repo.atualizar(obj, self._para_model(dados), self.ctx.usuario_id)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.ALTERAR, self.entidade, ident, antes, obj.to_dict())
        log.info("%s alterado id=%s por=%s", self.entidade, ident, self.ctx.usuario_id)

    def excluir(self, ident: int) -> None:
        self.ctx.exigir(self.perm_escrita)
        with session_scope() as s:
            repo = self._repo(s)
            obj = repo.obter_ou_erro(ident)
            self._checar_escopo(obj)
            self._validar_exclusao(s, obj)
            repo.excluir_logico(obj, self.ctx.usuario_id)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.EXCLUIR, self.entidade, ident, obj.to_dict(), None)
        log.info("%s excluído (lógico) id=%s por=%s", self.entidade, ident, self.ctx.usuario_id)

    # ------------------------------------------------------------------ lixeira
    def listar_excluidos(self) -> pd.DataFrame:
        self.ctx.exigir(Permissao.ADMINISTRAR)
        cols = [self.model.id, getattr(self.model, self.campo_rotulo).label("descricao"),
                self.model.excluido_em]
        stmt = (
            filtro_tenant(select(*cols), self.model, self.ctx.tenant_id, incluir_excluidos=True)
            .where(self.model.excluido_em.is_not(None))
            .order_by(self.model.excluido_em.desc())
        )
        with session_scope() as s:
            return df_de_resultado(s.execute(stmt))

    def restaurar(self, ident: int) -> None:
        self.ctx.exigir(Permissao.ADMINISTRAR)
        with session_scope() as s:
            repo = self._repo(s)
            obj = repo.obter_ou_erro(ident, incluir_excluidos=True)
            if obj.excluido_em is None:
                raise RegraNegocioError("Registro não está na lixeira.")
            repo.restaurar(obj, self.ctx.usuario_id)
            auditoria.registrar(s, self.ctx, AcaoAuditoria.RESTAURAR, self.entidade, ident, None, obj.to_dict())
