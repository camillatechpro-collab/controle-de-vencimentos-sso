"""Dashboard: indicadores, gráficos e lista de ação imediata."""

from __future__ import annotations

import streamlit as st

from sst.domain.enums import Categoria
from sst.domain.permissoes import UsuarioContexto
from sst.services.dashboard_service import DashboardService
from sst.ui import estado, graficos, opcoes
from sst.ui.componentes import ColunaTabela, carregar, tabela_pesquisavel


def _resumo_treinamentos(ctx: UsuarioContexto, df) -> None:
    """Linha de treinamentos (integração com a guia Treinamentos)."""
    from datetime import date, timedelta

    import pandas as pd

    from sst.services.treinamento_service import TreinamentoService

    tr = df[df["categoria"] == Categoria.TREINAMENTO.value] if not df.empty else df
    turmas = carregar(TreinamentoService(ctx).listar_turmas, padrao=None)
    recentes = 0
    if turmas is not None and not turmas.empty:
        recentes = int((pd.to_datetime(turmas["data_realizacao"]).dt.date >= date.today() - timedelta(days=365)).sum())
    vencidos = int((tr["status"] == "VENCIDO").sum()) if not tr.empty else 0
    a_vencer = int((tr["status"] == "A_VENCER").sum()) if not tr.empty else 0
    st.caption(f"🎓 **Treinamentos:** {vencidos} vencido(s) · {a_vencer} a vencer · "
               f"{len(tr)} vigente(s) por colaborador · {recentes} turma(s) nos últimos 12 meses — detalhes na guia **Treinamentos**.")


def pagina(ctx: UsuarioContexto) -> None:
    st.title("📊 Painel de vencimentos")
    estado.mostrar_flash()
    svc = DashboardService(ctx)

    # filtros numa única linha acima dos gráficos
    unidades = opcoes.unidades(ctx, apenas_ativas=False)
    c1, c2, _ = st.columns([1, 1, 2])
    unidade_id = c1.selectbox("Unidade", list(unidades), index=None, placeholder="Todas",
                              format_func=lambda i: unidades[i])
    categoria = c2.selectbox("Categoria", list(Categoria.opcoes()), index=None, placeholder="Todas",
                             format_func=lambda c: Categoria(c).rotulo)

    df = carregar(svc.base, unidade_id, categoria, padrao=None)
    if df is None:
        return
    ind = carregar(svc.indicadores, df, unidade_id, padrao=None)
    if ind is None:
        return

    k = st.columns(6)
    k[0].metric("🔴 Vencidos", ind.vencidos)
    k[1].metric("🟡 A vencer", ind.a_vencer, help="Dentro da antecedência configurada em cada tipo de controle")
    k[2].metric("📅 Próximos 30 dias", ind.vencendo_30)
    k[3].metric("🟢 Vigentes", ind.vigentes)
    k[4].metric("📎 Sem anexo obrigatório", ind.pendentes_anexo)
    if ind.conformidade_pct is None:
        k[5].metric("✅ Conformidade", "—", help="Cadastre a matriz de exigências por cargo para calcular")
    else:
        k[5].metric("✅ Conformidade", f"{ind.conformidade_pct:.1f}%".replace(".", ","),
                    help=f"{ind.exigencias_atendidas} de {ind.exigencias_total} exigências por cargo atendidas")

    if categoria in (None, Categoria.TREINAMENTO.value):
        _resumo_treinamentos(ctx, df)

    if df.empty:
        st.info("Nenhum vencimento ativo para os filtros escolhidos. Comece em **Vencimentos → Novo lançamento**.")
        return

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### Itens ativos por status")
        st.plotly_chart(graficos.barras_status(svc.por_status(df)), key="g_status",
                        config={"displayModeBar": False})
    with g2:
        st.markdown("##### Vencimentos nos próximos 12 meses")
        st.plotly_chart(graficos.barras_mensais(svc.proximos_12_meses(df)), key="g_meses",
                        config={"displayModeBar": False})

    g3, g4 = st.columns(2)
    with g3:
        st.markdown("##### Por categoria")
        st.plotly_chart(graficos.barras_empilhadas_status(svc.por_categoria_status(df), "categoria", "Itens"),
                        key="g_cat", config={"displayModeBar": False})
    with g4:
        st.markdown("##### Por unidade")
        st.plotly_chart(graficos.barras_empilhadas_status(svc.por_unidade(df), "unidade", "Itens"),
                        key="g_un", config={"displayModeBar": False})

    st.markdown("##### ⚠️ Ação imediata — vencidos e vencendo nos próximos 15 dias")
    acao = svc.acao_imediata(df, 15)
    if acao.empty:
        st.success("Nada vencido ou vencendo nos próximos 15 dias. 👏")
        return
    tabela_pesquisavel(
        acao,
        {
            "status": ColunaTabela("Status", "status"),
            "dias_restantes": ColunaTabela("Dias", "numero"),
            "data_vencimento": ColunaTabela("Vencimento", "data"),
            "tipo": ColunaTabela("Tipo de controle"),
            "alvo": ColunaTabela("Colaborador / item"),
            "setor": ColunaTabela("Setor"),
            "unidade": ColunaTabela("Unidade"),
            "categoria": ColunaTabela("Categoria", "rotulo"),
        },
        chave="dash_acao",
        filtros=["status", "categoria"],
        titulo_exportacao="Acao imediata",
        selecionavel=False,
    )
    st.caption("Para renovar, abra **Vencimentos**, selecione o item e use **Renovar**.")
