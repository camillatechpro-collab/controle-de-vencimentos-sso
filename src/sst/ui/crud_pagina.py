"""Página CRUD genérica: lista com pesquisa/filtros + formulário de inclusão/edição + exclusão."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import streamlit as st

from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.ui import estado
from sst.ui.componentes import (
    Campo,
    ColunaTabela,
    carregar,
    confirmar,
    executar,
    limpar_valores,
    render_campos,
    tabela_pesquisavel,
)


@dataclass
class ConfigCrud:
    chave: str
    titulo_singular: str
    service_cls: type
    campos: Callable[[UsuarioContexto], list[Campo]]
    colunas: dict[str, ColunaTabela]
    filtros: list[str] = field(default_factory=list)
    rotulo_registro: Callable[[dict], str] = lambda r: str(r.get("nome", r.get("id")))
    perm_escrita: Permissao = Permissao.EDITAR_CADASTROS
    detalhe_extra: Callable[[UsuarioContexto, dict], None] | None = None
    ajuda: str | None = None
    # clicar numa célula desta coluna chama `ao_clicar` (ex.: nome → perfil)
    coluna_clicavel: str | None = None
    ao_clicar: Callable[[UsuarioContexto, dict], None] | None = None
    # consulta de CNPJ: recebe (dados da API, valores atuais) e devolve os campos a preencher
    consulta_cnpj: Callable[[dict, dict], dict] | None = None


def _chave_modo(cfg: ConfigCrud) -> str:
    return f"{cfg.chave}__modo"


def _chave_versao(cfg: ConfigCrud) -> str:
    return f"{cfg.chave}__versao"


def _chave_prefill(cfg: ConfigCrud) -> str:
    return f"{cfg.chave}__prefill"


def _consulta_cnpj(ctx: UsuarioContexto, cfg: ConfigCrud, valores: dict) -> None:
    """Busca dados públicos do CNPJ e preenche o formulário (o usuário pode editar tudo)."""
    from sst.services.cadastro_service import consultar_cnpj_publico

    versao = st.session_state.get(_chave_versao(cfg), 0)
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        cnpj = c1.text_input("CNPJ para consulta", value=valores.get("cnpj") or "",
                             key=f"{cfg.chave}__cnpj_consulta_{versao}",
                             help="Busca razão social, nome fantasia, endereço, CNAE e situação cadastral em base pública.")
        c2.write("")
        c2.write("")
        if c2.button("🔎 Consultar CNPJ", key=f"{cfg.chave}__btn_cnpj_{versao}"):
            ok, r = executar(consultar_cnpj_publico, ctx, cnpj)
            if ok:
                st.session_state[_chave_prefill(cfg)] = {
                    **cfg.consulta_cnpj(r, valores), "_situacao": r.get("situacao_cadastral"),
                }
                st.session_state[_chave_versao(cfg)] = versao + 1
                st.rerun()
        situacao = st.session_state.get(_chave_prefill(cfg), {}).get("_situacao")
        if situacao:
            (st.success if situacao.upper() == "ATIVA" else st.warning)(
                f"Dados preenchidos pela consulta. Situação cadastral na Receita: **{situacao}**. "
                "Revise e salve."
            )
        else:
            st.caption("Sem internet ou API indisponível? Preencha os campos manualmente.")


def _fechar_form(cfg: ConfigCrud) -> None:
    st.session_state.pop(_chave_prefill(cfg), None)
    st.session_state[_chave_modo(cfg)] = None
    # nova versão = novas chaves de widget = formulário limpo na próxima abertura
    st.session_state[_chave_versao(cfg)] = st.session_state.get(_chave_versao(cfg), 0) + 1


def _formulario(ctx: UsuarioContexto, cfg: ConfigCrud, service, modo: tuple[str, int | None]) -> None:
    acao, ident = modo
    valores: dict[str, Any] = {}
    if acao == "editar" and ident is not None:
        valores = carregar(service.obter, ident, padrao=None)
        if valores is None:
            _fechar_form(cfg)
            return
    titulo = f"Novo(a) {cfg.titulo_singular.lower()}" if acao == "novo" else f"Editar {cfg.titulo_singular.lower()}"
    prefill = {k: v for k, v in st.session_state.get(_chave_prefill(cfg), {}).items() if not k.startswith("_")}
    valores = {**valores, **prefill}
    with st.container(border=True):
        st.subheader(titulo)
        if cfg.consulta_cnpj:
            _consulta_cnpj(ctx, cfg, valores)
        versao = st.session_state.get(_chave_versao(cfg), 0)
        with st.form(f"{cfg.chave}__form_{acao}_{ident}_{versao}", clear_on_submit=False):
            dados = render_campos(cfg.campos(ctx), valores, f"{cfg.chave}_{acao}_{ident}_{versao}")
            st.caption("* campos obrigatórios")
            c1, c2, _ = st.columns([1, 1, 4])
            salvar = c1.form_submit_button("💾 Salvar", type="primary")
            cancelar = c2.form_submit_button("Cancelar")
        if cancelar:
            _fechar_form(cfg)
            st.rerun()
        if salvar:
            dados = limpar_valores(dados)
            if acao == "novo":
                ok, _ = executar(service.criar, dados)
                msg = f"{cfg.titulo_singular} cadastrado(a) com sucesso."
            else:
                ok, _ = executar(service.atualizar, ident, dados)
                msg = f"{cfg.titulo_singular} atualizado(a) com sucesso."
            if ok:
                estado.flash(msg)
                _fechar_form(cfg)
                st.rerun()


def pagina_crud(ctx: UsuarioContexto, cfg: ConfigCrud) -> None:
    service = cfg.service_cls(ctx)
    pode_editar = ctx.pode(cfg.perm_escrita)
    estado.mostrar_flash()
    if cfg.ajuda:
        st.caption(cfg.ajuda)

    modo = st.session_state.get(_chave_modo(cfg))
    if modo:
        _formulario(ctx, cfg, service, modo)
        return

    if pode_editar and st.button(f"➕ Novo(a) {cfg.titulo_singular.lower()}", key=f"{cfg.chave}__novo", type="primary"):
        st.session_state[_chave_modo(cfg)] = ("novo", None)
        st.rerun()

    df = carregar(service.listar, padrao=None)
    if df is None:
        return
    selecionado, _ = tabela_pesquisavel(df, cfg.colunas, cfg.chave, cfg.filtros, titulo_exportacao=cfg.titulo_singular,
                                        coluna_clicavel=cfg.coluna_clicavel if cfg.ao_clicar else None)
    clicado = st.session_state.pop(f"{cfg.chave}__clicado", None)
    if clicado and cfg.ao_clicar:
        cfg.ao_clicar(ctx, clicado)
        return
    if not selecionado:
        return

    ident = int(selecionado["id"])
    with st.container(border=True):
        rotulo_sel = cfg.rotulo_registro(selecionado).replace("*", "\\*")
        st.markdown(f"**Selecionado:** {rotulo_sel}")
        if pode_editar:
            c1, c2 = st.columns([1, 3])
            if c1.button("✏️ Editar", key=f"{cfg.chave}__editar_{ident}"):
                st.session_state[_chave_modo(cfg)] = ("editar", ident)
                st.rerun()
            with c2.expander("🗑️ Excluir"):
                st.caption("O registro vai para a lixeira e pode ser restaurado por um administrador.")
                if confirmar(f"{cfg.chave}__excluir_{ident}", "Confirmo a exclusão deste registro", "Excluir"):
                    ok, _ = executar(service.excluir, ident)
                    if ok:
                        estado.flash(f"{cfg.titulo_singular} excluído(a).")
                        st.rerun()
        if cfg.detalhe_extra:
            cfg.detalhe_extra(ctx, selecionado)
