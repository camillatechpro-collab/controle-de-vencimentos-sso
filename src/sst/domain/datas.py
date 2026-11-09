"""Cálculos de datas (puro, sem I/O)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sst.domain.enums import ValidadeUnidade


def adicionar_meses(d: date, meses: int) -> date:
    """Soma meses ajustando o dia ao último dia do mês quando necessário.
    Ex.: 31/01/2025 + 1 mês = 28/02/2025."""
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(d.day, ultimo))


def calcular_vencimento(
    data_emissao: date | None, valor: int | None, unidade: ValidadeUnidade | str
) -> date | None:
    """Retorna a data de vencimento padrão ou None quando não é calculável
    (SEM_VALIDADE, MANUAL ou dados incompletos)."""
    unidade = ValidadeUnidade(unidade)
    if unidade in (ValidadeUnidade.SEM_VALIDADE, ValidadeUnidade.MANUAL):
        return None
    if data_emissao is None or not valor or valor <= 0:
        return None
    if unidade is ValidadeUnidade.DIAS:
        return data_emissao + timedelta(days=valor)
    if unidade is ValidadeUnidade.MESES:
        return adicionar_meses(data_emissao, valor)
    return adicionar_meses(data_emissao, valor * 12)  # ANOS


def hoje(timezone: str = "America/Sao_Paulo") -> date:
    """'Hoje' no fuso do cliente (não no fuso do servidor)."""
    return datetime.now(ZoneInfo(timezone)).date()


def formatar_data(d: date | datetime | None) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")
