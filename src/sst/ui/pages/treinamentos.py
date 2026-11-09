"""Guia Treinamentos: realizados, turmas, nova turma, catálogo de NRs e relatórios."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from sst.domain.enums import Modalidade, StatusVencimento, ValidadeUnidade
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.services.treinamento_service import TreinamentoService
from sst.services.vencimento_service import VencimentoService
from sst.ui import estado, opcoes
from sst.ui.componentes import ColunaTabela, carregar, executar, limpar_valores, status_texto, tabela_pesquisavel
from sst.ui.pages.vencimentos import _painel_anexos, _painel_detalhes

COLUNAS_REALIZADOS = {
    "status": ColunaTabela("Status", "status"),
    "colaborador": ColunaTabela("Colaborador"),
    "setor": ColunaTabela("Setor"),
    "norma": ColunaTabela("NR"),
    "tipo": ColunaTabela("Treinamento"),
    "data_emissao": ColunaTabela("Realização", "data"),
    "data_vencimento": ColunaTabela("Vencimento", "data"),
    "dias_restantes": ColunaTabela("Dias", "numero"),
    "anexos": ColunaTabela("Certificados", "numero"),
    "situacao": ColunaTabela("Situação", "rotulo"),
}


def _painel_participante(ctx: UsuarioContexto, linha: dict) -> None:
    vsvc = VencimentoService(ctx)
    vid = int(linha["id"])
    d = carregar(vsvc.obter, vid, padrao=None)
    if d is None:
        return
    ativo = str(d.get("situacao")).endswith("ATIVO")
    with st.container(border=True):
        st.markdown(f"**{linha.get('colaborador')}** · {d['tipo_nome']} · {status_texto(d['status'])}")
        t1, t2 = st.tabs(["Detalhes", f"Certificado / anexos ({int(linha.get('anexos') or 0)})"])
        with t1:
            _painel_detalhes(d)
        with t2:
            _painel_anexos(ctx, vsvc, vid, ativo)
        st.caption("Ajustes de vencimento individual, renovação e cancelamento: **Vencimentos** ou perfil do colaborador.")


# ---------------------------------------------------------------- abas
def _aba_realizados(ctx: UsuarioContexto, svc: TreinamentoService) -> None:
    catalogo = carregar(svc.catalogo, padrao=pd.DataFrame())
    normas = sorted({n for n in catalogo.get("norma", pd.Series(dtype=str)).dropna().unique()}) if not catalogo.empty else []
    setores = opcoes.setores(ctx)
    colabs = opcoes.colaboradores(ctx, apenas_ativos=False)
    c1, c2, c3, c4 = st.columns(4)
    norma = c1.selectbox("NR", normas, index=None, placeholder="Todas", key="tr_f_norma")
    colaborador_id = c2.selectbox("Colaborador", list(colabs), index=None, placeholder="Todos",
                                  format_func=lambda i: colabs[i], key="tr_f_colab")
    setor_id = c3.selectbox("Setor", list(setores), index=None, placeholder="Todos",
                            format_func=lambda i: setores[i], key="tr_f_setor")
    status_opcoes = [StatusVencimento.VENCIDO.value, StatusVencimento.A_VENCER.value,
                     StatusVencimento.VIGENTE.value, StatusVencimento.SEM_VALIDADE.value]
    status = c4.multiselect("Situação", status_opcoes, format_func=status_texto, placeholder="Todas", key="tr_f_status")
    historico = st.toggle("Incluir histórico (renovados e cancelados)", key="tr_f_hist")
    df = carregar(svc.listar_realizados, norma, colaborador_id, setor_id, status, historico, padrao=None)
    if df is None:
        return
    if not df.empty:
        resumo = df["status"].value_counts()
        st.caption(" · ".join(f"{status_texto(s)}: **{int(resumo.get(s, 0))}**" for s in status_opcoes[:3]))
    sel, _ = tabela_pesquisavel(df, COLUNAS_REALIZADOS, "tr_realizados", ["tipo"], titulo_exportacao="Treinamentos realizados")
    if sel:
        _painel_participante(ctx, sel)


def _aba_turmas(ctx: UsuarioContexto, svc: TreinamentoService) -> None:
    turmas = carregar(svc.listar_turmas, padrao=None)
    if turmas is None:
        return
    if turmas.empty:
        st.info("Nenhuma turma registrada. Use a aba **Nova turma**.")
        return
    sel, _ = tabela_pesquisavel(
        turmas,
        {"data_realizacao": ColunaTabela("Realização", "data"), "norma": ColunaTabela("NR"),
         "treinamento": ColunaTabela("Treinamento"), "participantes": ColunaTabela("Participantes", "numero"),
         "carga_horaria": ColunaTabela("Carga horária", "numero"), "instrutor": ColunaTabela("Instrutor"),
         "instituicao": ColunaTabela("Instituição"), "modalidade": ColunaTabela("Modalidade", "rotulo"),
         "local": ColunaTabela("Local")},
        "tr_turmas", ["treinamento"], titulo_exportacao="Turmas de treinamento",
    )
    if not sel:
        return
    turma_id = int(sel["id"])
    with st.container(border=True):
        st.markdown(f"#### {sel['treinamento']} · {pd.to_datetime(sel['data_realizacao']):%d/%m/%Y}")
        part = carregar(svc.participantes, turma_id, padrao=None)
        if part is None:
            return
        psel, _ = tabela_pesquisavel(part, COLUNAS_REALIZADOS, f"tr_part_{turma_id}", [],
                                     titulo_exportacao=f"Participantes turma {turma_id}")
        if psel:
            _painel_participante(ctx, psel)
        if ctx.pode(Permissao.EDITAR_VENCIMENTOS):
            ja = set(part["colaborador"].dropna()) if not part.empty else set()
            colabs = {i: n for i, n in opcoes.colaboradores(ctx).items() if n.split(" - Mat.")[0] not in ja}
            with st.form(f"tr_add_{turma_id}"):
                novos = st.multiselect("Adicionar participantes", list(colabs), format_func=lambda i: colabs[i],
                                       placeholder="Selecione colaboradores")
                if st.form_submit_button("➕ Adicionar à turma") and novos:
                    ok, r = executar(svc.adicionar_participantes, turma_id, novos)
                    if ok:
                        estado.flash(f"{r['criados']} participante(s) incluído(s), {r['renovados']} como renovação.")
                        st.rerun()


def _aba_nova_turma(ctx: UsuarioContexto, svc: TreinamentoService) -> None:
    treinamentos = carregar(svc.opcoes_treinamentos, padrao={}) or {}
    if not treinamentos:
        st.info("Nenhum treinamento ativo no catálogo. Cadastre em **Cadastros → Tipos de controle** (categoria Treinamento).")
        return
    fornecedores = opcoes.fornecedores(ctx)
    setores = opcoes.setores(ctx)
    filtro_setor = st.multiselect("Filtrar colaboradores por setor (opcional)", list(setores),
                                  format_func=lambda i: setores[i], key="tr_nova_setores")
    colabs = opcoes.colaboradores(ctx)
    if filtro_setor:
        from sst.services.cadastro_service import ColaboradorService

        df = carregar(ColaboradorService(ctx).listar, padrao=pd.DataFrame())
        ids = set(df[df["setor_id"].isin(filtro_setor)]["id"].astype(int)) if not df.empty else set()
        colabs = {i: n for i, n in colabs.items() if i in ids}
    versao = st.session_state.get("tr_nova_v", 0)
    with st.form(f"tr_nova_{versao}"):
        c1, c2 = st.columns(2)
        dados = {
            "tipo_controle_id": c1.selectbox("Treinamento *", list(treinamentos), index=None,
                                             format_func=lambda i: treinamentos[i], placeholder="Selecione"),
            "data_realizacao": c2.date_input("Data de realização *", value=date.today(), format="DD/MM/YYYY"),
            "carga_horaria": c1.number_input("Carga horária (h)", min_value=1, step=1, value=None,
                                             help="Vazio = carga horária padrão do catálogo"),
            "instrutor": c2.text_input("Instrutor"),
            "instituicao_fornecedor_id": c1.selectbox("Instituição", list(fornecedores), index=None,
                                                      format_func=lambda i: fornecedores[i], placeholder="Opcional"),
            "modalidade": c2.selectbox("Modalidade", list(Modalidade.opcoes()), index=None,
                                       format_func=lambda m: Modalidade(m).rotulo, placeholder="Opcional"),
            "local": c1.text_input("Local"),
            "numero_certificado": c2.text_input("Nº do certificado (se único para a turma)"),
            "observacoes": st.text_area("Observações", height=70),
        }
        participantes = st.multiselect("Participantes *", list(colabs), format_func=lambda i: colabs[i],
                                       placeholder="Selecione os colaboradores")
        st.caption("Cada participante recebe o próprio vencimento, calculado pela validade do treinamento. "
                   "Quem já tem este treinamento ativo fica com o anterior no histórico (renovação). "
                   "Os certificados individuais são anexados na aba **Turmas**, em cada participante.")
        if st.form_submit_button("💾 Registrar turma", type="primary"):
            ok, r = executar(svc.registrar_turma, limpar_valores(dados), participantes)
            if ok:
                _, res = r
                st.session_state["tr_nova_v"] = versao + 1
                estado.flash(f"Turma registrada: {res['criados']} novo(s) registro(s) e {res['renovados']} renovação(ões).")
                st.rerun()


def _aba_catalogo(svc: TreinamentoService) -> None:
    df = carregar(svc.catalogo, padrao=None)
    if df is None:
        return
    if df.empty:
        st.info("Nenhum treinamento no catálogo.")
        return
    df = df.assign(validade=[
        "Sem validade" if u == ValidadeUnidade.SEM_VALIDADE.value
        else "Informada manualmente" if u == ValidadeUnidade.MANUAL.value
        else f"{int(v)} {ValidadeUnidade(u).rotulo.lower()}" if v is not None and not pd.isna(v) else "—"
        for v, u in zip(df["validade_valor"], df["validade_unidade"], strict=True)
    ])
    tabela_pesquisavel(
        df, {"norma": ColunaTabela("NR"), "nome": ColunaTabela("Treinamento"), "validade": ColunaTabela("Validade"),
             "carga_horaria_padrao": ColunaTabela("Carga horária padrão", "numero"),
             "antecedencia_dias": ColunaTabela("Alerta (dias antes)", "numero"),
             "exige_anexo": ColunaTabela("Exige certificado", "bool"), "ativo": ColunaTabela("Ativo", "bool")},
        "tr_catalogo", ["norma"], titulo_exportacao="Catalogo de treinamentos", selecionavel=False,
    )
    st.caption("Para incluir ou alterar treinamentos e NRs, use **Cadastros → Tipos de controle** (categoria Treinamento).")


def _aba_relatorios(svc: TreinamentoService) -> None:
    df = carregar(svc.listar_realizados, padrao=None)
    if df is None:
        return
    if df.empty:
        st.info("Nenhum treinamento registrado.")
        return
    colunas_status = {"VENCIDO": ColunaTabela("🔴 Vencidos", "numero"), "A_VENCER": ColunaTabela("🟡 A vencer", "numero"),
                      "VIGENTE": ColunaTabela("🟢 Vigentes", "numero"), "SEM_VALIDADE": ColunaTabela("Sem validade", "numero"),
                      "total": ColunaTabela("Total", "numero")}
    st.markdown("##### Por NR")
    tabela_pesquisavel(svc.resumo_por(df, "norma"), {"norma": ColunaTabela("NR"), **colunas_status},
                       "tr_rel_nr", titulo_exportacao="Treinamentos por NR", selecionavel=False)
    st.markdown("##### Por setor")
    tabela_pesquisavel(svc.resumo_por(df, "setor"), {"setor": ColunaTabela("Setor"), **colunas_status},
                       "tr_rel_setor", titulo_exportacao="Treinamentos por setor", selecionavel=False)
    st.markdown("##### Vencidos e a vencer")
    criticos = df[df["status"].isin([StatusVencimento.VENCIDO.value, StatusVencimento.A_VENCER.value])]
    if criticos.empty:
        st.success("Nenhum treinamento vencido ou a vencer. 👏")
    else:
        tabela_pesquisavel(criticos, COLUNAS_REALIZADOS, "tr_rel_criticos", ["status", "norma"],
                           titulo_exportacao="Treinamentos vencidos e a vencer", selecionavel=False)
    st.caption(f"Base: {len(df)} treinamento(s) vigente(s) por colaborador, situação calculada na data de hoje. "
               "Use **⬇️ Excel** em cada tabela para exportar.")


def pagina(ctx: UsuarioContexto) -> None:
    st.title("🎓 Treinamentos")
    estado.mostrar_flash()
    svc = TreinamentoService(ctx)
    abas = ["Realizados", "Turmas"]
    if ctx.pode(Permissao.EDITAR_VENCIMENTOS):
        abas.append("Nova turma")
    abas += ["Catálogo de NRs", "Relatórios"]
    t = dict(zip(abas, st.tabs(abas), strict=True))
    with t["Realizados"]:
        _aba_realizados(ctx, svc)
    with t["Turmas"]:
        _aba_turmas(ctx, svc)
    if "Nova turma" in t:
        with t["Nova turma"]:
            _aba_nova_turma(ctx, svc)
    with t["Catálogo de NRs"]:
        _aba_catalogo(svc)
    with t["Relatórios"]:
        _aba_relatorios(svc)
