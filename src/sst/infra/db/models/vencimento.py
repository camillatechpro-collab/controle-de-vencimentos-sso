"""Núcleo: vencimentos, extensões 1:1 por categoria e anexos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sst.domain.enums import (
    AlvoTipo,
    Modalidade,
    ResultadoASO,
    SituacaoVencimento,
    TipoASO,
    TipoServicoEquipamento,
)
from sst.infra.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin
from sst.infra.db.models._tipos import enum_col

# Coluna FK de alvo correspondente a cada AlvoTipo (EMPRESA não tem FK)
COLUNAS_ALVO: dict[AlvoTipo, str | None] = {
    AlvoTipo.COLABORADOR: "colaborador_id",
    AlvoTipo.EQUIPAMENTO: "equipamento_id",
    AlvoTipo.UNIDADE: "alvo_unidade_id",
    AlvoTipo.FORNECEDOR: "fornecedor_id",
    AlvoTipo.EMPRESA: None,
}


def _sql_alvo_coerente() -> str:
    """Gera o CHECK: exatamente a coluna de alvo correspondente ao alvo_tipo
    está preenchida e todas as outras estão nulas."""
    todas = [c for c in COLUNAS_ALVO.values() if c]
    partes = []
    for alvo, coluna in COLUNAS_ALVO.items():
        condicoes = [f"alvo_tipo = '{alvo.value}'"]
        for c in todas:
            condicoes.append(f"{c} IS NOT NULL" if c == coluna else f"{c} IS NULL")
        partes.append("(" + " AND ".join(condicoes) + ")")
    return " OR ".join(partes)


SQL_ALVO_COERENTE = _sql_alvo_coerente()


class Vencimento(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "vencimentos"
    __table_args__ = (
        CheckConstraint(SQL_ALVO_COERENTE, name="alvo_coerente"),
        CheckConstraint(
            "NOT vencimento_ajustado_manual OR justificativa_ajuste IS NOT NULL",
            name="justificativa_ajuste",
        ),
        CheckConstraint(
            "data_vencimento IS NULL OR data_emissao IS NULL OR data_vencimento >= data_emissao",
            name="datas_coerentes",
        ),
        Index("ix_venc_tenant_vencimento", "tenant_id", "data_vencimento"),
        Index("ix_venc_tenant_situacao", "tenant_id", "situacao"),
        Index("ix_venc_tenant_tipo_colab", "tenant_id", "tipo_controle_id", "colaborador_id"),
        Index("ix_venc_tenant_tipo_equip", "tenant_id", "tipo_controle_id", "equipamento_id"),
    )

    tipo_controle_id: Mapped[int] = mapped_column(
        ForeignKey("tipos_controle.id"), nullable=False, index=True
    )
    alvo_tipo: Mapped[AlvoTipo] = mapped_column(enum_col(AlvoTipo), nullable=False)
    colaborador_id: Mapped[int | None] = mapped_column(ForeignKey("colaboradores.id"))
    equipamento_id: Mapped[int | None] = mapped_column(ForeignKey("equipamentos.id"))
    alvo_unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"))
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"))
    # Unidade de escopo (derivada do alvo) usada para filtros e permissão por unidade
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), index=True)

    numero_documento: Mapped[str | None] = mapped_column(String(80))
    emissor: Mapped[str | None] = mapped_column(String(150))
    data_emissao: Mapped[date | None] = mapped_column(Date)
    data_vencimento: Mapped[date | None] = mapped_column(Date)
    vencimento_ajustado_manual: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    justificativa_ajuste: Mapped[str | None] = mapped_column(Text)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    situacao: Mapped[SituacaoVencimento] = mapped_column(
        enum_col(SituacaoVencimento), default=SituacaoVencimento.ATIVO, nullable=False
    )
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    renovado_de_id: Mapped[int | None] = mapped_column(
        ForeignKey("vencimentos.id"), index=True
    )
    # Turma de treinamento que originou o registro (vários colaboradores, vencimento individual)
    turma_id: Mapped[int | None] = mapped_column(ForeignKey("turmas_treinamento.id"), index=True)
    observacoes: Mapped[str | None] = mapped_column(Text)

    treinamento: Mapped[VencTreinamento | None] = relationship(
        back_populates="vencimento", cascade="all, delete-orphan", uselist=False
    )
    exame: Mapped[VencExame | None] = relationship(
        back_populates="vencimento", cascade="all, delete-orphan", uselist=False
    )
    contrato: Mapped[VencContrato | None] = relationship(
        back_populates="vencimento", cascade="all, delete-orphan", uselist=False
    )
    servico_equipamento: Mapped[VencEquipamento | None] = relationship(
        back_populates="vencimento", cascade="all, delete-orphan", uselist=False
    )


class TurmaTreinamento(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Realização de um treinamento (turma). Cada participante tem o seu próprio
    registro em `vencimentos` (vencimento, certificado e renovações individuais)."""

    __tablename__ = "turmas_treinamento"
    __table_args__ = (Index("ix_turma_tenant_data", "tenant_id", "data_realizacao"),)

    tipo_controle_id: Mapped[int] = mapped_column(ForeignKey("tipos_controle.id"), nullable=False, index=True)
    data_realizacao: Mapped[date] = mapped_column(Date, nullable=False)
    carga_horaria: Mapped[int | None] = mapped_column(Integer)
    instrutor: Mapped[str | None] = mapped_column(String(150))
    instituicao_fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"))
    modalidade: Mapped[Modalidade | None] = mapped_column(enum_col(Modalidade))
    local: Mapped[str | None] = mapped_column(String(150))
    observacoes: Mapped[str | None] = mapped_column(Text)


class VencTreinamento(Base):
    __tablename__ = "venc_treinamentos"

    vencimento_id: Mapped[int] = mapped_column(
        ForeignKey("vencimentos.id", ondelete="CASCADE"), primary_key=True
    )
    carga_horaria: Mapped[int | None] = mapped_column(Integer)
    instrutor: Mapped[str | None] = mapped_column(String(150))
    instituicao_fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"))
    modalidade: Mapped[Modalidade | None] = mapped_column(enum_col(Modalidade))
    nota_aproveitamento: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    vencimento: Mapped[Vencimento] = relationship(back_populates="treinamento")


class VencExame(Base):
    """Dados mínimos do ASO (LGPD): sem CID e sem diagnóstico."""

    __tablename__ = "venc_exames"
    __campos_sensiveis__ = ("resultado",)

    vencimento_id: Mapped[int] = mapped_column(
        ForeignKey("vencimentos.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_aso: Mapped[TipoASO | None] = mapped_column(enum_col(TipoASO))
    medico_nome: Mapped[str | None] = mapped_column(String(150))
    medico_crm: Mapped[str | None] = mapped_column(String(20))
    clinica_fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"))
    resultado: Mapped[ResultadoASO | None] = mapped_column(enum_col(ResultadoASO))

    vencimento: Mapped[Vencimento] = relationship(back_populates="exame")


class VencContrato(Base):
    __tablename__ = "venc_contratos"

    vencimento_id: Mapped[int] = mapped_column(
        ForeignKey("vencimentos.id", ondelete="CASCADE"), primary_key=True
    )
    valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    objeto: Mapped[str | None] = mapped_column(Text)
    renovacao_automatica: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    aviso_previo_dias: Mapped[int | None] = mapped_column(Integer)

    vencimento: Mapped[Vencimento] = relationship(back_populates="contrato")


class VencEquipamento(Base):
    __tablename__ = "venc_equipamentos"

    vencimento_id: Mapped[int] = mapped_column(
        ForeignKey("vencimentos.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_servico: Mapped[TipoServicoEquipamento | None] = mapped_column(
        enum_col(TipoServicoEquipamento)
    )
    laudo_numero: Mapped[str | None] = mapped_column(String(80))
    executor_fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedores.id"))

    vencimento: Mapped[Vencimento] = relationship(back_populates="servico_equipamento")


class Anexo(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "anexos"

    vencimento_id: Mapped[int] = mapped_column(
        ForeignKey("vencimentos.id"), nullable=False, index=True
    )
    nome_original: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_relativo: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
