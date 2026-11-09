"""Hash de senha com scrypt (biblioteca padrão), comparação em tempo constante."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string

_N, _R, _P, _DKLEN = 2**14, 8, 1, 64
_PREFIXO = "scrypt"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def gerar_hash_senha(senha: str) -> str:
    if not senha:
        raise ValueError("Senha vazia.")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(senha.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{_PREFIXO}${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def verificar_senha(senha: str, hash_armazenado: str | None) -> bool:
    if not senha or not hash_armazenado:
        return False
    try:
        prefixo, n, r, p, salt_b64, dk_b64 = hash_armazenado.split("$")
        if prefixo != _PREFIXO:
            return False
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(dk_b64)
        calculado = hashlib.scrypt(
            senha.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(esperado)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


# Hash fixo usado quando o usuário não existe: iguala o tempo de resposta
# e impede descobrir e-mails cadastrados medindo a latência do login.
HASH_FALSO = gerar_hash_senha("senha-inexistente-" + secrets.token_hex(8))


def gerar_senha_temporaria(tamanho: int = 12) -> str:
    """Gera senha que atende à política (letras + números)."""
    alfabeto = string.ascii_letters + string.digits
    while True:
        senha = "".join(secrets.choice(alfabeto) for _ in range(tamanho))
        if any(c.isdigit() for c in senha) and any(c.isalpha() for c in senha):
            return senha
