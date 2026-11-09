"""Identidade visual NOLTH Web Design Studio (por Camilla Fialho).

Segue a linguagem do site nolth.netlify.app: tipografia Space Grotesk/Inter,
ciano e lilás como acentos discretos, cartões translúcidos com borda fina.
As cores de claro/escuro ficam em .streamlit/config.toml; aqui só há regras
que funcionam nos dois temas (transparências, sem cor de fundo fixa).
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parents[3] / "assets"
ICONE = ASSETS / "icone.png"

CIANO = "#3BE3F0"
LILAS = "#B98CFF"
MARCA = "NOLTH"
SLOGAN = "Web Design Studio"
AUTORA = "Camilla Fialho"
SITE = "https://nolth.netlify.app/#contato"

_CSS = f"""
<style>
/* títulos: limpos, com um traço curto ciano→lilás (como no site) */
h1 {{ letter-spacing: -0.01em; }}
h1::after {{
  content: ""; display: block; width: 44px; height: 3px; border-radius: 3px; margin-top: -.35rem;
  background: linear-gradient(90deg, {CIANO}, {LILAS});
}}
/* cartões de indicadores translúcidos */
[data-testid="stMetric"] {{
  background: rgba(130, 145, 175, .06); border: 1px solid rgba(59, 227, 240, .18);
  border-radius: 14px; padding: 8px 12px;
}}
[data-testid="stMetricLabel"] p {{ font-size: .8rem; opacity: .8; }}
/* marca no topo da barra lateral */
.nl-marca {{ display: flex; align-items: center; gap: .6rem; margin: -.25rem 0 .75rem; }}
.nl-marca img {{ border-radius: 9px; }}
.nl-marca .nome {{
  font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.15rem; letter-spacing: .14em;
  background: linear-gradient(90deg, #22C3D2, #9B6BF2); -webkit-background-clip: text; background-clip: text;
  color: transparent; line-height: 1.1;
}}
.nl-marca .slogan {{ font-size: .62rem; letter-spacing: .32em; text-transform: uppercase; opacity: .6; }}
/* texto escuro nos botões principais: contraste bom no ciano dos dois temas */
button[kind^="primary"], button[kind^="primary"] p {{ color: #0B1220 !important; font-weight: 600; }}
.nl-rodape {{ font-size: .74rem; opacity: .75; text-align: center; margin-top: .75rem; line-height: 1.6; }}
.nl-rodape a {{ color: #9B6BF2 !important; text-decoration: none; font-weight: 600; }}
.nl-rodape a:hover {{ text-decoration: underline; }}
</style>
"""


def _icone_html(tamanho: int = 38) -> str:
    if not ICONE.exists():
        return ""
    dados = base64.b64encode(ICONE.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{dados}" width="{tamanho}" height="{tamanho}" alt="NOLTH">'


def aplicar() -> None:
    """Injeta o estilo da marca (chamar uma vez por execução)."""
    st.markdown(_CSS, unsafe_allow_html=True)
    if ICONE.exists():
        st.logo(str(ICONE), size="large", link=SITE)


def marca_lateral() -> None:
    st.markdown(
        f'<div class="nl-marca">{_icone_html()}<div><div class="nome">{MARCA}</div>'
        f'<div class="slogan">{SLOGAN}</div></div></div>',
        unsafe_allow_html=True,
    )


def rodape() -> None:
    st.markdown(
        f'<div class="nl-rodape">Desenvolvido por <b>{MARCA} {SLOGAN}</b><br>'
        f'Criado por {AUTORA} · <a href="{SITE}" target="_blank" rel="noopener noreferrer">Fale comigo ↗</a><br>'
        f'<span style="opacity:.8">Tema claro/escuro: menu ⋮ no canto superior direito</span></div>',
        unsafe_allow_html=True,
    )


def cabecalho_login() -> None:
    st.markdown(
        f'<div style="text-align:center;margin:1.5rem 0 .4rem">{_icone_html(84)}</div>'
        f'<div class="nl-marca" style="justify-content:center;margin-bottom:1.25rem"><div style="text-align:center">'
        f'<div class="nome" style="font-size:1.5rem">{MARCA}</div><div class="slogan">{SLOGAN}</div></div></div>',
        unsafe_allow_html=True,
    )
