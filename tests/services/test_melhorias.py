"""Melhorias: perfil do colaborador, CNPJ, CPF/LGPD, remoção do CBO, migração e treinamentos."""

import io
import json
import sqlite3
import urllib.error
from dataclasses import replace
from datetime import date, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, text  # noqa: E402

from sst.domain.enums import Perfil  # noqa: E402
from sst.domain.exceptions import PermissaoNegadaError, RegraNegocioError, ValidacaoError  # noqa: E402
from sst.domain.validadores import mascarar_cpf  # noqa: E402
from sst.infra import consulta_cpf  # noqa: E402
from sst.infra.consulta_cnpj import ConsultaCNPJError, consultar_cnpj  # noqa: E402
from sst.infra.db import migracoes  # noqa: E402
from sst.services.auditoria_service import AuditoriaService  # noqa: E402
from sst.services.cadastro_service import (  # noqa: E402
    CargoService,
    ColaboradorService,
    FornecedorService,
    SetorService,
    UnidadeService,
    consultar_cnpj_publico,
)
from sst.services.dashboard_service import DashboardService  # noqa: E402
from sst.services.tipo_controle_service import TipoControleService  # noqa: E402
from sst.services.treinamento_service import TreinamentoService  # noqa: E402
from sst.services.vencimento_service import FiltroVencimentos, VencimentoService  # noqa: E402

CPF1, CPF2, CPF3 = "52998224725", "11144477735", "39053344705"
NR35 = "NR-35 Trabalho em Altura - Periódico"
ASO = "ASO Periódico"


def _tipo(ctx, nome):
    t = TipoControleService(ctx).listar()
    return int(t.loc[t["nome"] == nome, "id"].iloc[0])


def _estrutura(ctx):
    u = UnidadeService(ctx).criar({"nome": "Matriz", "uf": "SP"})
    s1 = SetorService(ctx).criar({"unidade_id": u, "nome": "Manutenção"})
    s2 = SetorService(ctx).criar({"unidade_id": u, "nome": "Produção"})
    cargo = CargoService(ctx).criar({"nome": "Eletricista"})
    a = ColaboradorService(ctx).criar({"nome": "Ana Silva", "cpf": CPF1, "unidade_id": u, "setor_id": s1, "cargo_id": cargo})
    b = ColaboradorService(ctx).criar({"nome": "Bruno Lima", "cpf": CPF2, "unidade_id": u, "setor_id": s2})
    c = ColaboradorService(ctx).criar({"nome": "Carla Reis", "cpf": CPF3, "unidade_id": u, "setor_id": s1})
    return u, s1, s2, a, b, c


# ===================================================================== migração
def test_migracao_acrescenta_colunas_preserva_dados_e_faz_backup(tmp_path):
    from sst.infra.db.engine import criar_tabelas

    caminho = tmp_path / "antigo.db"
    e = create_engine(f"sqlite:///{caminho}")
    criar_tabelas(e)
    with e.begin() as con:  # simula banco da versão anterior (sem as colunas novas)
        for col in ("nome_fantasia", "cep", "cnae", "situacao_cadastral", "razao_social"):
            con.execute(text(f"ALTER TABLE unidades DROP COLUMN {col}"))
        con.execute(text("INSERT INTO tenants (nome, plano, ativo, antecedencia_padrao_dias, criado_em, atualizado_em) VALUES ('T', 'P', 1, 30, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        con.execute(text("INSERT INTO unidades (tenant_id, nome, cnpj, ativo, criado_em, atualizado_em) VALUES (1, 'Filial antiga', '11222333000181', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        con.execute(text("INSERT INTO cargos (tenant_id, nome, cbo, ativo, criado_em, atualizado_em) VALUES (1, 'Soldador', '7243-15', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    assert [c for t, c, _ in migracoes.pendentes(e) if t == "unidades"]
    feito = migracoes.aplicar(e)
    assert "unidades.cnae" in feito and migracoes.pendentes(e) == []
    with e.connect() as con:
        assert con.execute(text("SELECT nome, cnpj FROM unidades")).one() == ("Filial antiga", "11222333000181")
        assert con.execute(text("SELECT cbo FROM cargos")).scalar() == "7243-15"  # CBO preservado
    backups = list((tmp_path / "backups").glob("sst-antes-migracao-*.db"))
    assert len(backups) == 1
    assert sqlite3.connect(backups[0]).execute("SELECT nome FROM unidades").fetchone() == ("Filial antiga",)
    assert migracoes.aplicar(e) == []  # idempotente
    e.dispose()


# ===================================================================== CBO
def test_cbo_fora_do_formulario_e_preservado_na_edicao(admin, banco):
    from sst.schemas.cadastros import CargoIn

    assert "cbo" not in CargoIn.model_fields
    svc = CargoService(admin)
    cid = svc.criar({"nome": "Soldador"})
    with banco.begin() as con:
        con.execute(text("UPDATE cargos SET cbo = '7243-15' WHERE id = :i"), {"i": cid})
    svc.atualizar(cid, {"nome": "Soldador MIG", "descricao": "Solda"})
    with banco.connect() as con:
        assert con.execute(text("SELECT nome, cbo FROM cargos WHERE id = :i"), {"i": cid}).one() == ("Soldador MIG", "7243-15")


# ===================================================================== CNPJ
class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


RESPOSTA_API = {
    "razao_social": "EMPRESA EXEMPLO LTDA", "nome_fantasia": "EXEMPLO", "descricao_tipo_de_logradouro": "RUA",
    "logradouro": "DAS FLORES", "numero": "100", "complemento": "SALA 2", "bairro": "CENTRO", "municipio": "SAO PAULO",
    "uf": "SP", "cep": "01001000", "cnae_fiscal": 7119703, "cnae_fiscal_descricao": "Serviços de desenho técnico",
    "descricao_situacao_cadastral": "ATIVA",
}


def test_consulta_cnpj_preenche_campos():
    pedidos = []

    def abrir(req, timeout):
        pedidos.append((req.full_url, timeout))
        return _Resp(json.dumps(RESPOSTA_API).encode())

    d = consultar_cnpj("11.222.333/0001-81", abrir=abrir)
    assert pedidos[0][0].endswith("/11222333000181")
    assert (d.razao_social, d.nome_fantasia, d.cidade, d.uf, d.cep) == ("EMPRESA EXEMPLO LTDA", "EXEMPLO", "SAO PAULO", "SP", "01001000")
    assert d.endereco == "RUA DAS FLORES, 100, SALA 2, CENTRO"
    assert d.cnae == "7119-7/03 Serviços de desenho técnico"
    assert d.situacao_cadastral == "ATIVA"


@pytest.mark.parametrize("erro,trecho", [
    (urllib.error.HTTPError("u", 404, "nf", {}, None), "não encontrado"),
    (urllib.error.HTTPError("u", 429, "lim", {}, None), "Limite"),
    (urllib.error.HTTPError("u", 503, "x", {}, None), "indisponível"),
    (urllib.error.URLError("sem rede"), "Preencha manualmente"),
    (TimeoutError(), "Preencha manualmente"),
])
def test_consulta_cnpj_trata_falhas(erro, trecho):
    def abrir(req, timeout):
        raise erro

    with pytest.raises(ConsultaCNPJError, match=trecho):
        consultar_cnpj("11222333000181", abrir=abrir)


def test_consulta_cnpj_valida_antes_e_resposta_invalida():
    chamado = []
    with pytest.raises(ConsultaCNPJError, match="inválido"):
        consultar_cnpj("11222333000180", abrir=lambda *a, **k: chamado.append(1))
    with pytest.raises(ConsultaCNPJError, match="alfanumérico"):
        consultar_cnpj("12ABC34501DE35", abrir=lambda *a, **k: chamado.append(1))
    assert not chamado  # nem chega a chamar a API
    with pytest.raises(ConsultaCNPJError, match="inválida"):
        consultar_cnpj("11222333000181", abrir=lambda *a, **k: _Resp(b"<html>erro</html>"))


def test_consulta_cnpj_exige_permissao_de_cadastro(admin):
    consulta = replace(admin, perfil=Perfil.CONSULTA)
    with pytest.raises(PermissaoNegadaError):
        consultar_cnpj_publico(consulta, "11222333000181")


def test_dados_do_cnpj_gravados_e_editaveis(admin):
    svc = FornecedorService(admin)
    fid = svc.criar({"razao_social": "Clínica X", "cnpj": "11222333000181", "nome_fantasia": "X Saúde",
                     "cnae": "8630-5/03", "situacao_cadastral": "ATIVA", "endereco": "Rua A, 1",
                     "cidade": "Campinas", "uf": "sp", "cep": "13010-000"})
    f = svc.obter(fid)
    assert (f["nome_fantasia"], f["uf"], f["cep"]) == ("X Saúde", "SP", "13010000")
    with pytest.raises(ValidacaoError, match="CEP"):
        svc.atualizar(fid, {"razao_social": "Clínica X", "cep": "123"})
    uid = UnidadeService(admin).criar({"nome": "Filial", "cnpj": "11222333000181", "razao_social": "EMPRESA LTDA",
                                       "cnae": "4321-5/00"})
    assert UnidadeService(admin).obter(uid)["razao_social"] == "EMPRESA LTDA"


# ===================================================================== CPF / LGPD
def test_cpf_mascarado_e_revelacao_auditada(admin):
    _, _, _, a, _, _ = _estrutura(admin)
    svc = ColaboradorService(admin)
    p = svc.perfil(a)
    assert "cpf" not in p and p["cpf_mascarado"] == "***.982.247-**"
    assert (p["setor"], p["cargo"], p["unidade"], p["empresa"]) == ("Manutenção", "Eletricista", "Matriz", "Empresa A")
    assert svc.revelar_cpf(a) == "529.982.247-25"
    aud = AuditoriaService(admin).listar()
    assert ((aud["acao"] == "VISUALIZAR_SENSIVEL") & (aud["entidade"] == "Colaborador")).any()
    with pytest.raises(PermissaoNegadaError):
        ColaboradorService(replace(admin, perfil=Perfil.CONSULTA)).revelar_cpf(a)
    assert ColaboradorService(replace(admin, perfil=Perfil.CONSULTA)).perfil(a)["cpf_mascarado"].startswith("***")


def test_cpf_sem_provedor_por_padrao_e_mascara():
    assert consulta_cpf.obter_provedor() is None
    assert mascarar_cpf("529.982.247-25") == "***.982.247-**"
    assert mascarar_cpf("123") == ""


# ===================================================================== perfil: vários ASOs e treinamentos
def test_perfil_reune_asos_treinamentos_e_renovacoes(admin):
    _, _, _, a, _, _ = _estrutura(admin)
    v = VencimentoService(admin)
    hoje = date.today()
    v1 = v.criar({"tipo_controle_id": _tipo(admin, ASO), "colaborador_id": a, "data_emissao": hoje - timedelta(days=400)})
    v.criar({"tipo_controle_id": _tipo(admin, ASO), "colaborador_id": a, "data_emissao": hoje - timedelta(days=10)},
            renovar_existente=True)
    v.criar({"tipo_controle_id": _tipo(admin, NR35), "colaborador_id": a, "data_emissao": hoje})
    v.criar({"tipo_controle_id": _tipo(admin, "NR-10 Básico - Reciclagem"), "colaborador_id": a, "data_emissao": hoje})
    v.anexar(v1, "aso.pdf", b"%PDF-1.4 teste")
    todos = v.listar(FiltroVencimentos(colaborador_id=a, situacoes=["ATIVO", "RENOVADO", "CANCELADO"]))
    asos = todos[todos["categoria"] == "EXAME"]
    assert sorted(asos["situacao"]) == ["ATIVO", "RENOVADO"]
    assert (todos["categoria"] == "TREINAMENTO").sum() == 2
    assert int(todos.loc[todos["id"] == v1, "anexos"].iloc[0]) == 1
    assert set(todos["setor"]) == {"Manutenção"}


# ===================================================================== treinamentos
def test_turma_cria_registro_individual_por_participante(admin):
    _, s1, _, a, b, c = _estrutura(admin)
    svc = TreinamentoService(admin)
    hoje = date.today()
    turma, r = svc.registrar_turma({"tipo_controle_id": _tipo(admin, NR35), "data_realizacao": hoje,
                                    "instrutor": "João", "local": "Sala 1"}, [a, b, a])
    assert r == {"criados": 2, "renovados": 0}
    part = svc.participantes(turma)
    assert sorted(part["colaborador"]) == ["Ana Silva", "Bruno Lima"]
    assert set(part["turma_id"]) == {turma}
    det = VencimentoService(admin).obter(int(part["id"].iloc[0]))
    assert det["tr_carga_horaria"] == 8 and det["tr_instrutor"] == "João"  # carga padrão do catálogo
    assert set(part["data_vencimento"]) == {hoje.replace(year=hoje.year + 2) if not (hoje.month == 2 and hoje.day == 29) else date(hoje.year + 2, 2, 28)}
    turmas = svc.listar_turmas()
    assert turmas.loc[0, "participantes"] == 2
    # adicionar participante depois
    assert svc.adicionar_participantes(turma, [c]) == {"criados": 1, "renovados": 0}
    assert len(svc.participantes(turma)) == 3


def test_nova_turma_renova_sem_duplicar(admin):
    _, _, _, a, b, _ = _estrutura(admin)
    svc = TreinamentoService(admin)
    t = _tipo(admin, NR35)
    d0 = date.today() - timedelta(days=700)
    svc.registrar_turma({"tipo_controle_id": t, "data_realizacao": d0}, [a])
    with pytest.raises(RegraNegocioError, match="Ana Silva"):  # mesma data = duplicidade
        svc.registrar_turma({"tipo_controle_id": t, "data_realizacao": d0}, [a, b])
    assert len(svc.listar_turmas()) == 1  # nada gravado (tudo ou nada)
    _, r = svc.registrar_turma({"tipo_controle_id": t, "data_realizacao": date.today()}, [a, b])
    assert r == {"criados": 1, "renovados": 1}
    hist = svc.listar_realizados(colaborador_id=a, incluir_historico=True)
    assert sorted(hist["situacao"]) == ["ATIVO", "RENOVADO"]
    assert len(svc.listar_realizados(colaborador_id=a)) == 1


def test_turma_valida_tipo_participantes_e_permissao(admin):
    _, _, _, a, _, _ = _estrutura(admin)
    svc = TreinamentoService(admin)
    with pytest.raises(RegraNegocioError, match="Treinamento"):
        svc.registrar_turma({"tipo_controle_id": _tipo(admin, ASO), "data_realizacao": date.today()}, [a])
    with pytest.raises(ValidacaoError):
        svc.registrar_turma({"tipo_controle_id": _tipo(admin, NR35), "data_realizacao": date.today()}, [])
    with pytest.raises(PermissaoNegadaError):
        TreinamentoService(replace(admin, perfil=Perfil.CONSULTA)).registrar_turma(
            {"tipo_controle_id": _tipo(admin, NR35), "data_realizacao": date.today()}, [a])


def test_filtros_e_relatorios_de_treinamentos(admin):
    _, s1, s2, a, b, c = _estrutura(admin)
    svc = TreinamentoService(admin)
    svc.registrar_turma({"tipo_controle_id": _tipo(admin, NR35), "data_realizacao": date.today()}, [a, b])
    svc.registrar_turma({"tipo_controle_id": _tipo(admin, "NR-10 Básico - Reciclagem"),
                         "data_realizacao": date.today() - timedelta(days=800)}, [c])
    assert set(svc.listar_realizados(norma="NR-35")["colaborador"]) == {"Ana Silva", "Bruno Lima"}
    assert set(svc.listar_realizados(setor_id=s1)["colaborador"]) == {"Ana Silva", "Carla Reis"}
    assert set(svc.listar_realizados(colaborador_id=b)["tipo"]) == {NR35}
    vencidos = svc.listar_realizados(status=["VENCIDO"])
    assert list(vencidos["colaborador"]) == ["Carla Reis"]
    por_nr = svc.resumo_por(svc.listar_realizados(), "norma").set_index("norma")
    assert por_nr.loc["NR-35", "VIGENTE"] == 2 and por_nr.loc["NR-10", "VENCIDO"] == 1
    assert len(svc.listar_turmas(norma="NR-10")) == 1
    cat = svc.catalogo()
    assert not cat.empty and cat["norma"].notna().any()


def test_turmas_isoladas_entre_empresas(admin, admin_b):
    _, _, _, a, _, _ = _estrutura(admin)
    turma, _ = TreinamentoService(admin).registrar_turma(
        {"tipo_controle_id": _tipo(admin, NR35), "data_realizacao": date.today()}, [a])
    outro = TreinamentoService(admin_b)
    assert outro.listar_turmas().empty and outro.listar_realizados().empty
    with pytest.raises(Exception):
        outro.participantes(turma)
    u_b = UnidadeService(admin_b).criar({"nome": "Matriz B"})
    cb = ColaboradorService(admin_b).criar({"nome": "Diego", "cpf": CPF1, "unidade_id": u_b})
    with pytest.raises(Exception):
        outro.adicionar_participantes(turma, [cb])
    with pytest.raises(Exception):  # colaborador de outra empresa não entra na turma
        TreinamentoService(admin).adicionar_participantes(turma, [cb])


def test_dashboard_inclui_treinamentos_com_setor(admin):
    _, _, _, a, _, _ = _estrutura(admin)
    TreinamentoService(admin).registrar_turma({"tipo_controle_id": _tipo(admin, NR35),
                                               "data_realizacao": date.today()}, [a])
    base = DashboardService(admin).base()
    linha = base[base["categoria"] == "TREINAMENTO"].iloc[0]
    assert linha["setor"] == "Manutenção" and linha["norma"] == "NR-35" and linha["turma_id"] > 0
