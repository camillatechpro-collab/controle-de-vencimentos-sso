import io
from datetime import date

import pandas as pd
import pytest
from openpyxl import load_workbook

from sst.domain.exceptions import ValidacaoError
from sst.infra import armazenamento
from sst.infra.excel.exportador import dataframe_para_xlsx, sanitizar_celula


def test_sanitiza_injecao_de_formula():
    assert sanitizar_celula("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert sanitizar_celula("+5") == "'+5"
    assert sanitizar_celula("@SUM(A1)") == "'@SUM(A1)"
    assert sanitizar_celula("Texto normal") == "Texto normal"
    assert sanitizar_celula(True) == "Sim"
    assert sanitizar_celula(float("nan")) is None


def test_exporta_xlsx_formatado():
    df = pd.DataFrame(
        {
            "nome": ["Ana", "=cmd|' /C calc'!A0"],
            "data_vencimento": [date(2026, 12, 1), None],
            "dias": pd.array([23, None], dtype="Int64"),
        }
    )
    conteudo = dataframe_para_xlsx(df, "Vencimentos", {"nome": "Nome", "data_vencimento": "Vencimento"})
    wb = load_workbook(io.BytesIO(conteudo))
    ws = wb.active
    assert ws.title == "Vencimentos"
    assert [c.value for c in ws[1]] == ["Nome", "Vencimento", "dias"]
    assert ws["A3"].value.startswith("'=")
    assert ws["B2"].number_format == "DD/MM/YYYY"
    assert ws["C3"].value is None
    assert ws.auto_filter.ref == "A1:C3"


@pytest.fixture
def pasta_anexos(tmp_path, monkeypatch):
    from sst import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("SST_ANEXOS_DIR", str(tmp_path))
    yield tmp_path
    config.get_settings.cache_clear()


def test_armazenamento_valida_assinatura(pasta_anexos):
    pdf = b"%PDF-1.7\n conteudo"
    salvo = armazenamento.salvar(7, "certificado.pdf", pdf)
    assert salvo.caminho_relativo.startswith("7/") and salvo.caminho_relativo.endswith(".pdf")
    assert armazenamento.ler(salvo.caminho_relativo, salvo.sha256) == pdf
    with pytest.raises(ValidacaoError):
        armazenamento.salvar(7, "virus.pdf", b"MZ\x90\x00 executavel")  # extensão mente
    with pytest.raises(ValidacaoError):
        armazenamento.salvar(7, "script.exe", pdf)
    with pytest.raises(ValidacaoError):
        armazenamento.ler("../../etc/passwd")
    assert armazenamento.nome_seguro("../../pasta\\malicioso<>.pdf") == "malicioso.pdf"


def test_armazenamento_detecta_adulteracao(pasta_anexos):
    salvo = armazenamento.salvar(1, "a.png", b"\x89PNG\r\n\x1a\nxxxx")
    (pasta_anexos / salvo.caminho_relativo).write_bytes(b"\x89PNG\r\n\x1a\nALTERADO")
    with pytest.raises(ValidacaoError):
        armazenamento.ler(salvo.caminho_relativo, salvo.sha256)
