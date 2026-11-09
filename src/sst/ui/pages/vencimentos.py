"""Página principal de vencimentos: lista com filtros, lançamento, lote, edição,
renovação, cancelamento, exclusão, anexos e histórico."""

from __future__ import annotations

from enum import Enum
from typing import Any

import streamlit as st

from sst.domain.datas import formatar_data
from sst.domain.enums import (
    AlvoTipo,
    Categoria,
    Modalidade,
    ResultadoASO,
    SituacaoVencimento,
    StatusVencimento,
    TipoASO,
    TipoServicoEquipamento,
    ValidadeUnidade,
)
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService
from sst.ui import estado, opcoes
from sst.ui.componentes import (
    Campo,
    ColunaTabela,
    carregar,
    confirmar,
    executar,
    limpar_valores,
    render_campos,
    rotulo,
    status_texto,
    tabela_pesquisavel,
)

MODO = "venc__modo"
VERSAO = "venc__versao"

COLUNAS = {
    "status": ColunaTabela("Status", "status"),
    "dias_restantes": ColunaTabela("Dias", "numero"),
    "data_vencimento": ColunaTabela("Vencimento", "data"),
    "tipo": ColunaTabela("Tipo de controle"),
    "alvo": ColunaTabela("Colaborador / item"),
    "unidade": ColunaTabela("Unidade"),
    "categoria": ColunaTabela("Categoria", "rotulo"),
    "numero_documento": ColunaTabela("Nº documento"),
    "data_emissao": ColunaTabela("Emissão", "data"),
    "anexos": ColunaTabela("Anexos", "numero"),
    "pendente_anexo": ColunaTabela("Falta anexo", "bool"),
}


def _valor(x: Any) -> Any:
    return x.value if isinstance(x, Enum) else x


def _abrir(modo: tuple) -> None:
    st.session_state[MODO] = modo
    st.rerun()


def _fechar() -> None:
    st.session_state[MODO] = None
    st.session_state[VERSAO] = st.session_state.get(VERSAO, 0) + 1


def _versao() -> int:
    return st.session_state.get(VERSAO, 0)


# ============================================================ definição de campos
def _descricao_validade(tipo: dict) -> str:
    uni = tipo["validade_unidade"]
    if uni == ValidadeUnidade.SEM_VALIDADE.value:
        return "Este tipo **não tem validade** (registro permanente)."
    if uni == ValidadeUnidade.MANUAL.value:
        return "Informe a **data de vencimento** que consta no documento."
    val = int(tipo["validade_valor"])
    return (
        f"Validade padrão: **{val} {ValidadeUnidade(uni).rotulo.lower()}** a partir da emissão. "
        "Deixe o vencimento em branco para calcular automaticamente; "
        "se informar outra data, preencha a justificativa."
    )


def _campo_alvo(ctx: UsuarioContexto, alvo: str) -> list[Campo]:
    if alvo == AlvoTipo.COLABORADOR.value:
        return [Campo("colaborador_id", "Colaborador", "select", obrigatorio=True,
                      opcoes=lambda: opcoes.colaboradores(ctx, apenas_ativos=False), largura_total=True)]
    if alvo == AlvoTipo.EQUIPAMENTO.value:
        return [Campo("equipamento_id", "Equipamento", "select", obrigatorio=True,
                      opcoes=lambda: opcoes.equipamentos(ctx), largura_total=True)]
    if alvo == AlvoTipo.UNIDADE.value:
        return [Campo("alvo_unidade_id", "Unidade", "select", obrigatorio=True,
                      opcoes=lambda: opcoes.unidades(ctx), largura_total=True)]
    if alvo == AlvoTipo.FORNECEDOR.value:
        return [Campo("fornecedor_id", "Fornecedor", "select", obrigatorio=True,
                      opcoes=lambda: opcoes.fornecedores(ctx), largura_total=True)]
    return []


def _campos_base(tipo: dict) -> list[Campo]:
    uni = tipo["validade_unidade"]
    calculavel = uni not in (ValidadeUnidade.MANUAL.value, ValidadeUnidade.SEM_VALIDADE.value)
    campos = [
        Campo("data_emissao", "Data de emissão / realização", "data", obrigatorio=calculavel),
    ]
    if uni != ValidadeUnidade.SEM_VALIDADE.value:
        campos.append(Campo("data_vencimento", "Data de vencimento", "data",
                            obrigatorio=uni == ValidadeUnidade.MANUAL.value,
                            ajuda="Em branco = calculada pela validade do tipo" if calculavel else None))
    campos += [
        Campo("numero_documento", "Nº do documento / certificado"),
        Campo("emissor", "Emissor / instituição"),
    ]
    if calculavel:
        campos.append(Campo("justificativa_ajuste", "Justificativa (se o vencimento diferir do calculado)", "area"))
    campos.append(Campo("observacoes", "Observações", "area"))
    return campos


def _campos_extensao(ctx: UsuarioContexto, tipo: dict) -> list[Campo]:
    cat = tipo["categoria"]
    forn = lambda: opcoes.fornecedores(ctx)  # noqa: E731
    if cat == Categoria.TREINAMENTO.value:
        ch = tipo.get("carga_horaria_padrao")
        return [
            Campo("tr_carga_horaria", "Carga horária (h)", "inteiro", extras={"min": 1, "max": 2000},
                  padrao=int(ch) if ch and ch == ch else None),
            Campo("tr_modalidade", "Modalidade", "select", opcoes=Modalidade.opcoes()),
            Campo("tr_instrutor", "Instrutor"),
            Campo("tr_instituicao_fornecedor_id", "Instituição (fornecedor)", "select", opcoes=forn),
            Campo("tr_nota_aproveitamento", "Nota / aproveitamento (%)", "decimal"),
        ]
    if cat == Categoria.EXAME.value:
        campos = [
            Campo("ex_tipo_aso", "Tipo de exame (ASO)", "select", opcoes=TipoASO.opcoes()),
            Campo("ex_clinica_fornecedor_id", "Clínica", "select", opcoes=forn),
            Campo("ex_medico_nome", "Médico examinador"),
            Campo("ex_medico_crm", "CRM"),
        ]
        if ctx.pode(Permissao.VER_DADOS_SAUDE):
            campos.append(Campo("ex_resultado", "Resultado", "select", opcoes=ResultadoASO.opcoes(),
                                ajuda="Dado pessoal sensível (LGPD). Não registre CID ou diagnóstico."))
        return campos
    if cat == Categoria.CONTRATO.value:
        return [
            Campo("ct_valor", "Valor (R$)", "decimal"),
            Campo("ct_aviso_previo_dias", "Aviso prévio (dias)", "inteiro", extras={"min": 0, "max": 365}),
            Campo("ct_renovacao_automatica", "Renovação automática", "bool"),
            Campo("ct_objeto", "Objeto do contrato", "area"),
        ]
    if cat == Categoria.EQUIPAMENTO.value:
        return [
            Campo("eq_tipo_servico", "Tipo de serviço", "select", opcoes=TipoServicoEquipamento.opcoes()),
            Campo("eq_laudo_numero", "Nº do laudo / ordem de serviço"),
            Campo("eq_executor_fornecedor_id", "Executor (fornecedor)", "select", opcoes=forn),
        ]
    return []


# ============================================================ formulários
def _form_vencimento(ctx: UsuarioContexto, acao: str, ident: int | None) -> None:
    svc = VencimentoService(ctx)
    tipos = opcoes.tipos_controle(ctx)
    valores: dict[str, Any] = {}
    vencimento_atual = None
    if acao in ("editar", "renovar"):
        valores = carregar(svc.obter, ident, padrao=None)
        if valores is None:
            _fechar()
            return
        tipo_id = valores["tipo_controle_id"]
        if tipo_id not in tipos:  # tipo inativado depois do lançamento
            tipos[tipo_id] = {"id": tipo_id, "nome": valores["tipo_nome"], "categoria": valores["categoria"],
                              "alvo_tipo": _valor(valores["alvo_tipo"]),
                              "validade_unidade": ValidadeUnidade.MANUAL.value, "validade_valor": None}
        vencimento_atual = valores.get("data_vencimento")
        if acao == "renovar":
            # mantém dados úteis do registro anterior; datas e nº do documento são novos
            for campo in ("data_emissao", "data_vencimento", "numero_documento", "justificativa_ajuste",
                          "observacoes", "ex_resultado", "tr_nota_aproveitamento"):
                valores.pop(campo, None)

    titulos = {"novo": "➕ Novo lançamento", "editar": "✏️ Editar lançamento", "renovar": "🔁 Renovar"}
    with st.container(border=True):
        st.subheader(titulos[acao])
        if acao == "novo":
            if not tipos:
                st.warning("Nenhum tipo de controle ativo. Cadastre em **Tipos de controle**.")
                if st.button("Voltar"):
                    _fechar()
                    st.rerun()
                return
            por_cat = sorted(tipos, key=lambda i: (tipos[i]["categoria"], tipos[i]["nome"]))
            tipo_id = st.selectbox(
                "Tipo de controle *", por_cat, index=None, placeholder="Selecione o que será controlado...",
                format_func=lambda i: f"{Categoria(tipos[i]['categoria']).rotulo} · {tipos[i]['nome']}",
                key=f"venc_tipo_{_versao()}",
            )
            if tipo_id is None:
                if st.button("Cancelar", key="venc_cancelar_sem_tipo"):
                    _fechar()
                    st.rerun()
                return
        tipo = tipos[tipo_id]
        if acao != "novo":
            st.markdown(f"**{tipo['nome']}** · {Categoria(tipo['categoria']).rotulo}")
            if acao == "renovar":
                st.caption(f"Registro atual vence em {formatar_data(vencimento_atual) or '—'}. "
                           "O registro atual será mantido no histórico como *Renovado*.")
        st.info(_descricao_validade(tipo))
        if valores.get("resultado_oculto"):
            st.caption("🔒 O resultado do ASO existe, mas seu perfil não tem acesso a dados de saúde. Ele não será alterado.")

        prefixo = f"venc_{acao}_{ident}_{tipo_id}_{_versao()}"
        with st.form(f"form_{prefixo}"):
            dados: dict[str, Any] = {}
            if acao == "novo":
                dados |= render_campos(_campo_alvo(ctx, tipo["alvo_tipo"]), valores, prefixo)
            dados |= render_campos(_campos_base(tipo), valores, prefixo)
            ext = _campos_extensao(ctx, tipo)
            if ext:
                st.markdown(f"**Dados do(a) {Categoria(tipo['categoria']).rotulo.lower()}**")
                dados |= render_campos(ext, valores, prefixo)
            st.caption("* campos obrigatórios · anexos são enviados após salvar, no painel do registro")
            c1, c2, _ = st.columns([1, 1, 4])
            salvar = c1.form_submit_button("💾 Salvar", type="primary")
            cancelar = c2.form_submit_button("Cancelar")
        if cancelar:
            _fechar()
            st.rerun()
        if salvar:
            dados = limpar_valores(dados)
            dados["tipo_controle_id"] = tipo_id
            if acao == "novo":
                ok, novo = executar(svc.criar, dados)
                msg = "Lançamento registrado."
            elif acao == "editar":
                ok, novo = executar(svc.atualizar, ident, dados)
                msg = "Lançamento atualizado."
            else:
                ok, novo = executar(svc.renovar, ident, dados)
                msg = "Renovação registrada. O registro anterior foi para o histórico."
            if ok:
                estado.flash(msg)
                _fechar()
                st.rerun()


def _form_lote(ctx: UsuarioContexto) -> None:
    svc = VencimentoService(ctx)
    tipos = {i: t for i, t in opcoes.tipos_controle(ctx).items() if t["alvo_tipo"] == AlvoTipo.COLABORADOR.value}
    with st.container(border=True):
        st.subheader("👥 Lançamento em lote (turma de treinamento / campanha de exames)")
        st.caption("Registros ativos do mesmo tipo para os colaboradores escolhidos serão renovados automaticamente.")
        tipo_id = st.selectbox(
            "Tipo de controle *", sorted(tipos, key=lambda i: tipos[i]["nome"]), index=None,
            format_func=lambda i: f"{Categoria(tipos[i]['categoria']).rotulo} · {tipos[i]['nome']}",
            placeholder="Selecione...", key=f"lote_tipo_{_versao()}",
        )
        if tipo_id is None:
            if st.button("Cancelar", key="lote_cancelar_sem_tipo"):
                _fechar()
                st.rerun()
            return
        tipo = tipos[tipo_id]
        st.info(_descricao_validade(tipo))
        colabs = opcoes.colaboradores(ctx)
        prefixo = f"lote_{tipo_id}_{_versao()}"
        with st.form(f"form_{prefixo}"):
            escolhidos = st.multiselect("Colaboradores *", list(colabs), format_func=lambda i: colabs[i],
                                        placeholder="Digite para buscar e selecione...")
            dados = render_campos(_campos_base(tipo), {}, prefixo)
            ext = [c for c in _campos_extensao(ctx, tipo) if c.nome != "ex_resultado"]
            if ext:
                dados |= render_campos(ext, {}, prefixo)
            c1, c2, _ = st.columns([1, 1, 4])
            salvar = c1.form_submit_button("💾 Lançar para todos", type="primary")
            cancelar = c2.form_submit_button("Cancelar")
        if cancelar:
            _fechar()
            st.rerun()
        if salvar:
            ok, r = executar(svc.criar_lote, tipo_id, escolhidos, limpar_valores(dados))
            if ok:
                estado.flash(f"Lote concluído: {r['criados']} novo(s) e {r['renovados']} renovado(s).")
                _fechar()
                st.rerun()


# ============================================================ painel do registro
def _painel_detalhes(d: dict) -> None:
    linhas = [
        ("Status", status_texto(d.get("status"))),
        ("Situação", rotulo(d.get("situacao"))),
        ("Emissão", formatar_data(d.get("data_emissao"))),
        ("Vencimento", formatar_data(d.get("data_vencimento")) or "—"),
        ("Nº documento", d.get("numero_documento") or "—"),
        ("Emissor", d.get("emissor") or "—"),
    ]
    if d.get("vencimento_ajustado_manual"):
        linhas.append(("Ajuste manual", d.get("justificativa_ajuste") or ""))
    extras = {
        "tr_carga_horaria": "Carga horária (h)", "tr_modalidade": "Modalidade", "tr_instrutor": "Instrutor",
        "ex_tipo_aso": "Tipo de ASO", "ex_medico_nome": "Médico", "ex_medico_crm": "CRM", "ex_resultado": "Resultado",
        "ct_valor": "Valor (R$)", "ct_aviso_previo_dias": "Aviso prévio (dias)",
        "eq_tipo_servico": "Serviço", "eq_laudo_numero": "Nº laudo",
    }
    for chave, rot in extras.items():
        if d.get(chave) not in (None, ""):
            linhas.append((rot, rotulo(d[chave])))
    if d.get("resultado_oculto"):
        linhas.append(("Resultado", "🔒 restrito ao seu perfil"))
    if d.get("motivo_cancelamento"):
        linhas.append(("Motivo do cancelamento", d["motivo_cancelamento"]))
    if d.get("observacoes"):
        linhas.append(("Observações", d["observacoes"]))
    c = st.columns(2)
    for i, (k, v) in enumerate(linhas):
        c[i % 2].markdown(f"**{k}:** {v}")


def _painel_anexos(ctx: UsuarioContexto, svc: VencimentoService, vid: int, ativo: bool) -> None:
    anexos = carregar(svc.listar_anexos, vid, padrao=None)
    if anexos is None:
        return
    chave_prep = f"anexo_preparado_{vid}"
    if anexos.empty:
        st.caption("Nenhum anexo.")
    for a in anexos.itertuples():
        c1, c2, c3 = st.columns([4, 1.4, 1])
        c1.markdown(f"📄 {a.nome_original} · {a.tamanho_bytes / 1024:.0f} KB")
        preparado = st.session_state.get(chave_prep)
        if preparado and preparado[0] == a.id:
            c2.download_button("⬇️ Baixar", data=preparado[3], file_name=preparado[1], mime=preparado[2],
                               key=f"dl_{a.id}")
        elif c2.button("Preparar download", key=f"prep_{a.id}"):
            ok, r = executar(svc.baixar_anexo, int(a.id))
            if ok:
                st.session_state[chave_prep] = (a.id, *r)
                st.rerun()
        if ctx.pode(Permissao.EDITAR_VENCIMENTOS) and c3.button("Remover", key=f"rm_{a.id}"):
            ok, _ = executar(svc.excluir_anexo, int(a.id))
            if ok:
                estado.flash("Anexo removido.")
                st.rerun()
    if ctx.pode(Permissao.EDITAR_VENCIMENTOS) and ativo:
        versao = st.session_state.get(f"upl_v_{vid}", 0)
        arquivo = st.file_uploader("Enviar anexo (PDF, PNG ou JPG)", type=["pdf", "png", "jpg", "jpeg"],
                                   key=f"upl_{vid}_{versao}")
        if arquivo is not None and st.button("📎 Enviar anexo", key=f"upl_btn_{vid}_{versao}", type="primary"):
            ok, _ = executar(svc.anexar, vid, arquivo.name, arquivo.getvalue())
            if ok:
                st.session_state[f"upl_v_{vid}"] = versao + 1
                estado.flash("Anexo enviado.")
                st.rerun()


def _painel_acoes(ctx: UsuarioContexto, svc: VencimentoService, vid: int, situacao: str) -> None:
    ativo = situacao == SituacaoVencimento.ATIVO.value
    if not ativo:
        st.caption("Registros renovados ou cancelados fazem parte do histórico e não podem ser alterados.")
    if ctx.pode(Permissao.EDITAR_VENCIMENTOS) and ativo:
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("🔁 Renovar", key=f"renovar_{vid}", type="primary"):
            _abrir(("renovar", vid))
        if c2.button("✏️ Editar", key=f"editar_{vid}"):
            _abrir(("editar", vid))
    if ctx.pode(Permissao.CANCELAR_VENCIMENTOS):
        if ativo:
            with st.expander("⛔ Cancelar lançamento"):
                st.caption("Use quando o registro foi lançado por engano ou perdeu a validade antes do prazo. "
                           "Se for uma renovação, o registro anterior volta a valer.")
                motivo = st.text_area("Motivo *", key=f"motivo_{vid}")
                if confirmar(f"cancelar_{vid}", "Confirmo o cancelamento", "Cancelar lançamento"):
                    ok, _ = executar(svc.cancelar, vid, motivo)
                    if ok:
                        estado.flash("Lançamento cancelado.")
                        st.rerun()
        if situacao != SituacaoVencimento.RENOVADO.value:
            with st.expander("🗑️ Excluir"):
                st.caption("Envia o registro para a lixeira.")
                if confirmar(f"excluir_venc_{vid}", "Confirmo a exclusão", "Excluir"):
                    ok, _ = executar(svc.excluir, vid)
                    if ok:
                        estado.flash("Lançamento excluído.")
                        st.rerun()


def _painel_registro(ctx: UsuarioContexto, linha: dict) -> None:
    svc = VencimentoService(ctx)
    vid = int(linha["id"])
    d = carregar(svc.obter, vid, padrao=None)
    if d is None:
        return
    situacao = _valor(d["situacao"])
    with st.container(border=True):
        st.markdown(f"### {status_texto(d['status'])} · {d['tipo_nome']}")
        st.caption(f"{linha.get('alvo', '')} · {linha.get('unidade') or 'Empresa (geral)'}")
        t1, t2, t3, t4 = st.tabs(["Detalhes", f"Anexos ({int(linha.get('anexos') or 0)})", "Histórico", "Ações"])
        with t1:
            _painel_detalhes(d)
        with t2:
            _painel_anexos(ctx, svc, vid, situacao == SituacaoVencimento.ATIVO.value)
        with t3:
            hist = carregar(svc.historico, vid, padrao=None)
            if hist is not None and not hist.empty:
                tabela_pesquisavel(
                    hist,
                    {"data_emissao": ColunaTabela("Emissão", "data"),
                     "data_vencimento": ColunaTabela("Vencimento", "data"),
                     "numero_documento": ColunaTabela("Nº documento"),
                     "situacao": ColunaTabela("Situação", "rotulo"),
                     "motivo_cancelamento": ColunaTabela("Motivo cancelamento")},
                    chave=f"hist_{vid}", titulo_exportacao="Historico", selecionavel=False,
                )
        with t4:
            _painel_acoes(ctx, svc, vid, situacao)


# ============================================================ página
def pagina(ctx: UsuarioContexto) -> None:
    st.title("🗓️ Vencimentos")
    estado.mostrar_flash()

    modo = st.session_state.get(MODO)
    if modo:
        if modo[0] == "lote":
            _form_lote(ctx)
        else:
            _form_vencimento(ctx, modo[0], modo[1] if len(modo) > 1 else None)
        return

    if ctx.pode(Permissao.EDITAR_VENCIMENTOS):
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("➕ Novo lançamento", type="primary"):
            _abrir(("novo", None))
        if b2.button("👥 Lançamento em lote"):
            _abrir(("lote",))

    unidades = opcoes.unidades(ctx, apenas_ativas=False)
    with st.expander("Filtros avançados", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        alvo = f1.selectbox("Aplica-se a", list(AlvoTipo.opcoes()), index=None, placeholder="Todos",
                            format_func=lambda a: AlvoTipo(a).rotulo)
        unidade_id = f2.selectbox("Unidade", list(unidades), index=None, placeholder="Todas",
                                  format_func=lambda i: unidades[i])
        de = f3.date_input("Vencimento de", value=None, format="DD/MM/YYYY")
        ate = f4.date_input("Vencimento até", value=None, format="DD/MM/YYYY")
        historico = st.toggle("Incluir histórico (renovados e cancelados)", value=False)
    filtro = FiltroVencimentos(
        alvo_tipo=alvo, unidade_id=unidade_id, vencimento_de=de, vencimento_ate=ate,
        situacoes=[s.value for s in SituacaoVencimento] if historico else [SituacaoVencimento.ATIVO.value],
    )
    df = carregar(VencimentoService(ctx).listar, filtro, padrao=None)
    if df is None:
        return
    if not df.empty:
        resumo = df["status"].value_counts()
        st.caption(" · ".join(
            f"{status_texto(s)}: **{int(resumo.get(s, 0))}**"
            for s in (StatusVencimento.VENCIDO.value, StatusVencimento.A_VENCER.value, StatusVencimento.VIGENTE.value)
        ))
    selecionado, _ = tabela_pesquisavel(
        df, COLUNAS, "venc", filtros=["status", "categoria", "tipo"], titulo_exportacao="Vencimentos",
    )
    if selecionado:
        _painel_registro(ctx, selecionado)
