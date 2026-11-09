"""Controle de Vencimentos — Segurança do Trabalho.

Executar:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

import streamlit as st  # noqa: E402

from sst.domain.permissoes import Permissao, UsuarioContexto  # noqa: E402
from sst.infra.db.engine import criar_tabelas  # noqa: E402
from sst.logging_config import get_logger, setup_logging  # noqa: E402
from sst.ui import estado, marca  # noqa: E402
from sst.ui.pages import (  # noqa: E402
    administracao,
    cadastros,
    catalogo,
    conta,
    dashboard,
    pendencias,
    treinamentos,
    vencimentos,
)

st.set_page_config(page_title="Controle de Vencimentos SST · NOLTH",
                   page_icon=str(marca.ICONE) if marca.ICONE.exists() else "🦺", layout="wide")
marca.aplicar()
setup_logging()
log = get_logger("app")


@st.cache_resource(show_spinner=False)
def _preparar_banco() -> bool:
    """Executado uma vez por processo: garante que as tabelas existem."""
    criar_tabelas()
    log.info("Banco verificado")
    return True


def _pagina(fn, ctx: UsuarioContexto, titulo: str, icone: str, url: str, padrao: bool = False) -> st.Page:
    def _run() -> None:
        fn(ctx)

    _run.__name__ = f"pg_{url}"
    return st.Page(_run, title=titulo, icon=icone, url_path=url, default=padrao)


def _sidebar(ctx: UsuarioContexto) -> None:
    with st.sidebar:
        marca.marca_lateral()
        st.markdown(f"**{ctx.nome}**  \n{ctx.perfil.rotulo}")
        if ctx.restrito_por_unidade:
            st.caption(f"Acesso restrito a {len(ctx.unidades_ids)} unidade(s)")
        if st.button("Sair", key="logout"):
            estado.encerrar_sessao()
            st.rerun()
        marca.rodape()


def main() -> None:
    try:
        _preparar_banco()
    except Exception:
        log.exception("Falha ao preparar o banco")
        st.error("Não foi possível acessar o banco de dados. Verifique a configuração (SST_DATABASE_URL) e os logs.")
        st.stop()

    ctx = estado.contexto_atual()
    if ctx is None:
        st.navigation([st.Page(conta.pagina_login, title="Entrar", icon="🔐", url_path="login")],
                      position="hidden").run()
        return

    if estado.deve_trocar_senha():
        st.navigation([_pagina(conta.pagina_troca_obrigatoria, ctx, "Definir senha", "🔐", "senha", True)],
                      position="hidden").run()
        return

    paginas: dict[str, list[st.Page]] = {
        "Visão geral": [
            _pagina(dashboard.pagina, ctx, "Painel", "📊", "painel", True),
            _pagina(pendencias.pagina, ctx, "Pendências", "🚩", "pendencias"),
        ],
        "Controle": [
            _pagina(vencimentos.pagina, ctx, "Vencimentos", "🗓️", "vencimentos"),
            _pagina(treinamentos.pagina, ctx, "Treinamentos", "🎓", "treinamentos"),
        ],
        "Cadastros": [
            _pagina(cadastros.pagina_colaboradores, ctx, "Colaboradores", "👷", "colaboradores"),
            _pagina(cadastros.pagina_equipamentos, ctx, "Equipamentos", "🧯", "equipamentos"),
            _pagina(cadastros.pagina_fornecedores, ctx, "Fornecedores", "🤝", "fornecedores"),
            _pagina(cadastros.pagina_estrutura, ctx, "Estrutura da empresa", "🏢", "estrutura"),
            _pagina(catalogo.pagina, ctx, "Tipos de controle", "📚", "tipos"),
        ],
    }
    admin: list[st.Page] = []
    if ctx.pode(Permissao.GERENCIAR_USUARIOS):
        admin.append(_pagina(administracao.pagina_usuarios, ctx, "Usuários", "🔑", "usuarios"))
    if ctx.pode(Permissao.ADMINISTRAR):
        admin.append(_pagina(administracao.pagina_auditoria, ctx, "Auditoria", "🧾", "auditoria"))
        admin.append(_pagina(administracao.pagina_configuracoes, ctx, "Configurações", "⚙️", "configuracoes"))
    if admin:
        paginas["Administração"] = admin
    paginas["Conta"] = [_pagina(conta.pagina_minha_conta, ctx, "Minha conta", "👤", "conta")]

    _sidebar(ctx)
    st.navigation(paginas).run()


main()
