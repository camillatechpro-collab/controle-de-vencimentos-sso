from datetime import date

import pytest

from sst.domain.datas import adicionar_meses, calcular_vencimento
from sst.domain.enums import Perfil, SituacaoVencimento, StatusVencimento, ValidadeUnidade
from sst.domain.exceptions import PermissaoNegadaError
from sst.domain.permissoes import Permissao, UsuarioContexto
from sst.domain.status import calcular_status, dias_restantes
from sst.domain.validadores import (
    formatar_cnpj,
    problemas_senha,
    validar_cnpj,
    validar_cpf,
    validar_email,
)
from sst.infra.seguranca import gerar_hash_senha, gerar_senha_temporaria, verificar_senha

HOJE = date(2026, 11, 8)


# ---------------- datas ----------------
@pytest.mark.parametrize(
    "inicio,meses,esperado",
    [
        (date(2025, 1, 31), 1, date(2025, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),  # bissexto
        (date(2025, 11, 15), 2, date(2026, 1, 15)),  # virada de ano
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2025, 5, 10), 24, date(2027, 5, 10)),
    ],
)
def test_adicionar_meses(inicio, meses, esperado):
    assert adicionar_meses(inicio, meses) == esperado


def test_calcular_vencimento_unidades():
    e = date(2026, 1, 10)
    assert calcular_vencimento(e, 30, ValidadeUnidade.DIAS) == date(2026, 2, 9)
    assert calcular_vencimento(e, 24, ValidadeUnidade.MESES) == date(2028, 1, 10)
    assert calcular_vencimento(e, 5, ValidadeUnidade.ANOS) == date(2031, 1, 10)
    assert calcular_vencimento(e, 12, ValidadeUnidade.MANUAL) is None
    assert calcular_vencimento(e, None, ValidadeUnidade.SEM_VALIDADE) is None
    assert calcular_vencimento(None, 12, ValidadeUnidade.MESES) is None


# ---------------- status ----------------
@pytest.mark.parametrize(
    "venc,situacao,esperado",
    [
        (date(2026, 11, 7), "ATIVO", StatusVencimento.VENCIDO),       # ontem
        (date(2026, 11, 8), "ATIVO", StatusVencimento.A_VENCER),      # vence hoje
        (date(2027, 1, 7), "ATIVO", StatusVencimento.A_VENCER),       # exatamente 60 dias
        (date(2027, 1, 8), "ATIVO", StatusVencimento.VIGENTE),        # 61 dias
        (None, "ATIVO", StatusVencimento.SEM_VALIDADE),
        (date(2020, 1, 1), "RENOVADO", StatusVencimento.RENOVADO),
        (date(2020, 1, 1), "CANCELADO", StatusVencimento.CANCELADO),
    ],
)
def test_calcular_status(venc, situacao, esperado):
    assert calcular_status(venc, SituacaoVencimento(situacao), 60, HOJE) is esperado


def test_dias_restantes():
    assert dias_restantes(date(2026, 11, 18), HOJE) == 10
    assert dias_restantes(date(2026, 11, 1), HOJE) == -7
    assert dias_restantes(None, HOJE) is None


# ---------------- validadores ----------------
def test_cpf():
    assert validar_cpf("529.982.247-25")
    assert validar_cpf("52998224725")
    assert not validar_cpf("529.982.247-26")
    assert not validar_cpf("111.111.111-11")
    assert not validar_cpf("123")


def test_cnpj_numerico_e_alfanumerico():
    assert validar_cnpj("11.222.333/0001-81")
    assert not validar_cnpj("11.222.333/0001-82")
    assert not validar_cnpj("00.000.000/0000-00")
    # Exemplo oficial do CNPJ alfanumérico publicado pela Receita Federal
    assert validar_cnpj("12.ABC.345/01DE-35")
    assert not validar_cnpj("12.ABC.345/01DE-36")
    assert formatar_cnpj("12abc34501de35") == "12.ABC.345/01DE-35"


def test_email():
    assert validar_email("tecnico@empresa.com.br")
    assert not validar_email("tecnico@empresa")
    assert not validar_email("")


def test_politica_senha():
    assert problemas_senha("curta1") != []
    assert problemas_senha("somenteletrasaqui") != []
    assert problemas_senha("SenhaForte2026") == []


# ---------------- segurança ----------------
def test_hash_senha():
    h = gerar_hash_senha("SenhaForte2026")
    assert h.startswith("scrypt$")
    assert verificar_senha("SenhaForte2026", h)
    assert not verificar_senha("senhaerrada99", h)
    assert not verificar_senha("SenhaForte2026", "lixo")
    assert gerar_hash_senha("SenhaForte2026") != h  # salt aleatório


def test_senha_temporaria_atende_politica():
    for _ in range(20):
        assert problemas_senha(gerar_senha_temporaria()) == []


# ---------------- permissões ----------------
def test_permissoes_por_perfil():
    consulta = UsuarioContexto(1, 1, "C", "c@x.com", Perfil.CONSULTA)
    tecnico = UsuarioContexto(2, 1, "T", "t@x.com", Perfil.TECNICO_SST, (5,))
    assert consulta.pode(Permissao.LER)
    with pytest.raises(PermissaoNegadaError):
        consulta.exigir(Permissao.EDITAR_VENCIMENTOS)
    assert not tecnico.pode(Permissao.VER_DADOS_SAUDE)
    assert tecnico.pode_ver_unidade(5)
    assert tecnico.pode_ver_unidade(None)  # itens da empresa
    assert not tecnico.pode_ver_unidade(6)
