from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sst.domain.enums import AcaoAuditoria
from sst.infra.db.base import Base, IdMixin, utcnow
from sst.infra.db.models._tipos import enum_col


class Auditoria(IdMixin, Base):
    """Trilha append-only. A aplicação nunca altera nem exclui linhas desta tabela."""

    __tablename__ = "auditoria"
    __table_args__ = (
        Index("ix_auditoria_entidade", "tenant_id", "entidade", "entidade_id"),
        Index("ix_auditoria_data", "tenant_id", "criado_em"),
    )

    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"))
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    usuario_email: Mapped[str | None] = mapped_column(String(200))
    acao: Mapped[AcaoAuditoria] = mapped_column(enum_col(AcaoAuditoria), nullable=False)
    entidade: Mapped[str] = mapped_column(String(60), nullable=False)
    entidade_id: Mapped[int | None] = mapped_column(Integer)
    dados_antes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    dados_depois: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
