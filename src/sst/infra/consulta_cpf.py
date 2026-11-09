"""Ponto de integração para consulta de CPF em fornecedor AUTORIZADO.

Não há fornecedor embutido: CPF não é dado público. A integração só deve ser
feita com um serviço contratado e com base legal (LGPD, art. 7º) — por exemplo,
o próprio eSocial/folha da empresa ou um bureau contratado. Nunca use bases
vazadas ou consultas não autorizadas.

Para integrar: implemente `ProvedorCPF`, registre em `PROVEDORES` e defina
SST_CPF_PROVEDOR=<nome>. Sem configuração, o sistema funciona só com validação
de dígitos e preenchimento manual (a tela não exibe botão de consulta).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sst.config import get_settings


@dataclass
class DadosCPF:
    nome: str | None = None
    situacao: str | None = None


class ProvedorCPF(Protocol):
    nome: str

    def consultar(self, cpf: str) -> DadosCPF:
        """Retorna os dados mínimos necessários. Deve lançar SSTError em caso de falha."""


PROVEDORES: dict[str, ProvedorCPF] = {}


def obter_provedor() -> ProvedorCPF | None:
    nome = get_settings().cpf_provedor
    return PROVEDORES.get(nome) if nome else None
