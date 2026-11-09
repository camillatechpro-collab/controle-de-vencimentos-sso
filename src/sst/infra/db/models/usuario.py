from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sst.domain.enums import Perfil
from sst.infra.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from sst.infra.db.models._tipos import enum_col


class Usuario(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "usuarios"
    __campos_sensiveis__ = ("senha_hash",)

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    # E-mail é o login: único em toda a plataforma (simplifica o login multiempresa)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[Perfil] = mapped_column(enum_col(Perfil), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deve_trocar_senha: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    unidades: Mapped[list[UsuarioUnidade]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class UsuarioUnidade(Base):
    """Escopo de acesso por unidade. Nenhuma linha = acesso a todas."""

    __tablename__ = "usuario_unidades"
    __table_args__ = (UniqueConstraint("usuario_id", "unidade_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unidade_id: Mapped[int] = mapped_column(
        ForeignKey("unidades.id", ondelete="CASCADE"), nullable=False
    )

    usuario: Mapped[Usuario] = relationship(back_populates="unidades")
