from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sst.infra.db.base import Base, IdMixin, TimestampMixin


class Tenant(IdMixin, TimestampMixin, Base):
    """Empresa cliente do SaaS."""

    __tablename__ = "tenants"

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14), unique=True, nullable=True)
    plano: Mapped[str] = mapped_column(String(30), default="PADRAO")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    antecedencia_padrao_dias: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    email_alertas: Mapped[str | None] = mapped_column(String(200), nullable=True)
