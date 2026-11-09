"""Agregações para o dashboard (DataFrames prontos para gráficos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from sst.config import get_settings
from sst.domain import datas
from sst.domain.enums import Categoria, StatusVencimento
from sst.domain.permissoes import UsuarioContexto
from sst.services.conformidade_service import ConformidadeService
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService

MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


@dataclass
class Indicadores:
    total_ativos: int
    vencidos: int
    a_vencer: int
    vencendo_30: int
    vigentes: int
    sem_validade: int
    pendentes_anexo: int
    conformidade_pct: float | None
    exigencias_atendidas: int
    exigencias_total: int


class DashboardService:
    def __init__(self, ctx: UsuarioContexto):
        self.ctx = ctx
        self.vencimentos = VencimentoService(ctx)
        self.conformidade = ConformidadeService(ctx)

    def base(self, unidade_id: int | None = None, categoria: str | None = None) -> pd.DataFrame:
        return self.vencimentos.listar(FiltroVencimentos(unidade_id=unidade_id, categoria=categoria))

    def indicadores(self, df: pd.DataFrame, unidade_id: int | None = None) -> Indicadores:
        pct, atendidas, total = self.conformidade.indice_conformidade(unidade_id)
        if df.empty:
            return Indicadores(0, 0, 0, 0, 0, 0, 0, pct, atendidas, total)
        st = df["status"]
        dias = df["dias_restantes"]
        return Indicadores(
            total_ativos=len(df),
            vencidos=int((st == StatusVencimento.VENCIDO.value).sum()),
            a_vencer=int((st == StatusVencimento.A_VENCER.value).sum()),
            vencendo_30=int(((dias >= 0) & (dias <= 30)).fillna(False).sum()),
            vigentes=int((st == StatusVencimento.VIGENTE.value).sum()),
            sem_validade=int((st == StatusVencimento.SEM_VALIDADE.value).sum()),
            pendentes_anexo=int(df["pendente_anexo"].sum()),
            conformidade_pct=pct,
            exigencias_atendidas=atendidas,
            exigencias_total=total,
        )

    @staticmethod
    def por_status(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["status", "rotulo", "quantidade"])
        r = df.groupby("status").size().reset_index(name="quantidade")
        r["rotulo"] = r["status"].map(lambda s: StatusVencimento(s).rotulo)
        return r

    @staticmethod
    def por_categoria_status(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["categoria", "status", "quantidade"])
        r = df.groupby(["categoria", "status"]).size().reset_index(name="quantidade")
        r["categoria"] = r["categoria"].map(lambda c: Categoria(c).rotulo)
        r["status_rotulo"] = r["status"].map(lambda s: StatusVencimento(s).rotulo)
        return r

    @staticmethod
    def por_unidade(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["unidade", "status", "quantidade"])
        d = df.copy()
        d["unidade"] = d["unidade"].fillna("Empresa (geral)")
        r = d.groupby(["unidade", "status"]).size().reset_index(name="quantidade")
        r["status_rotulo"] = r["status"].map(lambda s: StatusVencimento(s).rotulo)
        return r

    def proximos_12_meses(self, df: pd.DataFrame) -> pd.DataFrame:
        """Quantidade de vencimentos por mês (mês atual + 11), incluindo meses vazios."""
        hoje = datas.hoje(get_settings().timezone)
        meses = [datas.adicionar_meses(date(hoje.year, hoje.month, 1), i) for i in range(12)]
        base = pd.DataFrame({"mes": meses})
        if df.empty:
            base["quantidade"] = 0
        else:
            d = df[df["data_vencimento"].notna()].copy()
            d["mes"] = d["data_vencimento"].map(lambda x: date(x.year, x.month, 1))
            cont = d.groupby("mes").size().rename("quantidade").reset_index()
            base = base.merge(cont, on="mes", how="left").fillna({"quantidade": 0})
        base["quantidade"] = base["quantidade"].astype(int)
        base["rotulo"] = base["mes"].map(lambda m: f"{MESES_PT[m.month - 1]}/{str(m.year)[2:]}")
        return base

    @staticmethod
    def acao_imediata(df: pd.DataFrame, dias: int = 15) -> pd.DataFrame:
        if df.empty:
            return df
        mask = (df["status"] == StatusVencimento.VENCIDO.value) | (
            df["dias_restantes"].fillna(10**6) <= dias
        )
        return df[mask].sort_values("dias_restantes").reset_index(drop=True)
