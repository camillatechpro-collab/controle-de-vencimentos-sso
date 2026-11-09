"""Schema de entrada de vencimento (plano: campos de extensão com prefixo)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from pydantic import Field, model_validator

from sst.domain.enums import (
    Modalidade,
    ResultadoASO,
    TipoASO,
    TipoServicoEquipamento,
)
from sst.schemas.base import Entrada

# prefixo do campo no formulário → (atributo de relacionamento, classe do model)
PREFIXOS_EXTENSAO = {
    "tr_": "treinamento",
    "ex_": "exame",
    "ct_": "contrato",
    "eq_": "servico_equipamento",
}


class VencimentoIn(Entrada):
    tipo_controle_id: int = Field(title="Tipo de controle")
    colaborador_id: int | None = Field(default=None, title="Colaborador")
    equipamento_id: int | None = Field(default=None, title="Equipamento")
    alvo_unidade_id: int | None = Field(default=None, title="Unidade")
    fornecedor_id: int | None = Field(default=None, title="Fornecedor")
    numero_documento: str | None = Field(default=None, max_length=80, title="Nº do documento/certificado")
    emissor: str | None = Field(default=None, max_length=150, title="Emissor")
    data_emissao: date | None = Field(default=None, title="Data de emissão/realização")
    data_vencimento: date | None = Field(default=None, title="Data de vencimento")
    justificativa_ajuste: str | None = Field(default=None, max_length=1000, title="Justificativa do ajuste")
    responsavel_usuario_id: int | None = Field(default=None, title="Responsável")
    observacoes: str | None = Field(default=None, max_length=4000, title="Observações")

    # Treinamento
    tr_carga_horaria: int | None = Field(default=None, ge=1, le=2000, title="Carga horária")
    tr_instrutor: str | None = Field(default=None, max_length=150, title="Instrutor")
    tr_instituicao_fornecedor_id: int | None = Field(default=None, title="Instituição")
    tr_modalidade: Modalidade | None = Field(default=None, title="Modalidade")
    tr_nota_aproveitamento: Decimal | None = Field(default=None, ge=0, le=100, title="Nota/Aproveitamento")
    # Exame (ASO) — sem CID/diagnóstico por LGPD
    ex_tipo_aso: TipoASO | None = Field(default=None, title="Tipo de ASO")
    ex_medico_nome: str | None = Field(default=None, max_length=150, title="Médico")
    ex_medico_crm: str | None = Field(default=None, max_length=20, title="CRM")
    ex_clinica_fornecedor_id: int | None = Field(default=None, title="Clínica")
    ex_resultado: ResultadoASO | None = Field(default=None, title="Resultado")
    # Contrato
    ct_valor: Decimal | None = Field(default=None, ge=0, title="Valor")
    ct_objeto: str | None = Field(default=None, max_length=2000, title="Objeto")
    ct_renovacao_automatica: bool = Field(default=False, title="Renovação automática")
    ct_aviso_previo_dias: int | None = Field(default=None, ge=0, le=365, title="Aviso prévio (dias)")
    # Serviço em equipamento
    eq_tipo_servico: TipoServicoEquipamento | None = Field(default=None, title="Tipo de serviço")
    eq_laudo_numero: str | None = Field(default=None, max_length=80, title="Nº do laudo")
    eq_executor_fornecedor_id: int | None = Field(default=None, title="Executor")

    @model_validator(mode="after")
    def _datas(self) -> VencimentoIn:
        if self.data_emissao and self.data_vencimento and self.data_vencimento < self.data_emissao:
            raise ValueError("A data de vencimento não pode ser anterior à data de emissão")
        if self.data_emissao and self.data_emissao > date.today() + timedelta(days=366):
            raise ValueError("Data de emissão muito no futuro")
        return self

    def campos_principais(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if k[:3] not in PREFIXOS_EXTENSAO}

    def campos_extensao(self, prefixo: str) -> dict:
        return {
            k[len(prefixo):]: v for k, v in self.model_dump().items() if k.startswith(prefixo)
        }


class CancelamentoIn(Entrada):
    motivo: str = Field(min_length=5, max_length=1000, title="Motivo")
