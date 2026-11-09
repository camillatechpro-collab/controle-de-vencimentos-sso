"""Exportação de DataFrames para Excel formatado (OpenPyXL).

Proteção contra injeção de fórmula: textos iniciados por = + - @ (ou tab/CR)
recebem um apóstrofo, para que o Excel/LibreOffice não os executem.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from enum import Enum
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")
_COR_CABECALHO = "1F6FB2"


def sanitizar_celula(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, Enum):
        valor = valor.value
    if isinstance(valor, float) and pd.isna(valor):
        return None
    if valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, str) and valor.startswith(_PERIGOSOS):
        return "'" + valor
    return valor


def dataframe_para_xlsx(
    df: pd.DataFrame,
    titulo: str = "Relatório",
    rotulos: dict[str, str] | None = None,
    colunas: list[str] | None = None,
) -> bytes:
    rotulos = rotulos or {}
    colunas = [c for c in (colunas or list(df.columns)) if c in df.columns]
    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31] or "Dados"

    cabecalho = [rotulos.get(c, c) for c in colunas]
    ws.append(cabecalho)
    for cel in ws[1]:
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor=_COR_CABECALHO)
        cel.alignment = Alignment(vertical="center", wrap_text=True)

    for linha in df[colunas].itertuples(index=False, name=None):
        ws.append([sanitizar_celula(v) for v in linha])

    # formatos de data e largura de colunas
    for idx, _col in enumerate(colunas, start=1):
        letra = get_column_letter(idx)
        maior = len(str(cabecalho[idx - 1]))
        for cel in ws[letra][1:]:
            if isinstance(cel.value, datetime):
                cel.number_format = "DD/MM/YYYY HH:MM"
            elif isinstance(cel.value, date):
                cel.number_format = "DD/MM/YYYY"
            maior = max(maior, min(len(str(cel.value)) if cel.value is not None else 0, 60))
        ws.column_dimensions[letra].width = maior + 2

    ws.freeze_panes = "A2"
    if colunas:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(colunas))}{max(ws.max_row, 1)}"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
