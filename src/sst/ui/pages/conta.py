"""Login, troca de senha obrigatória e 'Minha conta'."""

from __future__ import annotations

import streamlit as st
from sst.domain.permissoes import UsuarioContexto
from sst.services.auth_service import AuthService
from sst.services.tenant_service import existe_empresa
from sst.ui import estado, marca
from sst.ui.componentes import executar


def pagina_login() -> None:
    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        marca.cabecalho_login()
        st.markdown("## 🦺 Controle de Vencimentos")
        st.caption("Segurança do Trabalho · treinamentos, exames, equipamentos, documentos e contratos")
        aviso = estado.aviso_login()
        if aviso:
            st.warning(aviso)
        if not existe_empresa():
            st.info(
                "Nenhuma empresa cadastrada ainda. No terminal, na pasta do projeto, execute:\n\n"
                "`python scripts/inicializar.py`"
            )
        with st.form("login"):
            email = st.text_input("E-mail", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            entrar = st.form_submit_button("Entrar", type="primary")
        if entrar:
            if not email or not senha:
                st.error("Informe e-mail e senha.")
                return
            ok, r = executar(AuthService.autenticar, email, senha)
            if ok:
                ctx, trocar = r
                estado.iniciar_sessao(ctx, trocar)
                st.rerun()
        marca.rodape()


def _form_troca(ctx: UsuarioContexto, chave: str) -> bool:
    with st.form(chave, clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha", type="password", help="Mínimo de 10 caracteres, com letras e números.")
        conf = st.text_input("Confirme a nova senha", type="password")
        enviar = st.form_submit_button("Alterar senha", type="primary")
    if enviar:
        ok, _ = executar(AuthService.trocar_senha, ctx, atual, nova, conf)
        return ok
    return False


def pagina_troca_obrigatoria(ctx: UsuarioContexto) -> None:
    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        st.markdown("## 🔐 Defina sua senha")
        st.info("Por segurança, troque a senha temporária antes de continuar.")
        if _form_troca(ctx, "troca_obrigatoria"):
            estado.senha_trocada()
            estado.flash("Senha alterada. Bem-vindo(a)!")
            st.rerun()
        if st.button("Sair"):
            estado.encerrar_sessao()
            st.rerun()


def pagina_minha_conta(ctx: UsuarioContexto) -> None:
    st.title("👤 Minha conta")
    estado.mostrar_flash()
    st.markdown(f"**Nome:** {ctx.nome}  \n**E-mail:** {ctx.email}  \n**Perfil:** {ctx.perfil.rotulo}")
    st.subheader("Alterar senha")
    if _form_troca(ctx, "troca_conta"):
        estado.flash("Senha alterada com sucesso.")
        st.rerun()
