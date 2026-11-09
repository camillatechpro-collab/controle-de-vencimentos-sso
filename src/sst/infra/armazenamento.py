"""Armazenamento seguro de anexos em disco.

- tipo validado pela assinatura do arquivo (magic bytes), não pela extensão
- nome físico aleatório (UUID), fora de qualquer pasta servida
- proteção contra path traversal na leitura
- SHA-256 para integridade
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sst.config import get_settings
from sst.domain.exceptions import ValidacaoError

# assinatura → (mime, extensão)
_ASSINATURAS: list[tuple[bytes, str, str]] = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
]
EXTENSOES_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg"}


@dataclass(frozen=True)
class ArquivoSalvo:
    caminho_relativo: str
    mime_type: str
    tamanho_bytes: int
    sha256: str


def detectar_tipo(conteudo: bytes) -> tuple[str, str] | None:
    for assinatura, mime, ext in _ASSINATURAS:
        if conteudo.startswith(assinatura):
            return mime, ext
    return None


def nome_seguro(nome: str) -> str:
    """Mantém só o nome-base (sem diretórios) e remove caracteres de controle."""
    base = Path(nome.replace("\\", "/")).name
    limpo = "".join(c for c in base if c.isprintable() and c not in '<>:"|?*')
    return (limpo or "arquivo")[:200]


def validar_arquivo(nome_original: str, conteudo: bytes) -> tuple[str, str]:
    settings = get_settings()
    if not conteudo:
        raise ValidacaoError("Arquivo vazio.")
    if len(conteudo) > settings.anexo_max_bytes:
        raise ValidacaoError(f"Arquivo maior que o limite de {settings.anexo_max_mb} MB.")
    ext_nome = Path(nome_original).suffix.lower()
    if ext_nome not in EXTENSOES_PERMITIDAS:
        raise ValidacaoError("Tipo de arquivo não permitido. Envie PDF, PNG ou JPG.")
    detectado = detectar_tipo(conteudo)
    if detectado is None:
        raise ValidacaoError("O conteúdo do arquivo não corresponde a PDF, PNG ou JPG.")
    return detectado


def salvar(tenant_id: int, nome_original: str, conteudo: bytes) -> ArquivoSalvo:
    mime, ext = validar_arquivo(nome_original, conteudo)
    base = get_settings().anexos_dir.resolve()
    pasta = base / str(int(tenant_id))
    pasta.mkdir(parents=True, exist_ok=True)
    relativo = f"{int(tenant_id)}/{uuid.uuid4().hex}{ext}"
    destino = base / relativo
    with open(destino, "xb") as f:  # 'x' nunca sobrescreve
        f.write(conteudo)
    return ArquivoSalvo(relativo, mime, len(conteudo), hashlib.sha256(conteudo).hexdigest())


def _resolver(caminho_relativo: str) -> Path:
    base = get_settings().anexos_dir.resolve()
    alvo = (base / caminho_relativo).resolve()
    if not alvo.is_relative_to(base):
        raise ValidacaoError("Caminho de anexo inválido.")
    return alvo


def ler(caminho_relativo: str, sha256_esperado: str | None = None) -> bytes:
    alvo = _resolver(caminho_relativo)
    if not alvo.is_file():
        raise ValidacaoError("Arquivo do anexo não encontrado no armazenamento.")
    conteudo = alvo.read_bytes()
    if sha256_esperado and hashlib.sha256(conteudo).hexdigest() != sha256_esperado:
        raise ValidacaoError("Falha de integridade: o arquivo foi alterado fora do sistema.")
    return conteudo


def remover(caminho_relativo: str) -> None:
    alvo = _resolver(caminho_relativo)
    if alvo.is_file():
        alvo.unlink()
