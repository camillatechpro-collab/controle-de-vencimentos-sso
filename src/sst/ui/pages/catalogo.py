"""Catálogo de tipos de controle e matriz de exigências por cargo."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from sst.domain.enums import AlvoTipo, Categoria, ValidadeUnidade
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.services.conformidade_service import ConformidadeService
from sst.services.tipo_controle_service import TipoControleService
from sst.ui import estado, opcoes
from sst.ui.componentes import Campo, ColunaTabela, carregar, executar
from sst.ui.crud_pagina import ConfigCrud, pagina_crud


def _campos_tipo(ctx):
    return [
        Campo("nome", "Nome", obrigatorio=True, largura_total=True),
        Campo("categoria", "Categoria", "select", obrigatorio=True, opcoes=Categoria.opcoes()),
        Campo("alvo_tipo", "Aplica-se a", "select", obrigatorio=True, opcoes=AlvoTipo.opcoes()),
        Campo("validade_valor", "Validade", "inteiro", extras={"min": 1, "max": 600},
              ajuda="Quantidade na unidade ao lado. Deixe vazio para 'Informada manualmente' ou 'Sem validade'."),
        Campo("validade_unidade", "Unidade da validade", "select", obrigatorio=True,
              opcoes=ValidadeUnidade.opcoes(), padrao=ValidadeUnidade.MESES.value),
        Campo("antecedencia_dias", "Antecedência do alerta (dias)", "inteiro", obrigatorio=True, padrao=30,
              extras={"min": 0, "max": 365}),
        Campo("norma_referencia", "Norma de referência"),
        Campo("carga_horaria_padrao", "Carga horária padrão (h)", "inteiro", extras={"min": 1, "max": 2000}),
        Campo("exige_anexo", "Exige anexo (certificado/laudo)", "bool"),
        Campo("descricao", "Descrição / orientação", "area"),
        Campo("ativo", "Ativo", "bool", padrao=True),
    ]


def _formatar_validade(r) -> str:
    uni = r.get("validade_unidade")
    if uni in (ValidadeUnidade.MANUAL.value, ValidadeUnidade.SEM_VALIDADE.value):
        return ValidadeUnidade(uni).rotulo
    val = r.get("validade_valor")
    return f"{int(val)} {ValidadeUnidade(uni).rotulo.lower()}" if val and not pd.isna(val) else ""


class _TipoListagem(TipoControleService):
    """Acrescenta coluna de validade legível à listagem."""

    def listar(self, incluir_inativos: bool = True):
        df = super().listar(incluir_inativos)
        if not df.empty:
            df["validade"] = df.apply(_formatar_validade, axis=1)
        return df


CFG_TIPO = ConfigCrud(
    chave="tipos", titulo_singular="Tipo de controle", service_cls=_TipoListagem, campos=_campos_tipo,
    colunas={
        "categoria": ColunaTabela("Categoria", "rotulo"), "nome": ColunaTabela("Nome"),
        "alvo_tipo": ColunaTabela("Aplica-se a", "rotulo"), "validade": ColunaTabela("Validade"),
        "antecedencia_dias": ColunaTabela("Alerta (dias)", "numero"), "norma_referencia": ColunaTabela("Norma"),
        "exige_anexo": ColunaTabela("Exige anexo", "bool"), "ativo": ColunaTabela("Ativo", "bool"),
    },
    filtros=["categoria", "alvo_tipo"],
    perm_escrita=Permissao.GERENCIAR_CATALOGO,
    ajuda="Periodicidades iniciais são sugestões: revise conforme seu PGR/PCMSO e a legislação aplicável.",
)


def _matriz(ctx: UsuarioContexto) -> None:
    cs = ConformidadeService(ctx)
    cargos = opcoes.cargos(ctx)
    if not cargos:
        st.info("Cadastre cargos em **Estrutura da empresa → Cargos** primeiro.")
        return
    tipos = {i: t for i, t in opcoes.tipos_controle(ctx).items() if t["alvo_tipo"] == AlvoTipo.COLABORADOR.value}
    estado.mostrar_flash()

    cargo_id = st.selectbox("Cargo", list(cargos), format_func=lambda i: cargos[i], key="matriz_cargo")
    atuais = carregar(cs.requisitos_do_cargo, cargo_id, padrao=[]) or []
    if ctx.pode(Permissao.GERENCIAR_CATALOGO):
        with st.form(f"matriz_form_{cargo_id}"):
            escolhidos = st.multiselect(
                "Treinamentos, exames e certificados exigidos para este cargo",
                list(tipos), default=[t for t in atuais if t in tipos],
                format_func=lambda i: f"{tipos[i]['nome']} ({Categoria(tipos[i]['categoria']).rotulo})",
                placeholder="Selecione...",
            )
            if st.form_submit_button("💾 Salvar exigências", type="primary"):
                ok, _ = executar(cs.definir_requisitos, cargo_id, escolhidos)
                if ok:
                    estado.flash("Exigências do cargo atualizadas.")
                    st.rerun()
    else:
        st.write(", ".join(tipos[t]["nome"] for t in atuais if t in tipos) or "Nenhuma exigência cadastrada.")

    st.markdown("##### Visão geral da matriz")
    df = carregar(cs.matriz, padrao=None)
    if df is None or df.empty:
        st.caption("Nenhuma exigência cadastrada ainda.")
        return
    pivo = pd.crosstab(df["tipo"], df["cargo"]).map(lambda v: "✔" if v else "")
    st.dataframe(pivo, width="stretch")


def pagina(ctx: UsuarioContexto) -> None:
    st.title("📚 Tipos de controle")
    t1, t2 = st.tabs(["Catálogo", "Exigências por cargo"])
    with t1:
        pagina_crud(ctx, CFG_TIPO)
    with t2:
        _matriz(ctx)
