"""Páginas de cadastro: estrutura (unidades/setores/cargos), colaboradores, equipamentos, fornecedores."""

from __future__ import annotations

import streamlit as st

from sst.domain.enums import SituacaoColaborador, SituacaoEquipamento, TipoFornecedor
from sst.domain.permissoes import UsuarioContexto
from sst.domain.validadores import formatar_cnpj, mascarar_cpf
from sst.schemas.cadastros import UFS
from sst.services.cadastro_service import (
    CargoService,
    ColaboradorService,
    EquipamentoService,
    FornecedorService,
    SetorService,
    UnidadeService,
)
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService
from sst.ui import opcoes
from sst.ui.componentes import Campo, ColunaTabela, carregar, tabela_pesquisavel
from sst.ui.crud_pagina import ConfigCrud, pagina_crud

UF_OPCOES = {uf: uf for uf in sorted(UFS)}


# ====================================================================== estrutura
def _campos_dados_cnpj() -> list[Campo]:
    return [
        Campo("nome_fantasia", "Nome fantasia"),
        Campo("situacao_cadastral", "Situação cadastral"),
        Campo("cnae", "CNAE principal", largura_total=True),
        Campo("endereco", "Endereço", largura_total=True),
        Campo("cidade", "Cidade"),
        Campo("uf", "UF", "select", opcoes=UF_OPCOES),
        Campo("cep", "CEP"),
    ]


def _preencher_cnpj(r: dict, atuais: dict, campo_nome: str) -> dict:
    """Mapeia o retorno da consulta para o formulário; mantém o nome já digitado."""
    dados = {k: r.get(k) for k in ("cnpj", "nome_fantasia", "endereco", "cidade", "uf", "cep", "cnae",
                                   "situacao_cadastral")}
    dados["razao_social"] = r.get("razao_social")
    if campo_nome != "razao_social" and not atuais.get(campo_nome):
        dados[campo_nome] = r.get("nome_fantasia") or r.get("razao_social")
    return {k: v for k, v in dados.items() if v}


def _campos_unidade(ctx):
    return [
        Campo("nome", "Nome", obrigatorio=True),
        Campo("cnpj", "CNPJ", ajuda="Aceita CNPJ numérico ou alfanumérico"),
        Campo("razao_social", "Razão social", largura_total=True),
        *_campos_dados_cnpj(),
        Campo("responsavel_nome", "Responsável"),
        Campo("email_alertas", "E-mail para alertas"),
        Campo("ativo", "Ativa", "bool", padrao=True),
    ]


def _campos_setor(ctx):
    return [
        Campo("unidade_id", "Unidade", "select", obrigatorio=True, opcoes=lambda: opcoes.unidades(ctx)),
        Campo("nome", "Nome", obrigatorio=True),
        Campo("ativo", "Ativo", "bool", padrao=True),
    ]


def _campos_cargo(ctx):
    return [
        Campo("nome", "Nome", obrigatorio=True),
        Campo("descricao", "Descrição", "area"),
        Campo("ativo", "Ativo", "bool", padrao=True),
    ]


CFG_UNIDADE = ConfigCrud(
    chave="unidades", titulo_singular="Unidade", service_cls=UnidadeService, campos=_campos_unidade,
    colunas={
        "nome": ColunaTabela("Nome"), "cnpj": ColunaTabela("CNPJ"), "cidade": ColunaTabela("Cidade"),
        "uf": ColunaTabela("UF"), "responsavel_nome": ColunaTabela("Responsável"), "ativo": ColunaTabela("Ativa", "bool"),
    },
    filtros=["uf"],
    rotulo_registro=lambda r: f"{r['nome']}" + (f" — CNPJ {formatar_cnpj(r['cnpj'])}" if r.get("cnpj") else ""),
    consulta_cnpj=lambda r, atuais: _preencher_cnpj(r, atuais, "nome"),
)
CFG_SETOR = ConfigCrud(
    chave="setores", titulo_singular="Setor", service_cls=SetorService, campos=_campos_setor,
    colunas={"nome": ColunaTabela("Setor"), "unidade": ColunaTabela("Unidade"), "ativo": ColunaTabela("Ativo", "bool")},
    filtros=["unidade"],
)
CFG_CARGO = ConfigCrud(
    chave="cargos", titulo_singular="Cargo", service_cls=CargoService, campos=_campos_cargo,
    colunas={"nome": ColunaTabela("Cargo"), "ativo": ColunaTabela("Ativo", "bool")},
    ajuda="Defina em **Tipos de controle → Exigências por cargo** quais treinamentos/exames cada cargo exige.",
)


def pagina_estrutura(ctx: UsuarioContexto) -> None:
    st.title("🏢 Estrutura da empresa")
    t1, t2, t3 = st.tabs(["Unidades", "Setores", "Cargos"])
    with t1:
        pagina_crud(ctx, CFG_UNIDADE)
    with t2:
        pagina_crud(ctx, CFG_SETOR)
    with t3:
        pagina_crud(ctx, CFG_CARGO)


# ====================================================================== vencimentos do item
def _vencimentos_do_alvo(ctx: UsuarioContexto, filtro: FiltroVencimentos, chave: str) -> None:
    st.markdown("**Vencimentos ativos deste cadastro**")
    df = carregar(VencimentoService(ctx).listar, filtro, padrao=None)
    if df is None:
        return
    if df.empty:
        st.caption("Nenhum vencimento ativo.")
        return
    tabela_pesquisavel(
        df,
        {
            "status": ColunaTabela("Status", "status"), "tipo": ColunaTabela("Tipo de controle"),
            "data_emissao": ColunaTabela("Emissão", "data"), "data_vencimento": ColunaTabela("Vencimento", "data"),
            "dias_restantes": ColunaTabela("Dias", "numero"),
        },
        chave=chave, titulo_exportacao="Vencimentos", selecionavel=False,
    )


# ====================================================================== colaboradores
def _campos_colaborador(ctx):
    return [
        Campo("nome", "Nome completo", obrigatorio=True),
        Campo("cpf", "CPF", obrigatorio=True,
              ajuda="Validado automaticamente (dígitos verificadores) ao salvar. Exibido mascarado no perfil (LGPD)."),
        Campo("matricula", "Matrícula"),
        Campo("unidade_id", "Unidade", "select", obrigatorio=True, opcoes=lambda: opcoes.unidades(ctx)),
        Campo("setor_id", "Setor", "select", opcoes=lambda: opcoes.setores(ctx),
              ajuda="O setor deve pertencer à unidade escolhida"),
        Campo("cargo_id", "Cargo", "select", opcoes=lambda: opcoes.cargos(ctx)),
        Campo("data_admissao", "Data de admissão", "data"),
        Campo("situacao", "Situação", "select", obrigatorio=True, opcoes=SituacaoColaborador.opcoes(),
              padrao=SituacaoColaborador.ATIVO.value),
        Campo("data_desligamento", "Data de desligamento", "data"),
        Campo("email", "E-mail"),
        Campo("telefone", "Telefone"),
    ]


CFG_COLABORADOR = ConfigCrud(
    chave="colaboradores", titulo_singular="Colaborador", service_cls=ColaboradorService,
    campos=_campos_colaborador,
    colunas={
        "nome": ColunaTabela("Nome"), "matricula": ColunaTabela("Matrícula"), "unidade": ColunaTabela("Unidade"),
        "setor": ColunaTabela("Setor"), "cargo": ColunaTabela("Cargo"),
        "data_admissao": ColunaTabela("Admissão", "data"), "situacao": ColunaTabela("Situação", "rotulo"),
    },
    filtros=["unidade", "cargo", "situacao"],
    rotulo_registro=lambda r: f"{r['nome']} — CPF {mascarar_cpf(r['cpf'])}",
    detalhe_extra=lambda ctx, r: _botao_perfil(r),
    coluna_clicavel="nome",
    ao_clicar=lambda ctx, r: _abrir_perfil(int(r["id"])),
    ajuda="Clique no **nome** para abrir o perfil completo (ASOs, treinamentos, anexos e histórico). "
          "Para quem saiu da empresa, altere a situação para **Desligado** — o histórico é preservado.",
)

CHAVE_PERFIL = "colaborador__perfil_id"


def _abrir_perfil(colaborador_id: int) -> None:
    st.session_state[CHAVE_PERFIL] = colaborador_id
    st.rerun()


def _botao_perfil(r: dict) -> None:
    if st.button("👤 Abrir perfil completo", key=f"perfil_{r['id']}", type="primary"):
        _abrir_perfil(int(r["id"]))


def pagina_colaboradores(ctx: UsuarioContexto) -> None:
    from sst.ui.pages import colaborador_perfil

    perfil_id = st.session_state.get(CHAVE_PERFIL)
    if perfil_id:
        colaborador_perfil.pagina(ctx, int(perfil_id), voltar=lambda: st.session_state.pop(CHAVE_PERFIL, None))
        return
    st.title("👷 Colaboradores")
    pagina_crud(ctx, CFG_COLABORADOR)


# ====================================================================== equipamentos
def _campos_equipamento(ctx):
    return [
        Campo("descricao", "Descrição", obrigatorio=True),
        Campo("tipo", "Tipo", obrigatorio=True, ajuda="Ex.: Extintor, Cinto paraquedista, Detector de gases"),
        Campo("unidade_id", "Unidade", "select", obrigatorio=True, opcoes=lambda: opcoes.unidades(ctx)),
        Campo("patrimonio", "Patrimônio"),
        Campo("numero_serie", "Número de série"),
        Campo("fabricante", "Fabricante"),
        Campo("modelo", "Modelo"),
        Campo("ca_numero", "Nº do CA (EPI)"),
        Campo("localizacao", "Localização"),
        Campo("responsavel_colaborador_id", "Responsável", "select", opcoes=lambda: opcoes.colaboradores(ctx)),
        Campo("situacao", "Situação", "select", obrigatorio=True, opcoes=SituacaoEquipamento.opcoes(),
              padrao=SituacaoEquipamento.ATIVO.value),
    ]


CFG_EQUIPAMENTO = ConfigCrud(
    chave="equipamentos", titulo_singular="Equipamento", service_cls=EquipamentoService,
    campos=_campos_equipamento,
    colunas={
        "descricao": ColunaTabela("Descrição"), "tipo": ColunaTabela("Tipo"), "patrimonio": ColunaTabela("Patrimônio"),
        "numero_serie": ColunaTabela("Nº série"), "ca_numero": ColunaTabela("CA"), "unidade": ColunaTabela("Unidade"),
        "localizacao": ColunaTabela("Localização"), "responsavel": ColunaTabela("Responsável"),
        "situacao": ColunaTabela("Situação", "rotulo"),
    },
    filtros=["tipo", "unidade", "situacao"],
    rotulo_registro=lambda r: f"{r['descricao']}" + (f" (Pat. {r['patrimonio']})" if r.get("patrimonio") else ""),
    detalhe_extra=lambda ctx, r: _vencimentos_do_alvo(
        ctx, FiltroVencimentos(equipamento_id=int(r["id"])), f"equip_venc_{r['id']}"
    ),
)


def pagina_equipamentos(ctx: UsuarioContexto) -> None:
    st.title("🧯 Equipamentos")
    pagina_crud(ctx, CFG_EQUIPAMENTO)


# ====================================================================== fornecedores
def _campos_fornecedor(ctx):
    return [
        Campo("razao_social", "Razão social", obrigatorio=True),
        Campo("cnpj", "CNPJ"),
        Campo("tipo", "Tipo", "select", obrigatorio=True, opcoes=TipoFornecedor.opcoes(),
              padrao=TipoFornecedor.OUTRO.value),
        *_campos_dados_cnpj(),
        Campo("contato", "Contato"),
        Campo("email", "E-mail"),
        Campo("telefone", "Telefone"),
        Campo("ativo", "Ativo", "bool", padrao=True),
    ]


CFG_FORNECEDOR = ConfigCrud(
    chave="fornecedores", titulo_singular="Fornecedor", service_cls=FornecedorService,
    campos=_campos_fornecedor,
    colunas={
        "razao_social": ColunaTabela("Razão social"), "cnpj": ColunaTabela("CNPJ"),
        "tipo": ColunaTabela("Tipo", "rotulo"), "contato": ColunaTabela("Contato"),
        "email": ColunaTabela("E-mail"), "telefone": ColunaTabela("Telefone"), "ativo": ColunaTabela("Ativo", "bool"),
    },
    filtros=["tipo"],
    rotulo_registro=lambda r: r["razao_social"],
    detalhe_extra=lambda ctx, r: _vencimentos_do_alvo(
        ctx, FiltroVencimentos(fornecedor_id=int(r["id"])), f"forn_venc_{r['id']}"
    ),
    consulta_cnpj=lambda r, atuais: _preencher_cnpj(r, atuais, "razao_social"),
)


def pagina_fornecedores(ctx: UsuarioContexto) -> None:
    st.title("🤝 Fornecedores")
    st.caption("Clínicas, empresas de treinamento, laboratórios e prestadores de serviço.")
    pagina_crud(ctx, CFG_FORNECEDOR)
