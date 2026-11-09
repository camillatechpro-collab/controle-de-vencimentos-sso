"""Entrada da turma de treinamento."""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import Field, field_validator

from sst.domain.enums import Modalidade
from sst.schemas.base import Entrada


class TurmaIn(Entrada):
    tipo_controle_id: int = Field(title="Treinamento")
    data_realizacao: date = Field(title="Data de realização")
    carga_horaria: int | None = Field(default=None, ge=1, le=2000, title="Carga horária")
    instrutor: str | None = Field(default=None, max_length=150, title="Instrutor")
    instituicao_fornecedor_id: int | None = Field(default=None, title="Instituição")
    modalidade: Modalidade | None = Field(default=None, title="Modalidade")
    local: str | None = Field(default=None, max_length=150, title="Local")
    numero_certificado: str | None = Field(default=None, max_length=80, title="Nº do certificado")
    observacoes: str | None = Field(default=None, max_length=4000, title="Observações")

    @field_validator("data_realizacao")
    @classmethod
    def _data(cls, v: date) -> date:
        if v > date.today() + timedelta(days=366):
            raise ValueError("Data de realização muito no futuro")
        return v
