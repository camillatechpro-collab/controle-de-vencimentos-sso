"""Tipos de coluna reutilizáveis."""

from __future__ import annotations

from enum import Enum as PyEnum

from sqlalchemy import Enum


def enum_col(enum_cls: type[PyEnum]) -> Enum:
    """Enum gravado como VARCHAR (portável SQLite/PostgreSQL), validado na escrita."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=30,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )
