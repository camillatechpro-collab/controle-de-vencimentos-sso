"""Cria as tabelas do banco e a primeira empresa com seu administrador.

Uso (interativo):
    python scripts/inicializar.py

Uso (não interativo):
    python scripts/inicializar.py --empresa "Minha Empresa" --cnpj 11222333000181 \
        --nome "Administrador" --email admin@empresa.com.br --senha "SenhaForte2026"
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, select  # noqa: E402

from sst.config import get_settings  # noqa: E402
from sst.domain.exceptions import SSTError  # noqa: E402
from sst.infra.db.engine import criar_tabelas, session_scope  # noqa: E402
from sst.infra.db.models import Tenant  # noqa: E402
from sst.logging_config import setup_logging  # noqa: E402
from sst.services.tenant_service import criar_tenant  # noqa: E402


def main() -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Inicializa o banco do Controle de Vencimentos SST")
    p.add_argument("--empresa")
    p.add_argument("--cnpj")
    p.add_argument("--nome")
    p.add_argument("--email")
    p.add_argument("--senha")
    p.add_argument("--sem-catalogo", action="store_true", help="não cria o catálogo de NRs sugerido")
    p.add_argument("--somente-tabelas", action="store_true")
    a = p.parse_args()

    print(f"Banco: {get_settings().database_url}")
    criar_tabelas()
    print("✔ Tabelas criadas/verificadas.")
    if a.somente_tabelas:
        return 0

    with session_scope() as s:
        existentes = s.scalar(select(func.count()).select_from(Tenant)) or 0
    if existentes and not a.empresa:
        print(f"Já existem {existentes} empresa(s) cadastrada(s). Nada a fazer.")
        print("Para cadastrar outra empresa, informe --empresa e os dados do administrador.")
        return 0

    empresa = a.empresa or input("Nome da empresa: ").strip()
    cnpj = a.cnpj if a.cnpj is not None else input("CNPJ (opcional): ").strip()
    nome = a.nome or input("Nome do administrador: ").strip()
    email = a.email or input("E-mail (login) do administrador: ").strip()
    senha = a.senha or getpass.getpass("Senha (mín. 10 caracteres, letras e números): ")
    if not a.senha and getpass.getpass("Confirme a senha: ") != senha:
        print("✘ As senhas não conferem.")
        return 1
    try:
        tid = criar_tenant(empresa, cnpj or None, nome, email, senha, semear_catalogo=not a.sem_catalogo)
    except SSTError as e:
        print(f"✘ {e.mensagem}")
        return 1
    print(f"✔ Empresa criada (id {tid}). Acesse com o e-mail {email.lower()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
