"""Perfil do colaborador: dados cadastrais, ASOs, treinamentos, anexos e histórico de renovações."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import streamlit as st

from sst.domain.datas import formatar_data
from sst.domain.enums import AlvoTipo, Categoria, SituacaoVencimento, StatusVencimento, TipoASO, ValidadeUnidade
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.services.cadastro_service import ColaboradorService
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService
from sst.ui import estado, opcoes
from sst.ui.componentes import ColunaTabela, carregar, executar, limpar_valores, rotulo, tabela_pesquisavel
from sst.ui.pages.vencimentos import _painel_anexos, _painel_detalhes

TODAS = [s.value for s in SituacaoVencimento]

COLUNAS_REGISTROS = {
    "status": ColunaTabela("Status", "status"),
    "tipo": ColunaTabela("Tipo"),
    "data_emissao": ColunaTabela("Realização", "data"),
    "data_vencimento": ColunaTabela("Vencimento", "data"),
    "dias_restantes": ColunaTabela("Dias", "numero"),
    "numero_documento": ColunaTabela("Nº documento"),
    "anexos": ColunaTabela("Anexos", "numero"),
    "situacao": ColunaTabela("Situação", "rotulo"),
}


def _dados_cadastrais(ctx: UsuarioContexto, svc: ColaboradorService, p: dict) -> None:
    chave_cpf = f"perfil_cpf_{p['id']}"
    cpf = st.session_state.get(chave_cpf) or p["cpf_mascarado"]
    with st.container(border=True):
        st.markdown("##### Dados cadastrais")
        campos = [
            ("Empresa", p.get("empresa")), ("Unidade", p.get("unidade")), ("Setor", p.get("setor")),
            ("Cargo", p.get("cargo")), ("Matrícula", p.get("matricula")), ("CPF", cpf),
            ("Admissão", formatar_data(p.get("data_admissao"))), ("Situação", rotulo(p.get("situacao"))),
            ("Desligamento", formatar_data(p.get("data_desligamento"))), ("E-mail", p.get("email")),
            ("Telefone", p.get("telefone")),
        ]
        cols = st.columns(3)
        for i, (k, v) in enumerate(campos):
            texto = str(v).replace("*", r"\*") if v else "—"
            cols[i % 3].markdown(f"**{k}:** {texto}")
        if ctx.pode(Permissao.EDITAR_CADASTROS) and chave_cpf not in st.session_state:
            if st.button("👁️ Mostrar CPF completo", key=f"btn_cpf_{p['id']}",
                         help="Dado pessoal (LGPD): a visualização fica registrada na auditoria."):
                ok, r = executar(svc.revelar_cpf, int(p["id"]))
                if ok:
                    st.session_state[chave_cpf] = r
                    st.rerun()


def _lista_com_detalhe(ctx: UsuarioContexto, vsvc: VencimentoService, df: pd.DataFrame, chave: str, vazio: str) -> None:
    historico = st.toggle("Incluir registros anteriores (renovados e cancelados)", key=f"{chave}__hist")
    if not historico:
        df = df[df["situacao"] == SituacaoVencimento.ATIVO.value]
    if df.empty:
        st.info(vazio)
        return
    selecionado, _ = tabela_pesquisavel(df, COLUNAS_REGISTROS, chave, ["status", "tipo"],
                                        titulo_exportacao=chave)
    if not selecionado:
        return
    vid = int(selecionado["id"])
    d = carregar(vsvc.obter, vid, padrao=None)
    if d is None:
        return
    ativo = str(d.get("situacao")).endswith(SituacaoVencimento.ATIVO.value)
    with st.container(border=True):
        st.markdown(f"**{d['tipo_nome']}**")
        t1, t2, t3 = st.tabs(["Detalhes", f"Anexos ({int(selecionado.get('anexos') or 0)})", "Renovações deste item"])
        with t1:
            _painel_detalhes(d)
        with t2:
            _painel_anexos(ctx, vsvc, vid, ativo)
        with t3:
            hist = carregar(vsvc.historico, vid, padrao=None)
            if hist is not None and not hist.empty:
                tabela_pesquisavel(
                    hist, {"data_emissao": ColunaTabela("Realização", "data"),
                           "data_vencimento": ColunaTabela("Vencimento", "data"),
                           "numero_documento": ColunaTabela("Nº documento"),
                           "situacao": ColunaTabela("Situação", "rotulo")},
                    chave=f"{chave}_hist_{vid}", titulo_exportacao="Renovacoes", selecionavel=False,
                )
        if ativo:
            st.caption("Para renovar com outro documento, use **Novo registro** deste perfil "
                       "(o anterior fica no histórico) ou **Vencimentos → Renovar**.")


def _novo_registro(ctx: UsuarioContexto, vsvc: VencimentoService, colaborador_id: int) -> None:
    tipos = {i: t for i, t in opcoes.tipos_controle(ctx).items() if t["alvo_tipo"] == AlvoTipo.COLABORADOR.value}
    if not tipos:
        st.info("Cadastre tipos de controle para colaboradores em **Cadastros → Tipos de controle**.")
        return
    ordem = sorted(tipos, key=lambda i: (tipos[i]["categoria"] != Categoria.EXAME.value,
                                         tipos[i]["categoria"] != Categoria.TREINAMENTO.value, tipos[i]["nome"]))
    tipo_id = st.selectbox("Tipo *", ordem, index=None, placeholder="Selecione o ASO, treinamento ou outro controle",
                           format_func=lambda i: f"{Categoria(tipos[i]['categoria']).rotulo} · {tipos[i]['nome']}",
                           key=f"perfil_novo_tipo_{colaborador_id}")
    if tipo_id is None:
        return
    tipo = tipos[tipo_id]
    unidade = ValidadeUnidade(tipo["validade_unidade"])
    versao = st.session_state.get(f"perfil_novo_v_{colaborador_id}", 0)
    with st.form(f"perfil_novo_{colaborador_id}_{tipo_id}_{versao}"):
        c1, c2 = st.columns(2)
        dados = {"tipo_controle_id": tipo_id, "colaborador_id": colaborador_id}
        dados["data_emissao"] = c1.date_input("Data de realização *", value=None, format="DD/MM/YYYY")
        if unidade is ValidadeUnidade.MANUAL:
            dados["data_vencimento"] = c2.date_input("Data de vencimento *", value=None, format="DD/MM/YYYY")
        elif unidade is ValidadeUnidade.SEM_VALIDADE:
            c2.caption("Este tipo não tem validade.")
        else:
            c2.caption(f"Vencimento calculado automaticamente: {tipo['validade_valor']} "
                       f"{ValidadeUnidade(tipo['validade_unidade']).rotulo.lower()} após a realização.")
        dados["numero_documento"] = c1.text_input("Nº do documento/certificado")
        if tipo["categoria"] == Categoria.EXAME.value:
            dados["ex_tipo_aso"] = c2.selectbox("Tipo de ASO", list(TipoASO.opcoes()), index=None,
                                                format_func=lambda x: TipoASO(x).rotulo, placeholder="Selecione")
            dados["ex_medico_nome"] = c1.text_input("Médico")
            dados["ex_medico_crm"] = c2.text_input("CRM")
        elif tipo["categoria"] == Categoria.TREINAMENTO.value:
            dados["tr_carga_horaria"] = c2.number_input("Carga horária (h)", min_value=1, step=1,
                                                        value=int(tipo["carga_horaria_padrao"])
                                                        if tipo.get("carga_horaria_padrao") and not pd.isna(tipo["carga_horaria_padrao"]) else None)
            dados["tr_instrutor"] = c1.text_input("Instrutor")
        dados["observacoes"] = st.text_area("Observações", height=70)
        renovar = st.checkbox("Se já houver registro ativo deste tipo, lançar como renovação (o anterior fica no histórico)",
                              value=True)
        st.caption("Depois de salvar, anexe o ASO/certificado no registro, na aba correspondente.")
        enviar = st.form_submit_button("💾 Salvar registro", type="primary")
    if enviar:
        ok, _ = executar(vsvc.criar, limpar_valores(dados), renovar_existente=renovar)
        if ok:
            st.session_state[f"perfil_novo_v_{colaborador_id}"] = versao + 1
            estado.flash("Registro salvo.")
            st.rerun()


def pagina(ctx: UsuarioContexto, colaborador_id: int, voltar: Callable[[], None]) -> None:
    if st.button("← Voltar para a lista de colaboradores", key="perfil_voltar"):
        voltar()
        st.rerun()
    svc = ColaboradorService(ctx)
    vsvc = VencimentoService(ctx)
    p = carregar(svc.perfil, colaborador_id, padrao=None)
    if p is None:
        voltar()
        return
    st.title(f"👤 {p['nome']}")
    st.caption(" · ".join(x for x in (p.get("cargo"), p.get("setor"), p.get("unidade"), rotulo(p.get("situacao"))) if x))
    estado.mostrar_flash()
    _dados_cadastrais(ctx, svc, p)

    df = carregar(vsvc.listar, FiltroVencimentos(colaborador_id=colaborador_id, situacoes=TODAS), padrao=None)
    if df is None:
        return
    ativos = df[df["situacao"] == SituacaoVencimento.ATIVO.value]
    asos = df[df["categoria"] == Categoria.EXAME.value]
    trein = df[df["categoria"] == Categoria.TREINAMENTO.value]
    outros = df[~df["categoria"].isin([Categoria.EXAME.value, Categoria.TREINAMENTO.value])]
    k = st.columns(4)
    k[0].metric("🩺 ASOs vigentes", int((asos["situacao"] == SituacaoVencimento.ATIVO.value).sum()))
    k[1].metric("🎓 Treinamentos vigentes", int((trein["situacao"] == SituacaoVencimento.ATIVO.value).sum()))
    k[2].metric("🔴 Vencidos", int((ativos["status"] == StatusVencimento.VENCIDO.value).sum()))
    k[3].metric("🟡 A vencer", int((ativos["status"] == StatusVencimento.A_VENCER.value).sum()))

    abas = ["🩺 ASOs", "🎓 Treinamentos", "📋 Outros controles", "🕓 Histórico de renovações"]
    pode_lancar = ctx.pode(Permissao.EDITAR_VENCIMENTOS)
    if pode_lancar:
        abas.append("➕ Novo registro")
    t = st.tabs(abas)
    with t[0]:
        _lista_com_detalhe(ctx, vsvc, asos, f"perfil_aso_{colaborador_id}", "Nenhum ASO registrado.")
    with t[1]:
        _lista_com_detalhe(ctx, vsvc, trein, f"perfil_tr_{colaborador_id}", "Nenhum treinamento registrado.")
    with t[2]:
        _lista_com_detalhe(ctx, vsvc, outros, f"perfil_out_{colaborador_id}", "Nenhum outro controle registrado.")
    with t[3]:
        if df.empty:
            st.info("Sem registros.")
        else:
            hist = df.sort_values(["tipo", "data_emissao"], na_position="first")
            tabela_pesquisavel(
                hist,
                {"tipo": ColunaTabela("Tipo"), "categoria": ColunaTabela("Categoria", "rotulo"),
                 "data_emissao": ColunaTabela("Realização", "data"), "data_vencimento": ColunaTabela("Vencimento", "data"),
                 "situacao": ColunaTabela("Situação", "rotulo"), "status": ColunaTabela("Status", "status"),
                 "numero_documento": ColunaTabela("Nº documento"), "anexos": ColunaTabela("Anexos", "numero")},
                chave=f"perfil_hist_{colaborador_id}", filtros=["categoria", "tipo", "situacao"],
                titulo_exportacao=f"Historico {p['nome']}", selecionavel=False,
            )
            st.caption("Cada renovação gera um novo registro; o anterior fica como **Renovado**.")
    if pode_lancar:
        with t[4]:
            _novo_registro(ctx, vsvc, colaborador_id)
