"""Administração: usuários, auditoria e configurações (empresa + lixeira)."""

from __future__ import annotations

import streamlit as st

from sst.domain.enums import AcaoAuditoria, Perfil
from sst.domain.permissoes import UsuarioContexto
from sst.services.auditoria_service import AuditoriaService
from sst.services.cadastro_service import (
    CargoService,
    ColaboradorService,
    EquipamentoService,
    FornecedorService,
    SetorService,
    UnidadeService,
)
from sst.services.tenant_service import TenantService
from sst.services.tipo_controle_service import TipoControleService
from sst.services.usuario_service import UsuarioService
from sst.ui import estado, opcoes
from sst.ui.componentes import (
    Campo,
    ColunaTabela,
    carregar,
    confirmar,
    executar,
    limpar_valores,
    render_campos,
    tabela_pesquisavel,
)

PERFIS_ATRIBUIVEIS = {p.value: p.rotulo for p in Perfil if p is not Perfil.SUPERADMIN}
DESCRICAO_PERFIS = (
    "**Administrador:** tudo, inclusive usuários e configurações · "
    "**Gestor SST:** cadastros, vencimentos, catálogo, cancelamentos e dados de saúde · "
    "**Técnico SST:** cadastros e vencimentos (sem resultado de ASO e sem cancelar) · "
    "**Consulta:** somente leitura e exportação"
)


# ====================================================================== usuários
def _campos_usuario(ctx):
    return [
        Campo("nome", "Nome", obrigatorio=True),
        Campo("email", "E-mail (login)", obrigatorio=True),
        Campo("perfil", "Perfil", "select", obrigatorio=True, opcoes=PERFIS_ATRIBUIVEIS),
        Campo("ativo", "Ativo", "bool", padrao=True),
        Campo("unidades_ids", "Unidades permitidas (vazio = todas)", "multiselect",
              opcoes=lambda: opcoes.unidades(ctx, apenas_ativas=False), largura_total=True),
    ]


def pagina_usuarios(ctx: UsuarioContexto) -> None:
    st.title("🔑 Usuários")
    estado.mostrar_flash()
    st.caption(DESCRICAO_PERFIS)
    svc = UsuarioService(ctx)
    chave_modo = "usuarios__modo"
    versao = st.session_state.get("usuarios__v", 0)

    senha_exibir = st.session_state.pop("usuarios__senha", None)
    if senha_exibir:
        st.success(
            f"Senha temporária de **{senha_exibir[0]}**: `{senha_exibir[1]}`  \n"
            "Anote e entregue ao usuário por um canal seguro. Ela não será exibida novamente "
            "e deverá ser trocada no primeiro acesso."
        )

    modo = st.session_state.get(chave_modo)
    if modo:
        acao, ident = modo
        valores = carregar(svc.obter, ident, padrao={}) if ident else {}
        with st.container(border=True):
            st.subheader("Novo usuário" if acao == "novo" else "Editar usuário")
            with st.form(f"form_usuario_{acao}_{ident}_{versao}"):
                dados = render_campos(_campos_usuario(ctx), valores, f"usr_{acao}_{ident}_{versao}")
                c1, c2, _ = st.columns([1, 1, 4])
                salvar = c1.form_submit_button("💾 Salvar", type="primary")
                cancelar = c2.form_submit_button("Cancelar")
            if cancelar or salvar:
                ok = cancelar
                if salvar:
                    dados = limpar_valores(dados)
                    dados["unidades_ids"] = dados.get("unidades_ids") or []
                    if acao == "novo":
                        ok, r = executar(svc.criar, dados)
                        if ok:
                            st.session_state["usuarios__senha"] = (dados["email"], r[1])
                    else:
                        ok, _ = executar(svc.atualizar, ident, dados)
                        if ok:
                            estado.flash("Usuário atualizado.")
                if ok:
                    st.session_state[chave_modo] = None
                    st.session_state["usuarios__v"] = versao + 1
                    st.rerun()
        return

    if st.button("➕ Novo usuário", type="primary"):
        st.session_state[chave_modo] = ("novo", None)
        st.rerun()
    df = carregar(svc.listar, padrao=None)
    if df is None:
        return
    sel, _ = tabela_pesquisavel(
        df,
        {
            "nome": ColunaTabela("Nome"), "email": ColunaTabela("E-mail"), "perfil": ColunaTabela("Perfil", "rotulo"),
            "unidades": ColunaTabela("Unidades"), "ativo": ColunaTabela("Ativo", "bool"),
            "ultimo_login_em": ColunaTabela("Último acesso", "datahora"),
            "bloqueado_ate": ColunaTabela("Bloqueado até", "datahora"),
        },
        chave="usuarios", filtros=["perfil"], titulo_exportacao="Usuarios",
    )
    if sel:
        uid = int(sel["id"])
        with st.container(border=True):
            st.markdown(f"**Selecionado:** {sel['nome']} ({sel['email']})")
            c1, c2 = st.columns([1, 3])
            if c1.button("✏️ Editar", key=f"usr_edit_{uid}"):
                st.session_state[chave_modo] = ("editar", uid)
                st.rerun()
            with c2.expander("🔄 Gerar nova senha temporária (também desbloqueia)"):
                if confirmar(f"reset_{uid}", "Confirmo o reset de senha deste usuário", "Gerar senha"):
                    ok, senha = executar(svc.resetar_senha, uid)
                    if ok:
                        st.session_state["usuarios__senha"] = (sel["email"], senha)
                        st.rerun()


# ====================================================================== auditoria
def pagina_auditoria(ctx: UsuarioContexto) -> None:
    st.title("🧾 Auditoria")
    st.caption("Registro imutável de quem fez o quê e quando. Dados de saúde aparecem mascarados (***).")
    c1, c2, c3 = st.columns(3)
    de = c1.date_input("De", value=None, format="DD/MM/YYYY")
    ate = c2.date_input("Até", value=None, format="DD/MM/YYYY")
    acao = c3.selectbox("Ação", list(AcaoAuditoria.opcoes()), index=None, placeholder="Todas",
                        format_func=lambda a: AcaoAuditoria(a).rotulo)
    df = carregar(AuditoriaService(ctx).listar, de, ate, None, acao, padrao=None)
    if df is None:
        return
    tabela_pesquisavel(
        df,
        {
            "criado_em": ColunaTabela("Data/hora", "datahora"), "usuario_email": ColunaTabela("Usuário"),
            "acao": ColunaTabela("Ação", "rotulo"), "entidade": ColunaTabela("Entidade"),
            "entidade_id": ColunaTabela("ID", "numero"), "dados_antes": ColunaTabela("Antes"),
            "dados_depois": ColunaTabela("Depois"),
        },
        chave="auditoria", filtros=["entidade", "usuario_email"], titulo_exportacao="Auditoria",
        selecionavel=False, altura=520,
    )
    st.caption("Exibe os 5.000 eventos mais recentes do filtro.")


# ====================================================================== configurações
LIXEIRA = {
    "Unidades": UnidadeService, "Setores": SetorService, "Cargos": CargoService,
    "Colaboradores": ColaboradorService, "Equipamentos": EquipamentoService,
    "Fornecedores": FornecedorService, "Tipos de controle": TipoControleService,
}


def pagina_configuracoes(ctx: UsuarioContexto) -> None:
    st.title("⚙️ Configurações")
    estado.mostrar_flash()
    t1, t2 = st.tabs(["Empresa", "Lixeira"])
    with t1:
        svc = TenantService(ctx)
        dados = carregar(svc.obter, padrao=None)
        if dados is not None:
            with st.form("config_empresa"):
                v = render_campos(
                    [
                        Campo("nome", "Nome da empresa", obrigatorio=True),
                        Campo("antecedencia_padrao_dias", "Antecedência padrão de alerta (dias)", "inteiro",
                              obrigatorio=True, extras={"min": 0, "max": 365}),
                        Campo("email_alertas", "E-mail geral para alertas", largura_total=True),
                    ],
                    dados, "cfg_emp",
                )
                if st.form_submit_button("💾 Salvar", type="primary"):
                    ok, _ = executar(svc.atualizar, limpar_valores(v))
                    if ok:
                        estado.flash("Configurações salvas.")
                        st.rerun()
    with t2:
        st.caption("Registros excluídos podem ser restaurados aqui. Vencimentos excluídos aparecem no histórico.")
        nome = st.selectbox("Cadastro", list(LIXEIRA))
        svc_l = LIXEIRA[nome](ctx)
        df = carregar(svc_l.listar_excluidos, padrao=None)
        if df is None:
            return
        sel, _ = tabela_pesquisavel(
            df, {"descricao": ColunaTabela("Registro"), "excluido_em": ColunaTabela("Excluído em", "datahora")},
            chave=f"lixeira_{nome}", titulo_exportacao="Lixeira",
        )
        if sel and confirmar(f"restaurar_{nome}_{sel['id']}", f"Restaurar “{sel['descricao']}”", "Restaurar"):
            ok, _ = executar(svc_l.restaurar, int(sel["id"]))
            if ok:
                estado.flash("Registro restaurado.")
                st.rerun()
