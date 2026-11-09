"""Utilitários compartilhados pelos services."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

import pandas as pd
from sqlalchemy import Result


def df_de_resultado(resultado: Result) -> pd.DataFrame:
    """Converte resultado SQLAlchemy em DataFrame com enums convertidos em texto."""
    colunas = list(resultado.keys())
    df = pd.DataFrame(resultado.all(), columns=colunas)
    for col in df.columns:
        serie = df[col]
        # pandas 3 guarda StrEnum em colunas "string" mantendo o objeto Enum
        if pd.api.types.is_object_dtype(serie) or pd.api.types.is_string_dtype(serie):
            if any(isinstance(x, Enum) for x in serie.head(50)):
                df[col] = serie.map(lambda x: x.value if isinstance(x, Enum) else x).astype(object)
    return df


def como_utc(dt: datetime | None) -> datetime | None:
    """SQLite devolve datetimes sem fuso: assume UTC para comparar com segurança."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
