"""Repositório com filtro de tenant obrigatório.

Toda consulta de negócio deve passar por aqui (ou usar `filtro_tenant`) para
que seja impossível ler/alterar dados de outra empresa por esquecimento.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from sst.domain.exceptions import NaoEncontradoError
from sst.infra.db.base import Base, utcnow

M = TypeVar("M", bound=Base)


def tem_soft_delete(model: type[Base]) -> bool:
    return hasattr(model, "excluido_em")


def filtro_tenant(stmt: Select, model: type[Base], tenant_id: int, incluir_excluidos=False) -> Select:
    stmt = stmt.where(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
    if tem_soft_delete(model) and not incluir_excluidos:
        stmt = stmt.where(model.excluido_em.is_(None))  # type: ignore[attr-defined]
    return stmt


class TenantRepository(Generic[M]):
    def __init__(self, session: Session, model: type[M], tenant_id: int, nome_entidade: str = ""):
        if not tenant_id:
            raise ValueError("tenant_id é obrigatório.")
        self.s = session
        self.model = model
        self.tenant_id = tenant_id
        self.nome = nome_entidade or model.__name__

    # ------------- leitura -------------
    def select(self, incluir_excluidos: bool = False) -> Select:
        return filtro_tenant(select(self.model), self.model, self.tenant_id, incluir_excluidos)

    def obter(self, ident: int, incluir_excluidos: bool = False) -> M | None:
        stmt = self.select(incluir_excluidos).where(self.model.id == ident)  # type: ignore[attr-defined]
        return self.s.scalars(stmt).first()

    def obter_ou_erro(self, ident: int, incluir_excluidos: bool = False) -> M:
        obj = self.obter(ident, incluir_excluidos)
        if obj is None:
            raise NaoEncontradoError(self.nome, ident)
        return obj

    def existe(self, incluir_excluidos: bool = True, excluir_id: int | None = None, **filtros: Any) -> bool:
        stmt = self.select(incluir_excluidos)
        for campo, valor in filtros.items():
            stmt = stmt.where(getattr(self.model, campo) == valor)
        if excluir_id is not None:
            stmt = stmt.where(self.model.id != excluir_id)  # type: ignore[attr-defined]
        return self.s.scalars(stmt.limit(1)).first() is not None

    def listar(self, *condicoes: Any, incluir_excluidos: bool = False) -> list[M]:
        stmt = self.select(incluir_excluidos)
        for c in condicoes:
            stmt = stmt.where(c)
        return list(self.s.scalars(stmt))

    # ------------- escrita -------------
    def adicionar(self, obj: M, usuario_id: int | None = None) -> M:
        obj.tenant_id = self.tenant_id  # type: ignore[attr-defined]
        if hasattr(obj, "criado_por_id"):
            obj.criado_por_id = usuario_id  # type: ignore[attr-defined]
            obj.atualizado_por_id = usuario_id  # type: ignore[attr-defined]
        self.s.add(obj)
        self.s.flush()  # gera o id e dispara constraints cedo
        return obj

    def atualizar(self, obj: M, dados: dict[str, Any], usuario_id: int | None = None) -> M:
        for campo, valor in dados.items():
            if campo in {"id", "tenant_id", "criado_em", "criado_por_id"}:
                continue  # campos protegidos
            setattr(obj, campo, valor)
        if hasattr(obj, "atualizado_por_id"):
            obj.atualizado_por_id = usuario_id  # type: ignore[attr-defined]
        self.s.flush()
        return obj

    def excluir_logico(self, obj: M, usuario_id: int | None = None, quando: datetime | None = None) -> None:
        obj.excluido_em = quando or utcnow()  # type: ignore[attr-defined]
        obj.excluido_por_id = usuario_id  # type: ignore[attr-defined]
        self.s.flush()

    def restaurar(self, obj: M, usuario_id: int | None = None) -> None:
        obj.excluido_em = None  # type: ignore[attr-defined]
        obj.excluido_por_id = None  # type: ignore[attr-defined]
        if hasattr(obj, "atualizado_por_id"):
            obj.atualizado_por_id = usuario_id  # type: ignore[attr-defined]
        self.s.flush()
