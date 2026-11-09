"""Provedores de opções para caixas de seleção (consultados no momento do render)."""

from __future__ import annotations

from sst.domain.permissoes import UsuarioContexto
from sst.services.cadastro_service import (
    CargoService,
    ColaboradorService,
    EquipamentoService,
    FornecedorService,
    SetorService,
    UnidadeService,
)
from sst.services.tipo_controle_service import TipoControleService
from sst.ui.componentes import carregar


def unidades(ctx: UsuarioContexto, apenas_ativas: bool = True) -> dict[int, str]:
    return carregar(UnidadeService(ctx).opcoes, apenas_ativas, padrao={}) or {}


def setores(ctx: UsuarioContexto, unidade_id: int | None = None) -> dict[int, str]:
    df = carregar(SetorService(ctx).listar, False, padrao=None)
    if df is None or df.empty:
        return {}
    if unidade_id:
        df = df[df["unidade_id"] == unidade_id]
    return {int(r.id): f"{r.nome} ({r.unidade})" for r in df.itertuples()}


def cargos(ctx: UsuarioContexto) -> dict[int, str]:
    return carregar(CargoService(ctx).opcoes, padrao={}) or {}


def fornecedores(ctx: UsuarioContexto) -> dict[int, str]:
    return carregar(FornecedorService(ctx).opcoes, padrao={}) or {}


def colaboradores(ctx: UsuarioContexto, apenas_ativos: bool = True) -> dict[int, str]:
    return carregar(ColaboradorService(ctx).opcoes, apenas_ativos, padrao={}) or {}


def equipamentos(ctx: UsuarioContexto, apenas_ativos: bool = True) -> dict[int, str]:
    return carregar(EquipamentoService(ctx).opcoes, apenas_ativos, padrao={}) or {}


def tipos_controle(ctx: UsuarioContexto) -> dict[int, dict]:
    return carregar(TipoControleService(ctx).opcoes_por_alvo, padrao={}) or {}
