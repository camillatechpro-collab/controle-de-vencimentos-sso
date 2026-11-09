"""Estado de sessão do usuário (login, timeout, mensagens entre reruns)."""

from __future__ import annotations

import time

import streamlit as st

from sst.config import get_settings
from sst.domain.exceptions import SSTError
from sst.domain.permissoes import UsuarioContexto
from sst.logging_config import get_logger
from sst.services.auth_service import AuthService

log = get_logger(__name__)

_CTX = "_sst_ctx"
_TROCAR = "_sst_trocar_senha"
_ULTIMO = "_sst_ultimo_acesso"
_FLASH = "_sst_flash"
_AVISO = "_sst_aviso_login"


def iniciar_sessao(ctx: UsuarioContexto, deve_trocar_senha: bool) -> None:
    st.session_state[_CTX] = ctx
    st.session_state[_TROCAR] = deve_trocar_senha
    st.session_state[_ULTIMO] = time.monotonic()


def encerrar_sessao(motivo: str | None = None) -> None:
    ctx = st.session_state.get(_CTX)
    if ctx is not None and motivo is None:
        try:
            AuthService.registrar_logout(ctx)
        except Exception:  # logout nunca deve travar a tela
            log.exception("Falha ao registrar logout")
    for chave in list(st.session_state.keys()):
        del st.session_state[chave]
    if motivo:
        st.session_state[_AVISO] = motivo


def contexto_atual() -> UsuarioContexto | None:
    """Retorna o usuário logado ou None. Aplica timeout por inatividade e revalida
    perfil/escopo no banco a cada execução (inativação tem efeito imediato)."""
    ctx: UsuarioContexto | None = st.session_state.get(_CTX)
    if ctx is None:
        return None
    limite = get_settings().sessao_timeout_min * 60
    ultimo = st.session_state.get(_ULTIMO, 0.0)
    if time.monotonic() - ultimo > limite:
        encerrar_sessao("Sua sessão expirou por inatividade. Entre novamente.")
        return None
    try:
        ctx = AuthService.recarregar_contexto(ctx)
    except SSTError as e:
        encerrar_sessao(e.mensagem)
        return None
    st.session_state[_CTX] = ctx
    st.session_state[_ULTIMO] = time.monotonic()
    return ctx


def deve_trocar_senha() -> bool:
    return bool(st.session_state.get(_TROCAR))


def senha_trocada() -> None:
    st.session_state[_TROCAR] = False


def aviso_login() -> str | None:
    return st.session_state.pop(_AVISO, None)


def flash(mensagem: str, tipo: str = "success") -> None:
    """Mensagem exibida após o st.rerun()."""
    st.session_state[_FLASH] = (tipo, mensagem)


def mostrar_flash() -> None:
    item = st.session_state.pop(_FLASH, None)
    if item:
        tipo, msg = item
        {"success": st.success, "info": st.info, "warning": st.warning}.get(tipo, st.info)(msg)
