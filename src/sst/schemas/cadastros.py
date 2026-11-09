"""Schemas de entrada dos cadastros."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import AfterValidator, Field, field_validator, model_validator

from sst.domain.enums import (
    AlvoTipo,
    Categoria,
    SituacaoColaborador,
    SituacaoEquipamento,
    TipoFornecedor,
    ValidadeUnidade,
)
from sst.domain.validadores import (
    normalizar_cnpj,
    somente_digitos,
    validar_cnpj,
    validar_cpf,
    validar_email,
)
from sst.schemas.base import Entrada

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def _cnpj_opcional(v: str | None) -> str | None:
    if v is None:
        return None
    if not validar_cnpj(v):
        raise ValueError("CNPJ inválido")
    return normalizar_cnpj(v)


def _email_opcional(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().lower()
    if not validar_email(v):
        raise ValueError("e-mail inválido")
    return v


def _cep_opcional(v: str | None) -> str | None:
    if v is None:
        return None
    d = somente_digitos(v)
    if len(d) != 8:
        raise ValueError("CEP deve ter 8 dígitos")
    return d


CnpjOpcional = Annotated[str | None, AfterValidator(_cnpj_opcional)]
EmailOpcional = Annotated[str | None, AfterValidator(_email_opcional)]


class UnidadeIn(Entrada):
    nome: str = Field(min_length=2, max_length=150, title="Nome")
    cnpj: CnpjOpcional = Field(default=None, title="CNPJ")
    razao_social: str | None = Field(default=None, max_length=200, title="Razão social")
    nome_fantasia: str | None = Field(default=None, max_length=200, title="Nome fantasia")
    cep: str | None = Field(default=None, title="CEP")
    cnae: str | None = Field(default=None, max_length=255, title="CNAE principal")
    situacao_cadastral: str | None = Field(default=None, max_length=60, title="Situação cadastral")
    endereco: str | None = Field(default=None, max_length=255, title="Endereço")
    cidade: str | None = Field(default=None, max_length=100, title="Cidade")
    uf: str | None = Field(default=None, title="UF")
    responsavel_nome: str | None = Field(default=None, max_length=150, title="Responsável")
    email_alertas: EmailOpcional = Field(default=None, title="E-mail para alertas")
    ativo: bool = Field(default=True, title="Ativo")


    @field_validator("uf")
    @classmethod
    def _uf(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper()
        if v not in UFS:
            raise ValueError("UF inválida")
        return v

    @field_validator("cep")
    @classmethod
    def _cep(cls, v: str | None) -> str | None:
        return _cep_opcional(v)


class SetorIn(Entrada):
    unidade_id: int = Field(title="Unidade")
    nome: str = Field(min_length=2, max_length=150, title="Nome")
    ativo: bool = Field(default=True, title="Ativo")


class CargoIn(Entrada):
    nome: str = Field(min_length=2, max_length=150, title="Nome")
    descricao: str | None = Field(default=None, title="Descrição")
    ativo: bool = Field(default=True, title="Ativo")


class ColaboradorIn(Entrada):
    nome: str = Field(min_length=3, max_length=150, title="Nome")
    cpf: str = Field(title="CPF")
    matricula: str | None = Field(default=None, max_length=30, title="Matrícula")
    unidade_id: int = Field(title="Unidade")
    setor_id: int | None = Field(default=None, title="Setor")
    cargo_id: int | None = Field(default=None, title="Cargo")
    data_admissao: date | None = Field(default=None, title="Data de admissão")
    data_desligamento: date | None = Field(default=None, title="Data de desligamento")
    email: EmailOpcional = Field(default=None, title="E-mail")
    telefone: str | None = Field(default=None, max_length=30, title="Telefone")
    situacao: SituacaoColaborador = Field(default=SituacaoColaborador.ATIVO, title="Situação")


    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str) -> str:
        if not validar_cpf(v):
            raise ValueError("CPF inválido")
        return somente_digitos(v)

    @model_validator(mode="after")
    def _datas(self) -> ColaboradorIn:
        if self.data_desligamento and self.data_admissao and self.data_desligamento < self.data_admissao:
            raise ValueError("Data de desligamento anterior à admissão")
        if self.situacao is SituacaoColaborador.DESLIGADO and not self.data_desligamento:
            raise ValueError("Informe a data de desligamento para colaborador desligado")
        if self.data_desligamento and self.situacao is not SituacaoColaborador.DESLIGADO:
            raise ValueError("Colaborador com data de desligamento deve estar com situação 'Desligado'")
        return self


class FornecedorIn(Entrada):
    razao_social: str = Field(min_length=2, max_length=200, title="Razão social")
    cnpj: CnpjOpcional = Field(default=None, title="CNPJ")
    tipo: TipoFornecedor = Field(default=TipoFornecedor.OUTRO, title="Tipo")
    nome_fantasia: str | None = Field(default=None, max_length=200, title="Nome fantasia")
    cep: str | None = Field(default=None, title="CEP")
    cnae: str | None = Field(default=None, max_length=255, title="CNAE principal")
    situacao_cadastral: str | None = Field(default=None, max_length=60, title="Situação cadastral")
    endereco: str | None = Field(default=None, max_length=255, title="Endereço")
    cidade: str | None = Field(default=None, max_length=100, title="Cidade")
    uf: str | None = Field(default=None, title="UF")
    contato: str | None = Field(default=None, max_length=150, title="Contato")
    email: EmailOpcional = Field(default=None, title="E-mail")
    telefone: str | None = Field(default=None, max_length=30, title="Telefone")
    ativo: bool = Field(default=True, title="Ativo")

    @field_validator("uf")
    @classmethod
    def _uf(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper()
        if v not in UFS:
            raise ValueError("UF inválida")
        return v

    @field_validator("cep")
    @classmethod
    def _cep(cls, v: str | None) -> str | None:
        return _cep_opcional(v)


class EquipamentoIn(Entrada):
    unidade_id: int = Field(title="Unidade")
    descricao: str = Field(min_length=2, max_length=200, title="Descrição")
    tipo: str = Field(min_length=2, max_length=100, title="Tipo")
    patrimonio: str | None = Field(default=None, max_length=50, title="Patrimônio")
    numero_serie: str | None = Field(default=None, max_length=80, title="Número de série")
    fabricante: str | None = Field(default=None, max_length=100, title="Fabricante")
    modelo: str | None = Field(default=None, max_length=100, title="Modelo")
    ca_numero: str | None = Field(default=None, max_length=20, title="Nº do CA")
    localizacao: str | None = Field(default=None, max_length=150, title="Localização")
    responsavel_colaborador_id: int | None = Field(default=None, title="Responsável")
    situacao: SituacaoEquipamento = Field(default=SituacaoEquipamento.ATIVO, title="Situação")


class TipoControleIn(Entrada):
    categoria: Categoria = Field(title="Categoria")
    nome: str = Field(min_length=3, max_length=150, title="Nome")
    norma_referencia: str | None = Field(default=None, max_length=100, title="Norma de referência")
    alvo_tipo: AlvoTipo = Field(title="Aplica-se a")
    validade_valor: int | None = Field(default=None, ge=1, le=600, title="Validade")
    validade_unidade: ValidadeUnidade = Field(default=ValidadeUnidade.MESES, title="Unidade da validade")
    antecedencia_dias: int = Field(default=30, ge=0, le=365, title="Antecedência do alerta (dias)")
    exige_anexo: bool = Field(default=False, title="Exige anexo")
    carga_horaria_padrao: int | None = Field(default=None, ge=1, le=2000, title="Carga horária padrão")
    descricao: str | None = Field(default=None, title="Descrição")
    ativo: bool = Field(default=True, title="Ativo")

    @model_validator(mode="after")
    def _validade(self) -> TipoControleIn:
        precisa_valor = self.validade_unidade in (
            ValidadeUnidade.DIAS, ValidadeUnidade.MESES, ValidadeUnidade.ANOS
        )
        if precisa_valor and not self.validade_valor:
            raise ValueError("Informe a validade para a unidade escolhida")
        if not precisa_valor:
            self.validade_valor = None
        coerencia = {
            Categoria.EXAME: {AlvoTipo.COLABORADOR},
            Categoria.TREINAMENTO: {AlvoTipo.COLABORADOR},
            Categoria.EQUIPAMENTO: {AlvoTipo.EQUIPAMENTO},
        }
        permitido = coerencia.get(self.categoria)
        if permitido and self.alvo_tipo not in permitido:
            raise ValueError(
                f"Categoria {self.categoria.rotulo} deve se aplicar a "
                + ", ".join(a.rotulo for a in permitido)
            )
        return self
