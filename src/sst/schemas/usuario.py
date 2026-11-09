from __future__ import annotations

from pydantic import Field, field_validator

from sst.domain.enums import Perfil
from sst.domain.validadores import validar_email
from sst.schemas.base import Entrada


class UsuarioIn(Entrada):
    nome: str = Field(min_length=3, max_length=150, title="Nome")
    email: str = Field(title="E-mail")
    perfil: Perfil = Field(title="Perfil")
    unidades_ids: list[int] = Field(default_factory=list, title="Unidades permitidas")
    ativo: bool = Field(default=True, title="Ativo")

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not validar_email(v):
            raise ValueError("e-mail inválido")
        return v

    @field_validator("perfil")
    @classmethod
    def _perfil(cls, v: Perfil) -> Perfil:
        if v is Perfil.SUPERADMIN:
            raise ValueError("perfil não pode ser atribuído pela interface")
        return v
