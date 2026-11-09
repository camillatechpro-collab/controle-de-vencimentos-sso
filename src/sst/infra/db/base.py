"""Base declarativa e mixins comuns (SQLAlchemy 2.x, estilo tipado)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Nomes determinísticos de constraints (necessário para migrações futuras com Alembic)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # colunas omitidas de auditoria/serialização
    __campos_sensiveis__ = ()  # sem anotação: o declarative ignora

    def to_dict(self, incluir_sensiveis: bool = False) -> dict[str, Any]:
        """Serializa colunas (não relacionamentos) em tipos simples."""
        dados: dict[str, Any] = {}
        for col in self.__table__.columns:
            if not incluir_sensiveis and col.key in self.__campos_sensiveis__:
                continue
            dados[col.key] = getattr(self, col.key)
        return dados


def serializar(valor: Any) -> Any:
    """Converte valores para JSON (auditoria)."""
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: serializar(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [serializar(v) for v in valor]
    return valor


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class TenantMixin:
    @declared_attr
    def tenant_id(cls) -> Mapped[int]:  # noqa: N805
        return mapped_column(
            ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
        )


class TimestampMixin:
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    criado_por_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atualizado_por_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SoftDeleteMixin:
    excluido_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    excluido_por_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
