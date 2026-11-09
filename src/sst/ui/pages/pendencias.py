"""Pendências de conformidade (exigências por cargo não atendidas)."""

from __future__ import annotations

import streamlit as st

from sst.domain.permissoes import UsuarioContexto
from sst.services.conformidade_service import ConformidadeService
from sst.ui import estado, opcoes
from sst.ui.componentes import ColunaTabela, carregar, tabela_pesquisavel


def pagina(ctx: UsuarioContexto) -> None:
    st.title("🚩 Pendências e conformidade")
    estado.mostrar_flash()
    st.caption(
        "Compara as exigências cadastradas para cada cargo com os registros de cada colaborador ativo. "
        "Item **atendido** = registro vigente ou a vencer; **pendente** = sem registro ou vencido."
    )
    unidades = opcoes.unidades(ctx, apenas_ativas=False)
    c1, c2 = st.columns([1, 3])
    unidade_id = c1.selectbox("Unidade", list(unidades), index=None, placeholder="Todas",
                              format_func=lambda i: unidades[i])
    mostrar_todos = c2.toggle("Mostrar também os itens atendidos", value=False)

    svc = ConformidadeService(ctx)
    df = carregar(svc.situacao_exigencias, unidade_id, padrao=None)
    if df is None:
        return
    if df.empty:
        st.info("Nenhuma exigência para calcular. Cadastre em **Tipos de controle → Exigências por cargo** "
                "e vincule cargos aos colaboradores.")
        return

    total, atendidos = len(df), int(df["atendido"].sum())
    k = st.columns(4)
    k[0].metric("✅ Conformidade", f"{100 * atendidos / total:.1f}%".replace(".", ","))
    k[1].metric("Exigências atendidas", atendidos)
    k[2].metric("🔴 Pendentes", total - atendidos)
    k[3].metric("Colaboradores com pendência", int(df.loc[~df["atendido"], "colaborador_id"].nunique()))

    exibir = df if mostrar_todos else df[~df["atendido"]]
    if exibir.empty:
        st.success("Todos os colaboradores estão em conformidade com as exigências dos seus cargos. 👏")
        return
    tabela_pesquisavel(
        exibir,
        {
            "status": ColunaTabela("Situação", "status"),
            "colaborador": ColunaTabela("Colaborador"),
            "matricula": ColunaTabela("Matrícula"),
            "cargo": ColunaTabela("Cargo"),
            "unidade": ColunaTabela("Unidade"),
            "tipo": ColunaTabela("Exigência"),
            "categoria": ColunaTabela("Categoria", "rotulo"),
            "data_vencimento": ColunaTabela("Vencimento", "data"),
        },
        chave="pendencias",
        filtros=["status", "cargo", "tipo"],
        titulo_exportacao="Pendencias",
        selecionavel=False,
    )
    st.caption("Para regularizar, lance o registro em **Vencimentos** (individual ou em lote).")
