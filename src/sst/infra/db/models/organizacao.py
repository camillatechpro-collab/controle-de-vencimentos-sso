"""Estrutura organizacional: unidades, setores, cargos, colaboradores, fornecedores, equipamentos."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sst.domain.enums import SituacaoColaborador, SituacaoEquipamento, TipoFornecedor
from sst.infra.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin
from sst.infra.db.models._tipos import enum_col


class Unidade(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "unidades"
    __table_args__ = (UniqueConstraint("tenant_id", "nome"),)

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14))
    razao_social: Mapped[str | None] = mapped_column(String(200))
    # Dados cadastrais públicos (consulta de CNPJ ou preenchimento manual)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    cep: Mapped[str | None] = mapped_column(String(8))
    cnae: Mapped[str | None] = mapped_column(String(255))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(60))
    endereco: Mapped[str | None] = mapped_column(String(255))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))
    responsavel_nome: Mapped[str | None] = mapped_column(String(150))
    email_alertas: Mapped[str | None] = mapped_column(String(200))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Setor(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "setores"
    __table_args__ = (UniqueConstraint("unidade_id", "nome"),)

    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Cargo(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "cargos"
    __table_args__ = (UniqueConstraint("tenant_id", "nome"),)

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    # CBO: retirado das telas; a coluna é mantida para preservar os dados já cadastrados
    cbo: Mapped[str | None] = mapped_column(String(10))
    descricao: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Colaborador(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "colaboradores"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cpf"),
        Index("ix_colaboradores_tenant_nome", "tenant_id", "nome"),
    )

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), nullable=False)
    matricula: Mapped[str | None] = mapped_column(String(30))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), nullable=False, index=True)
    setor_id: Mapped[int | None] = mapped_column(ForeignKey("setores.id"))
    cargo_id: Mapped[int | None] = mapped_column(ForeignKey("cargos.id"), index=True)
    data_admissao: Mapped[date | None] = mapped_column(Date)
    data_desligamento: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(30))
    situacao: Mapped[SituacaoColaborador] = mapped_column(
        enum_col(SituacaoColaborador), default=SituacaoColaborador.ATIVO, nullable=False
    )


class Fornecedor(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "fornecedores"
    __table_args__ = (UniqueConstraint("tenant_id", "cnpj"),)

    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14))
    tipo: Mapped[TipoFornecedor] = mapped_column(
        enum_col(TipoFornecedor), default=TipoFornecedor.OUTRO, nullable=False
    )
    # Dados cadastrais públicos (consulta de CNPJ ou preenchimento manual)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    cep: Mapped[str | None] = mapped_column(String(8))
    cnae: Mapped[str | None] = mapped_column(String(255))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(60))
    endereco: Mapped[str | None] = mapped_column(String(255))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))
    contato: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(30))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Equipamento(IdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "equipamentos"
    __table_args__ = (UniqueConstraint("tenant_id", "patrimonio"),)

    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)  # Extintor, Cinto, Detector...
    patrimonio: Mapped[str | None] = mapped_column(String(50))
    numero_serie: Mapped[str | None] = mapped_column(String(80))
    fabricante: Mapped[str | None] = mapped_column(String(100))
    modelo: Mapped[str | None] = mapped_column(String(100))
    ca_numero: Mapped[str | None] = mapped_column(String(20))
    localizacao: Mapped[str | None] = mapped_column(String(150))
    responsavel_colaborador_id: Mapped[int | None] = mapped_column(ForeignKey("colaboradores.id"))
    situacao: Mapped[SituacaoEquipamento] = mapped_column(
        enum_col(SituacaoEquipamento), default=SituacaoEquipamento.ATIVO, nullable=False
    )
