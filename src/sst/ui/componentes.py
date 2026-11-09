"""Componentes reutilizáveis: tratamento de erros, campos de formulário, tabela com pesquisa."""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import pandas as pd
import streamlit as st

from sst.domain.enums import StatusVencimento, _ROTULOS
from sst.domain.exceptions import SSTError, ValidacaoError
from sst.domain.status import ICONES_STATUS
from sst.infra.excel.exportador import dataframe_para_xlsx
from sst.logging_config import get_logger

log = get_logger("ui")

DATA_MIN, DATA_MAX = date(1900, 1, 1), date(2100, 12, 31)


# ======================================================================== erros
def executar(fn: Callable, *args: Any, **kwargs: Any) -> tuple[bool, Any]:
    """Executa uma operação de service exibindo erros amigáveis.
    Retorna (sucesso, resultado)."""
    try:
        return True, fn(*args, **kwargs)
    except ValidacaoError as e:
        st.error("**Verifique os dados informados:**\n\n" + "\n".join(f"- {m}" for m in e.erros))
    except SSTError as e:
        st.error(e.mensagem)
    except Exception:
        codigo = uuid.uuid4().hex[:8].upper()
        log.exception("Erro inesperado [%s] em %s", codigo, getattr(fn, "__qualname__", fn))
        st.error(
            f"Ocorreu um erro inesperado. Nenhuma alteração foi gravada. "
            f"Informe ao suporte o código **{codigo}**."
        )
    return False, None


def carregar(fn: Callable, *args: Any, padrao: Any = None, **kwargs: Any) -> Any:
    """Leitura com tratamento de erro (retorna `padrao` se falhar)."""
    ok, r = executar(fn, *args, **kwargs)
    return r if ok else padrao


# ======================================================================== formatação
def rotulo(valor: Any) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, Enum):
        valor = valor.value
    return _ROTULOS.get(str(valor), str(valor))


def status_texto(status: str | None) -> str:
    if not status:
        return ""
    if status == "SEM_REGISTRO":
        return "🔴 Sem registro"
    return f"{ICONES_STATUS.get(status, '')} {StatusVencimento(status).rotulo}"


def _sem_acento(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c)).lower()


# ======================================================================== campos
@dataclass
class Campo:
    nome: str
    rotulo: str
    tipo: str = "texto"  # texto | area | data | inteiro | decimal | bool | select | multiselect | senha
    obrigatorio: bool = False
    opcoes: dict | Callable[[], dict] | None = None
    ajuda: str | None = None
    padrao: Any = None
    largura_total: bool = False
    desabilitado: bool = False
    extras: dict = field(default_factory=dict)

    def obter_opcoes(self) -> dict:
        if callable(self.opcoes):
            return self.opcoes() or {}
        return self.opcoes or {}


def _valor_inicial(campo: Campo, valores: dict) -> Any:
    v = valores.get(campo.nome, None)
    if v is None:
        v = campo.padrao
    if isinstance(v, Enum):
        v = v.value
    return v


def render_campo(campo: Campo, valores: dict, prefixo: str) -> Any:
    chave = f"{prefixo}__{campo.nome}"
    label = campo.rotulo + (" *" if campo.obrigatorio else "")
    v = _valor_inicial(campo, valores)
    comum = {"key": chave, "help": campo.ajuda, "disabled": campo.desabilitado}
    t = campo.tipo
    if t == "texto":
        return st.text_input(label, value="" if v is None else str(v), **comum, **campo.extras)
    if t == "senha":
        return st.text_input(label, type="password", **comum)
    if t == "area":
        return st.text_area(label, value="" if v is None else str(v), height=90, **comum)
    if t == "data":
        if isinstance(v, datetime):
            v = v.date()
        return st.date_input(label, value=v, format="DD/MM/YYYY", min_value=DATA_MIN, max_value=DATA_MAX, **comum)
    if t == "inteiro":
        return st.number_input(label, value=int(v) if v is not None else None, step=1,
                               min_value=campo.extras.get("min", 0), max_value=campo.extras.get("max"), **comum)
    if t == "decimal":
        return st.number_input(label, value=float(v) if v is not None else None, step=0.01,
                               min_value=0.0, format="%.2f", **comum)
    if t == "bool":
        return st.checkbox(label, value=bool(v) if v is not None else False, **comum)
    if t == "select":
        opcoes = campo.obter_opcoes()
        chaves = list(opcoes.keys())
        indice = chaves.index(v) if v in chaves else None
        return st.selectbox(label, chaves, index=indice, format_func=lambda k: opcoes.get(k, str(k)),
                            placeholder="Selecione...", **comum)
    if t == "multiselect":
        opcoes = campo.obter_opcoes()
        atuais = [x for x in (v or []) if x in opcoes]
        return st.multiselect(label, list(opcoes.keys()), default=atuais,
                              format_func=lambda k: opcoes.get(k, str(k)), placeholder="Selecione...", **comum)
    raise ValueError(f"Tipo de campo desconhecido: {t}")


def render_campos(campos: list[Campo], valores: dict | None, prefixo: str, colunas: int = 2) -> dict[str, Any]:
    """Renderiza campos em grade e devolve {nome: valor}."""
    valores = valores or {}
    resultado: dict[str, Any] = {}
    fila: list[Campo] = []

    def _descarregar():
        if not fila:
            return
        cols = st.columns(colunas)
        for i, c in enumerate(fila):
            with cols[i % colunas]:
                resultado[c.nome] = render_campo(c, valores, prefixo)
        fila.clear()

    for c in campos:
        if c.largura_total or c.tipo == "area":
            _descarregar()
            resultado[c.nome] = render_campo(c, valores, prefixo)
        else:
            fila.append(c)
            if len(fila) == colunas:
                _descarregar()
    _descarregar()
    return resultado


def limpar_valores(dados: dict[str, Any]) -> dict[str, Any]:
    """Converte float→Decimal/int quando aplicável e strings vazias em None."""
    limpo = {}
    for k, v in dados.items():
        if isinstance(v, str) and v.strip() == "":
            v = None
        elif isinstance(v, float) and v.is_integer() and not k.endswith(("valor", "nota_aproveitamento")):
            v = int(v)
        elif isinstance(v, float):
            v = Decimal(str(v))
        limpo[k] = v
    return limpo


# ======================================================================== tabela
@dataclass
class ColunaTabela:
    rotulo: str
    tipo: str = "texto"  # texto | data | datahora | numero | status | rotulo | bool
    largura: str | None = None


def _preparar_exibicao(df: pd.DataFrame, colunas: dict[str, ColunaTabela]) -> tuple[pd.DataFrame, dict]:
    exib = pd.DataFrame(index=df.index)
    config: dict[str, Any] = {}
    for nome, col in colunas.items():
        if nome not in df.columns:
            continue
        serie = df[nome]
        if col.tipo == "status":
            serie = serie.map(status_texto)
        elif col.tipo == "rotulo":
            serie = serie.map(rotulo)
        elif col.tipo == "bool":
            serie = serie.map(lambda x: "Sim" if bool(x) and not pd.isna(x) else "Não")
        elif col.tipo == "data":
            serie = pd.to_datetime(serie, errors="coerce")
            config[col.rotulo] = st.column_config.DateColumn(col.rotulo, format="DD/MM/YYYY", width=col.largura)
        elif col.tipo == "datahora":
            serie = pd.to_datetime(serie, errors="coerce", utc=True).dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
            config[col.rotulo] = st.column_config.DatetimeColumn(col.rotulo, format="DD/MM/YYYY HH:mm", width=col.largura)
        elif col.tipo == "numero":
            config[col.rotulo] = st.column_config.NumberColumn(col.rotulo, format="%d", width=col.largura)
        if col.rotulo not in config and col.largura:
            config[col.rotulo] = st.column_config.Column(col.rotulo, width=col.largura)
        exib[col.rotulo] = serie
    return exib, config


def tabela_pesquisavel(
    df: pd.DataFrame,
    colunas: dict[str, ColunaTabela],
    chave: str,
    filtros: list[str] | None = None,
    titulo_exportacao: str = "Dados",
    selecionavel: bool = True,
    altura: int | None = None,
    coluna_clicavel: str | None = None,
) -> tuple[dict | None, pd.DataFrame]:
    """Tabela com busca textual, filtros por coluna, contador, exportação Excel e seleção.
    Retorna (linha_selecionada | None, df_filtrado).
    `coluna_clicavel`: clicar numa célula dessa coluna grava a linha em
    st.session_state[f"{chave}__clicado"] (ex.: abrir o perfil ao clicar no nome)."""
    filtros = [f for f in (filtros or []) if f in df.columns]
    n_cols = 1 + len(filtros)
    cols = st.columns([2] + [1] * len(filtros)) if n_cols > 1 else [st.container()]
    with cols[0]:
        busca = st.text_input("🔎 Pesquisar", key=f"{chave}__busca", placeholder="Digite para filtrar...")
    filtrado = df
    for i, f in enumerate(filtros, start=1):
        valores = sorted({v for v in df[f].dropna().unique()}, key=lambda x: rotulo(x))
        rot = colunas[f].rotulo if f in colunas else f
        with cols[i]:
            escolha = st.multiselect(rot, valores, key=f"{chave}__f_{f}",
                                     format_func=lambda x, _t=colunas.get(f): status_texto(x) if _t and _t.tipo == "status" else rotulo(x),
                                     placeholder="Todos")
        if escolha:
            filtrado = filtrado[filtrado[f].isin(escolha)]
    if busca and not filtrado.empty:
        termo = _sem_acento(busca.strip())
        cols_busca = [c for c in colunas if c in filtrado.columns]
        texto = filtrado[cols_busca].apply(
            lambda linha: _sem_acento(" ".join(rotulo(x) for x in linha)), axis=1
        )
        filtrado = filtrado[texto.str.contains(termo, regex=False)]

    filtrado = filtrado.reset_index(drop=True)
    exib, config = _preparar_exibicao(filtrado, colunas)

    topo1, topo2 = st.columns([4, 1])
    topo1.caption(f"{len(filtrado)} de {len(df)} registro(s)")
    if not filtrado.empty:
        exportar = filtrado.copy()
        for nome, col in colunas.items():
            if nome in exportar.columns and col.tipo in ("status",):
                exportar[nome] = exportar[nome].map(lambda s: StatusVencimento(s).rotulo if s in StatusVencimento.__members__ else rotulo(s))
            elif nome in exportar.columns and col.tipo == "rotulo":
                exportar[nome] = exportar[nome].map(rotulo)
        topo2.download_button(
            "⬇️ Excel",
            data=dataframe_para_xlsx(exportar, titulo_exportacao, {k: v.rotulo for k, v in colunas.items()}, list(colunas)),
            file_name=f"{titulo_exportacao.lower().replace(' ', '_')}_{date.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{chave}__xlsx",
        )

    if filtrado.empty:
        st.info("Nenhum registro encontrado.")
        return None, filtrado

    kwargs: dict[str, Any] = {"hide_index": True, "column_config": config, "width": "stretch"}
    if altura:
        kwargs["height"] = altura
    if not selecionavel:
        st.dataframe(exib, **kwargs)
        return None, filtrado
    modos = ["single-row", "single-cell"] if coluna_clicavel else "single-row"
    evento = st.dataframe(exib, key=f"{chave}__grid", on_select="rerun", selection_mode=modos, **kwargs)
    linhas = list(evento.selection.rows) if evento and hasattr(evento, "selection") else []
    if coluna_clicavel and evento is not None and hasattr(evento, "selection"):
        alvo = colunas[coluna_clicavel].rotulo
        for linha, coluna in getattr(evento.selection, "cells", []) or []:
            if coluna == alvo and linha < len(filtrado):
                st.session_state[f"{chave}__clicado"] = filtrado.iloc[linha].to_dict()
                linhas = [linha]
                break
    if linhas and linhas[0] < len(filtrado):
        st.caption("Linha selecionada — as ações estão logo abaixo.")
        return filtrado.iloc[linhas[0]].to_dict(), filtrado
    st.caption("Clique na caixa à esquerda de uma linha para ver as ações.")
    return None, filtrado


def confirmar(chave: str, texto: str, rotulo_botao: str = "Confirmar", tipo: str = "primary") -> bool:
    """Confirmação em dois passos (evita exclusões acidentais sem diálogos de navegador)."""
    marcado = st.checkbox(texto, key=f"{chave}__chk")
    return st.button(rotulo_botao, key=f"{chave}__btn", type=tipo, disabled=not marcado)
