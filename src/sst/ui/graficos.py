"""Gráficos Plotly no padrão visual da aplicação.

Regras: cores de status reservadas e sempre com rótulo de texto; marcas finas
com 2px de espaço entre segmentos; grade discreta; um único eixo; tooltip em todas as marcas.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from sst.domain.enums import StatusVencimento
from sst.domain.status import CORES_STATUS, ORDEM_STATUS

COR_SERIE = "#1FB5C4"  # ciano NOLTH, legível no tema claro e no escuro
GRADE = "rgba(128, 140, 165, 0.18)"  # neutros translúcidos: servem aos dois temas
EIXO = "rgba(128, 140, 165, 0.35)"
SUPERFICIE = "rgba(0, 0, 0, 0)"  # transparente: o fundo vem do tema escolhido

_ORDEM = [s.value for s in sorted(ORDEM_STATUS, key=ORDEM_STATUS.get)]


def _layout(fig: go.Figure, altura: int = 320, legenda: bool = True) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SUPERFICIE,
        plot_bgcolor=SUPERFICIE,
        font=dict(size=13),
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        hoverlabel=dict(font_size=13),
        bargap=0.35,
    )
    fig.update_xaxes(gridcolor=GRADE, linecolor=EIXO, zeroline=False)
    fig.update_yaxes(gridcolor=GRADE, linecolor=EIXO, zeroline=False)
    return fig


def barras_status(df: pd.DataFrame) -> go.Figure:
    """Barra horizontal por status (uma série: sem legenda; rótulo direto no eixo)."""
    d = df.copy()
    d["ordem"] = d["status"].map(lambda s: _ORDEM.index(s) if s in _ORDEM else 99)
    d = d.sort_values("ordem", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=d["quantidade"], y=d["rotulo"], orientation="h",
            marker=dict(color=[CORES_STATUS.get(s, COR_SERIE) for s in d["status"]],
                        line=dict(width=0)),
            text=d["quantidade"], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: <b>%{x}</b><extra></extra>",
        )
    )
    fig.update_xaxes(showgrid=True, title=None, rangemode="tozero")
    fig.update_yaxes(showgrid=False, title=None)
    return _layout(fig, altura=260, legenda=False)


def barras_empilhadas_status(df: pd.DataFrame, eixo: str, titulo_eixo: str) -> go.Figure:
    """Barras horizontais empilhadas por status (legenda sempre presente)."""
    fig = go.Figure()
    ordem_categorias = (
        df.groupby(eixo)["quantidade"].sum().sort_values(ascending=True).index.tolist()
    )
    for status in _ORDEM:
        parte = df[df["status"] == status]
        if parte.empty:
            continue
        fig.add_trace(
            go.Bar(
                y=parte[eixo], x=parte["quantidade"], orientation="h",
                name=StatusVencimento(status).rotulo,
                marker=dict(color=CORES_STATUS[status], line=dict(width=0)),
                hovertemplate=f"%{{y}} · {StatusVencimento(status).rotulo}: <b>%{{x}}</b><extra></extra>",
            )
        )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(categoryorder="array", categoryarray=ordem_categorias, title=None, showgrid=False)
    fig.update_xaxes(title=titulo_eixo, rangemode="tozero")
    altura = max(240, 44 * len(ordem_categorias) + 80)
    return _layout(fig, altura=altura)


def barras_mensais(df: pd.DataFrame) -> go.Figure:
    """Vencimentos por mês (uma série, cor única)."""
    fig = go.Figure(
        go.Bar(
            x=df["rotulo"], y=df["quantidade"],
            marker=dict(color=COR_SERIE, line=dict(width=0)),
            text=[q if q else "" for q in df["quantidade"]], textposition="outside", cliponaxis=False,
            hovertemplate="%{x}: <b>%{y}</b> vencimento(s)<extra></extra>",
        )
    )
    fig.update_xaxes(showgrid=False, title=None, type="category")
    fig.update_yaxes(title="Vencimentos", rangemode="tozero")
    return _layout(fig, altura=300, legenda=False)
