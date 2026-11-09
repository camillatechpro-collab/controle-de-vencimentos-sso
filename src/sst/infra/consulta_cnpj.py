"""Consulta de CNPJ em API de dados cadastrais públicos (padrão: BrasilAPI, que
reproduz os dados abertos da Receita Federal). Sem dependências externas.

Falhas (CNPJ inexistente, limite de requisições, API fora do ar, resposta
inválida) viram `ConsultaCNPJError` com mensagem amigável; o usuário sempre pode
preencher os campos manualmente.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass

from sst.config import get_settings
from sst.domain.exceptions import SSTError
from sst.domain.validadores import normalizar_cnpj, validar_cnpj
from sst.logging_config import get_logger

log = get_logger(__name__)


class ConsultaCNPJError(SSTError):
    """Consulta indisponível ou sem resultado: preencha manualmente."""


@dataclass
class DadosCNPJ:
    cnpj: str
    razao_social: str | None
    nome_fantasia: str | None
    endereco: str | None
    cidade: str | None
    uf: str | None
    cep: str | None
    cnae: str | None
    situacao_cadastral: str | None

    def como_dict(self) -> dict:
        return asdict(self)


def _texto(v) -> str | None:
    if v is None:
        return None
    t = " ".join(str(v).split())
    return t or None


def _mapear(cnpj: str, d: dict) -> DadosCNPJ:
    partes = [
        _texto(" ".join(x for x in (d.get("descricao_tipo_de_logradouro"), d.get("logradouro")) if x)),
        _texto(d.get("numero")),
        _texto(d.get("complemento")),
        _texto(d.get("bairro")),
    ]
    endereco = ", ".join(p for p in partes if p) or None
    codigo_cnae = d.get("cnae_fiscal")
    desc_cnae = _texto(d.get("cnae_fiscal_descricao"))
    cnae = None
    if codigo_cnae:
        c = str(codigo_cnae).zfill(7)
        cnae = f"{c[:4]}-{c[4]}/{c[5:]}" + (f" {desc_cnae}" if desc_cnae else "")
    cep = "".join(ch for ch in str(d.get("cep") or "") if ch.isdigit()) or None
    return DadosCNPJ(
        cnpj=cnpj,
        razao_social=_texto(d.get("razao_social")),
        nome_fantasia=_texto(d.get("nome_fantasia")),
        endereco=endereco[:255] if endereco else None,
        cidade=_texto(d.get("municipio")),
        uf=(_texto(d.get("uf")) or "").upper() or None,
        cep=cep[:8] if cep else None,
        cnae=cnae[:255] if cnae else None,
        situacao_cadastral=_texto(d.get("descricao_situacao_cadastral")),
    )


def consultar_cnpj(cnpj: str, abrir: Callable | None = None) -> DadosCNPJ:
    """`abrir` permite substituir o acesso HTTP (testes)."""
    c = normalizar_cnpj(cnpj)
    if not validar_cnpj(c):
        raise ConsultaCNPJError("CNPJ inválido. Confira os dígitos.")
    if not c.isdigit():
        raise ConsultaCNPJError(
            "A consulta automática ainda não atende CNPJ alfanumérico. Preencha os dados manualmente."
        )
    cfg = get_settings()
    url = cfg.cnpj_api_url.format(cnpj=c)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ControleVencimentosSST/1.0"})
    abrir = abrir or urllib.request.urlopen
    try:
        with abrir(req, timeout=cfg.cnpj_api_timeout) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.warning("Consulta CNPJ HTTP %s", e.code)
        if e.code in (400, 404):
            raise ConsultaCNPJError("CNPJ não encontrado na base pública. Confira o número ou preencha manualmente.") from e
        if e.code == 429:
            raise ConsultaCNPJError("Limite de consultas atingido. Aguarde um minuto ou preencha manualmente.") from e
        raise ConsultaCNPJError("Serviço de consulta de CNPJ indisponível no momento. Preencha manualmente.") from e
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        log.warning("Consulta CNPJ indisponível: %s", e)
        raise ConsultaCNPJError("Não foi possível acessar o serviço de consulta (sem internet ou serviço fora do ar). "
                                "Preencha manualmente.") from e
    except (ValueError, UnicodeDecodeError) as e:
        raise ConsultaCNPJError("Resposta inválida do serviço de consulta. Preencha manualmente.") from e
    if not isinstance(dados, dict) or not dados.get("razao_social"):
        raise ConsultaCNPJError("CNPJ não encontrado na base pública. Preencha manualmente.")
    return _mapear(c, dados)
