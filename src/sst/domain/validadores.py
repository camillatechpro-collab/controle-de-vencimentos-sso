"""Validadores puros: CPF, CNPJ (numérico e alfanumérico), e-mail, senha."""

from __future__ import annotations

import re

_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def somente_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def validar_cpf(cpf: str | None) -> bool:
    numeros = somente_digitos(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(numeros[tamanho]):
            return False
    return True


def formatar_cpf(cpf: str | None) -> str:
    n = somente_digitos(cpf)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else (cpf or "")


def mascarar_cpf(cpf: str | None) -> str:
    """LGPD: exibe só os dígitos centrais (***.456.789-**)."""
    n = somente_digitos(cpf)
    return f"***.{n[3:6]}.{n[6:9]}-**" if len(n) == 11 else ""


def normalizar_cnpj(cnpj: str | None) -> str:
    """Remove pontuação e coloca em maiúsculas (suporta CNPJ alfanumérico)."""
    return re.sub(r"[^0-9A-Za-z]", "", cnpj or "").upper()


def validar_cnpj(cnpj: str | None) -> bool:
    """Valida CNPJ numérico e o novo CNPJ alfanumérico (IN RFB 2.229/2024):
    12 primeiros caracteres em [0-9A-Z], 2 dígitos verificadores numéricos.
    Valor de cada caractere = código ASCII − 48."""
    c = normalizar_cnpj(cnpj)
    if len(c) != 14 or not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c):
        return False
    if c == c[0] * 14:
        return False
    valores = [ord(ch) - 48 for ch in c]
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(v * p for v, p in zip(valores[:pos], pesos, strict=True))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if dv != valores[pos]:
            return False
    return True


def formatar_cnpj(cnpj: str | None) -> str:
    c = normalizar_cnpj(cnpj)
    if len(c) != 14:
        return cnpj or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def validar_email(email: str | None) -> bool:
    return bool(email) and bool(_RE_EMAIL.match(email.strip()))


def problemas_senha(senha: str) -> list[str]:
    """Política mínima: 10+ caracteres, ao menos uma letra e um número."""
    erros: list[str] = []
    if len(senha) < 10:
        erros.append("a senha deve ter pelo menos 10 caracteres")
    if not re.search(r"[A-Za-z]", senha):
        erros.append("a senha deve conter letras")
    if not re.search(r"\d", senha):
        erros.append("a senha deve conter números")
    return erros
