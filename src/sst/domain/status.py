"""Regra única de cálculo de status (fonte de verdade)."""

from __future__ import annotations

from datetime import date

from sst.domain.enums import SituacaoVencimento, StatusVencimento


def calcular_status(
    data_vencimento: date | None,
    situacao: SituacaoVencimento | str,
    antecedencia_dias: int,
    hoje: date,
) -> StatusVencimento:
    situacao = SituacaoVencimento(situacao)
    if situacao is SituacaoVencimento.CANCELADO:
        return StatusVencimento.CANCELADO
    if situacao is SituacaoVencimento.RENOVADO:
        return StatusVencimento.RENOVADO
    if data_vencimento is None:
        return StatusVencimento.SEM_VALIDADE
    if data_vencimento < hoje:
        return StatusVencimento.VENCIDO
    if (data_vencimento - hoje).days <= max(antecedencia_dias, 0):
        return StatusVencimento.A_VENCER
    return StatusVencimento.VIGENTE


def dias_restantes(data_vencimento: date | None, hoje: date) -> int | None:
    """Positivo = faltam N dias; negativo = vencido há N dias."""
    if data_vencimento is None:
        return None
    return (data_vencimento - hoje).days


# Ordem de criticidade para ordenação e cores na interface
ORDEM_STATUS = {
    StatusVencimento.VENCIDO: 0,
    StatusVencimento.A_VENCER: 1,
    StatusVencimento.VIGENTE: 2,
    StatusVencimento.SEM_VALIDADE: 3,
    StatusVencimento.RENOVADO: 4,
    StatusVencimento.CANCELADO: 5,
}

# Paleta de status reservada (good/warning/critical + neutros). Nunca usada
# para séries comuns e sempre acompanhada de rótulo de texto (não só cor).
CORES_STATUS = {
    StatusVencimento.VENCIDO.value: "#D03B3B",
    StatusVencimento.A_VENCER.value: "#FAB219",
    StatusVencimento.VIGENTE.value: "#0CA30C",
    StatusVencimento.SEM_VALIDADE.value: "#A9A9A3",
    StatusVencimento.RENOVADO.value: "#7D8CA3",
    StatusVencimento.CANCELADO.value: "#C3C2B7",
}

ICONES_STATUS = {
    StatusVencimento.VENCIDO.value: "🔴",
    StatusVencimento.A_VENCER.value: "🟡",
    StatusVencimento.VIGENTE.value: "🟢",
    StatusVencimento.SEM_VALIDADE.value: "⚪",
    StatusVencimento.RENOVADO.value: "🔁",
    StatusVencimento.CANCELADO.value: "⛔",
}
