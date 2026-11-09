"""Base dos schemas de entrada (Pydantic v2) e tradução de erros para pt-BR."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from sst.domain.exceptions import ValidacaoError

_MENSAGENS = {
    "missing": "campo obrigatório",
    "string_too_short": "texto muito curto",
    "string_too_long": "texto muito longo",
    "int_parsing": "deve ser um número inteiro",
    "int_type": "deve ser um número inteiro",
    "decimal_parsing": "deve ser um número",
    "float_parsing": "deve ser um número",
    "greater_than_equal": "valor abaixo do mínimo permitido",
    "less_than_equal": "valor acima do máximo permitido",
    "date_parsing": "data inválida",
    "date_type": "data inválida",
    "enum": "opção inválida",
    "bool_parsing": "valor inválido",
}


class Entrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _vazio_para_none(cls, dados: Any) -> Any:
        if isinstance(dados, dict):
            return {k: (None if isinstance(v, str) and v.strip() == "" else v) for k, v in dados.items()}
        return dados


def validar(schema: type[Entrada], dados: dict[str, Any]) -> dict[str, Any]:
    """Valida e devolve dicionário limpo; converte erros para ValidacaoError."""
    try:
        return schema.model_validate(dados).model_dump()
    except ValidationError as exc:
        erros: list[str] = []
        for e in exc.errors():
            campo = str(e["loc"][0]) if e["loc"] else ""
            info = schema.model_fields.get(campo)
            rotulo = (info.title if info and info.title else campo.replace("_", " ").capitalize())
            if e["type"] == "value_error":
                msg = str(e.get("ctx", {}).get("error", e["msg"]))
            else:
                msg = _MENSAGENS.get(e["type"], e["msg"])
            erros.append(f"{rotulo}: {msg}" if rotulo else msg)
        raise ValidacaoError(erros) from exc
