"""Testes de integração dos services com SQLite real (arquivo temporário)."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from sst.domain.enums import Perfil  # noqa: E402
from sst.domain.exceptions import (  # noqa: E402
    AutenticacaoError,
    NaoEncontradoError,
    PermissaoNegadaError,
    RegraNegocioError,
    ValidacaoError,
)
from sst.services.auth_service import AuthService  # noqa: E402
from sst.services.cadastro_service import (  # noqa: E402
    CargoService,
    ColaboradorService,
    EquipamentoService,
    UnidadeService,
)
from sst.services.conformidade_service import ConformidadeService  # noqa: E402
from sst.services.tipo_controle_service import TipoControleService  # noqa: E402
from sst.services.usuario_service import UsuarioService  # noqa: E402
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService  # noqa: E402

CPF1, CPF2 = "52998224725", "11144477735"


def _tipo(ctx, nome):
    tipos = TipoControleService(ctx).listar()
    return int(tipos.loc[tipos["nome"] == nome, "id"].iloc[0])


def _base(ctx):
    u = UnidadeService(ctx).criar({"nome": "Matriz", "uf": "SP"})
    cargo = CargoService(ctx).criar({"nome": "Eletricista"})
    c = ColaboradorService(ctx).criar({"nome": "Ana Silva", "cpf": CPF1, "unidade_id": u, "cargo_id": cargo})
    return u, cargo, c


# ------------------------------------------------------------------ banco
def test_foreign_keys_ativas(banco):
    with banco.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_catalogo_semeado(admin):
    assert len(TipoControleService(admin).listar()) >= 20


# ------------------------------------------------------------------ cadastros
def test_crud_colaborador_completo(admin):
    u, cargo, cid = _base(admin)
    svc = ColaboradorService(admin)
    assert svc.obter(cid)["cpf"] == CPF1
    svc.atualizar(cid, {"nome": "Ana Souza", "cpf": CPF1, "unidade_id": u, "cargo_id": cargo})
    assert svc.obter(cid)["nome"] == "Ana Souza"
    df = svc.listar()
    assert df.loc[0, "unidade"] == "Matriz" and df.loc[0, "cargo"] == "Eletricista"
    with pytest.raises(RegraNegocioError):
        svc.criar({"nome": "Outra", "cpf": CPF1, "unidade_id": u})  # CPF duplicado
    svc.excluir(cid)
    assert svc.listar().empty
    assert len(svc.listar_excluidos()) == 1
    with pytest.raises(RegraNegocioError, match="lixeira"):
        svc.criar({"nome": "Outra", "cpf": CPF1, "unidade_id": u})
    svc.restaurar(cid)
    assert len(svc.listar()) == 1


def test_validacao_cpf_invalido(admin):
    u = UnidadeService(admin).criar({"nome": "Matriz"})
    with pytest.raises(ValidacaoError) as e:
        ColaboradorService(admin).criar({"nome": "Ana", "cpf": "123", "unidade_id": u})
    assert any("CPF" in m for m in e.value.erros)


def test_unidade_com_colaborador_nao_exclui(admin):
    u, _, _ = _base(admin)
    with pytest.raises(RegraNegocioError):
        UnidadeService(admin).excluir(u)


# ------------------------------------------------------------------ isolamento
def test_isolamento_entre_empresas(admin, admin_b):
    u, _, cid = _base(admin)
    assert ColaboradorService(admin_b).listar().empty
    with pytest.raises(NaoEncontradoError):
        ColaboradorService(admin_b).obter(cid)
    with pytest.raises(NaoEncontradoError):
        ColaboradorService(admin_b).excluir(cid)
    # B não consegue apontar para a unidade de A
    with pytest.raises(NaoEncontradoError):
        ColaboradorService(admin_b).criar({"nome": "Intrusa", "cpf": CPF2, "unidade_id": u})
    tipo_b = _tipo(admin_b, "ASO Periódico")
    with pytest.raises(NaoEncontradoError):
        VencimentoService(admin_b).criar({"tipo_controle_id": tipo_b, "colaborador_id": cid,
                                          "data_emissao": date.today()})


# ------------------------------------------------------------------ permissões
def test_consulta_nao_grava(admin):
    consulta = replace(admin, perfil=Perfil.CONSULTA)
    with pytest.raises(PermissaoNegadaError):
        UnidadeService(consulta).criar({"nome": "X1"})
    assert UnidadeService(consulta).listar() is not None


def test_escopo_por_unidade(admin):
    u1, _, c1 = _base(admin)
    u2 = UnidadeService(admin).criar({"nome": "Filial"})
    ColaboradorService(admin).criar({"nome": "Bruno Lima", "cpf": CPF2, "unidade_id": u2})
    tecnico = replace(admin, perfil=Perfil.TECNICO_SST, unidades_ids=(u1,))
    df = ColaboradorService(tecnico).listar()
    assert df["unidade_id"].tolist() == [u1]
    with pytest.raises(PermissaoNegadaError):
        ColaboradorService(tecnico).criar({"nome": "Carla Reis", "cpf": "39053344705", "unidade_id": u2})


# ------------------------------------------------------------------ vencimentos
def test_vencimento_calcula_data_e_status(admin):
    _, _, cid = _base(admin)
    tipo = _tipo(admin, "NR-35 Trabalho em Altura - Periódico")  # 24 meses, 60 dias
    vs = VencimentoService(admin)
    emissao = date.today() - timedelta(days=700)
    vid = vs.criar({"tipo_controle_id": tipo, "colaborador_id": cid, "data_emissao": emissao,
                    "tr_carga_horaria": 8})
    d = vs.obter(vid)
    assert d["data_vencimento"] > emissao
    assert d["status"] == "A_VENCER"
    assert d["tr_carga_horaria"] == 8
    df = vs.listar()
    assert df.loc[0, "alvo"] == "Ana Silva"
    assert bool(df.loc[0, "pendente_anexo"]) is True  # tipo exige anexo


def test_ajuste_manual_exige_justificativa(admin):
    _, _, cid = _base(admin)
    tipo = _tipo(admin, "ASO Periódico")
    vs = VencimentoService(admin)
    base = {"tipo_controle_id": tipo, "colaborador_id": cid, "data_emissao": date(2026, 1, 10),
            "data_vencimento": date(2026, 6, 10)}
    with pytest.raises(ValidacaoError, match="Justificativa"):
        vs.criar(base)
    vid = vs.criar(base | {"justificativa_ajuste": "Determinação do médico coordenador"})
    assert vs.obter(vid)["vencimento_ajustado_manual"] is True


def test_renovacao_preserva_historico_e_cancelamento_reativa(admin):
    _, _, cid = _base(admin)
    tipo = _tipo(admin, "ASO Periódico")
    vs = VencimentoService(admin)
    v1 = vs.criar({"tipo_controle_id": tipo, "colaborador_id": cid, "data_emissao": date(2025, 1, 10)})
    with pytest.raises(RegraNegocioError, match="Renovar"):
        vs.criar({"tipo_controle_id": tipo, "colaborador_id": cid, "data_emissao": date(2026, 1, 10)})
    v2 = vs.renovar(v1, {"data_emissao": date(2026, 1, 10)})
    assert vs.obter(v1)["situacao"].value == "RENOVADO"
    hist = vs.historico(v2)
    assert hist["id"].tolist() == [v1, v2]
    vs.cancelar(v2, "Lançado por engano")
    assert vs.obter(v1)["situacao"].value == "ATIVO"
    assert vs.listar(FiltroVencimentos(situacoes=["ATIVO"]))["id"].tolist() == [v1]


def test_lote_cria_e_renova(admin):
    u, _, c1 = _base(admin)
    c2 = ColaboradorService(admin).criar({"nome": "Bruno Lima", "cpf": CPF2, "unidade_id": u})
    tipo = _tipo(admin, "NR-35 Trabalho em Altura - Periódico")
    vs = VencimentoService(admin)
    vs.criar({"tipo_controle_id": tipo, "colaborador_id": c1, "data_emissao": date(2025, 1, 1)})
    r = vs.criar_lote(tipo, [c1, c2], {"data_emissao": date(2026, 10, 1), "tr_carga_horaria": 8})
    assert r == {"criados": 1, "renovados": 1}


def test_aso_resultado_oculto_para_tecnico(admin):
    _, _, cid = _base(admin)
    tipo = _tipo(admin, "ASO Periódico")
    vid = VencimentoService(admin).criar({"tipo_controle_id": tipo, "colaborador_id": cid,
                                          "data_emissao": date.today(), "ex_resultado": "APTO"})
    tecnico = replace(admin, perfil=Perfil.TECNICO_SST)
    d = VencimentoService(tecnico).obter(vid)
    assert d["ex_resultado"] is None and d["resultado_oculto"] is True
    # técnico edita sem apagar o resultado
    VencimentoService(tecnico).atualizar(vid, {"data_emissao": date.today(), "emissor": "Clínica"})
    assert VencimentoService(admin).obter(vid)["ex_resultado"].value == "APTO"


def test_anexo(admin):
    _, _, cid = _base(admin)
    tipo = _tipo(admin, "ASO Periódico")
    vs = VencimentoService(admin)
    vid = vs.criar({"tipo_controle_id": tipo, "colaborador_id": cid, "data_emissao": date.today()})
    aid = vs.anexar(vid, "aso.pdf", b"%PDF-1.4 teste")
    nome, mime, conteudo = vs.baixar_anexo(aid)
    assert (nome, mime, conteudo) == ("aso.pdf", "application/pdf", b"%PDF-1.4 teste")
    assert bool(vs.listar().loc[0, "pendente_anexo"]) is False
    with pytest.raises(ValidacaoError):
        vs.anexar(vid, "falso.pdf", b"nao e pdf")


def test_equipamento_vencimento(admin):
    u = UnidadeService(admin).criar({"nome": "Matriz"})
    eid = EquipamentoService(admin).criar({"unidade_id": u, "descricao": "Extintor 6kg", "tipo": "Extintor",
                                           "patrimonio": "EXT-1"})
    tipo = _tipo(admin, "Extintor - Recarga/Manutenção Nível 2")
    vid = VencimentoService(admin).criar({"tipo_controle_id": tipo, "equipamento_id": eid,
                                          "data_emissao": date.today() - timedelta(days=400)})
    assert VencimentoService(admin).obter(vid)["status"] == "VENCIDO"
    with pytest.raises(RegraNegocioError):
        EquipamentoService(admin).excluir(eid)


# ------------------------------------------------------------------ conformidade
def test_pendencias(admin):
    _, cargo, cid = _base(admin)
    aso = _tipo(admin, "ASO Periódico")
    nr10 = _tipo(admin, "NR-10 Básico - Reciclagem")
    cs = ConformidadeService(admin)
    cs.definir_requisitos(cargo, [aso, nr10])
    VencimentoService(admin).criar({"tipo_controle_id": aso, "colaborador_id": cid, "data_emissao": date.today()})
    pend = cs.pendencias()
    assert pend["tipo_controle_id"].tolist() == [nr10]
    assert cs.indice_conformidade() == (50.0, 1, 2)


# ------------------------------------------------------------------ autenticação
def test_login_e_bloqueio(admin):
    ctx, trocar = AuthService.autenticar("ADMIN@a.com.br", "SenhaForte2026")
    assert ctx.tenant_id == admin.tenant_id and trocar is False
    for _ in range(5):
        with pytest.raises(AutenticacaoError):
            AuthService.autenticar("admin@a.com.br", "errada12345")
    with pytest.raises(AutenticacaoError):  # bloqueado mesmo com a senha certa
        AuthService.autenticar("admin@a.com.br", "SenhaForte2026")
    with pytest.raises(AutenticacaoError):
        AuthService.autenticar("naoexiste@a.com.br", "SenhaForte2026")


def test_usuarios_senha_temporaria_e_ultimo_admin(admin):
    us = UsuarioService(admin)
    uid, senha = us.criar({"nome": "Técnico Um", "email": "tec@a.com.br", "perfil": "TECNICO_SST"})
    ctx, trocar = AuthService.autenticar("tec@a.com.br", senha)
    assert trocar is True and ctx.perfil is Perfil.TECNICO_SST
    AuthService.trocar_senha(ctx, senha, "NovaSenha2026x", "NovaSenha2026x")
    assert AuthService.autenticar("tec@a.com.br", "NovaSenha2026x")[1] is False
    with pytest.raises(RegraNegocioError):
        us.atualizar(admin.usuario_id, {"nome": "Admin", "email": "admin@a.com.br", "perfil": "CONSULTA"})
