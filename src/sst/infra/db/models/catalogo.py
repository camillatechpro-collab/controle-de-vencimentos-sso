"""Catálogo de tipos de controle e matriz de requisitos por cargo."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sst.domain.enums import AlvoTipo, Categoria, ValidadeUnidade
from sst.infra.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin
from sst.infra.db.models._tipos import enum_col


class TipoControle(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tipos_controle"
    __table_args__ = (UniqueConstraint("tenant_id", "nome"),)

    categoria: Mapped[Categoria] = mapped_column(enum_col(Categoria), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    norma_referencia: Mapped[str | None] = mapped_column(String(100))
    alvo_tipo: Mapped[AlvoTipo] = mapped_column(enum_col(AlvoTipo), nullable=False)
    validade_valor: Mapped[int | None] = mapped_column(Integer)
    validade_unidade: Mapped[ValidadeUnidade] = mapped_column(
        enum_col(ValidadeUnidade), nullable=False, default=ValidadeUnidade.MESES
    )
    antecedencia_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    exige_anexo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    carga_horaria_padrao: Mapped[int | None] = mapped_column(Integer)
    descricao: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RequisitoCargo(IdMixin, TenantMixin, TimestampMixin, Base):
    """Matriz: o cargo X exige o tipo de controle Y."""

    __tablename__ = "requisitos_cargo"
    __table_args__ = (UniqueConstraint("cargo_id", "tipo_controle_id"),)

    cargo_id: Mapped[int] = mapped_column(
        ForeignKey("cargos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo_controle_id: Mapped[int] = mapped_column(
        ForeignKey("tipos_controle.id", ondelete="CASCADE"), nullable=False
    )
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
