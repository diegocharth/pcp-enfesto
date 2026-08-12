"""
Testes do parser do PDF de Estoque Total ("ROLOS") do ERP Vexta.

A maior parte dos testes usa linhas sinteticas (extrair_de_linhas), replicando
exatamente o que o pdfplumber devolve para o PDF real -- inclusive as quebras
de linha no meio do nome do material. O teste com o PDF real roda apenas se o
arquivo de exemplo existir em Downloads.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from engine.import_rolos.fonte_vexta_estoque_pdf import FonteVextaEstoquePdf

PDF_ESTOQUE_WIN = r"C:\Users\CHARTH DIEGO\Downloads\ESTOQUE TOTAL CREPE PATOU - 12-08-26.pdf"


def _pdfplumber_disponivel():
    try:
        import pdfplumber  # noqa: F401
        return True
    except ImportError:
        return False


# Linhas sinteticas copiadas do comportamento real do pdfplumber no PDF de
# exemplo: grupo com nome quebrado (SILVER BIRCH), grupo em linha unica
# (CASHMERE), lote 0 (sem lote), largura 0 (sem largura) e lixo (cid:9).
LINHAS = [
    "3 CHARTH COMERCIO DE ARTIGOS DE VESTUARIO E ACESSORIOS LTDA ROLOS",
    "122448 CREPE PATOU - 27339A SILVER BIRCH",
    "MATERIAL_CODIGO MATERIAL_NOME ID NUMERO Lote SALDO LARGURA",
    "122448 CREPE PATOU - 27339A SILVER",
    "02.01.03.00021SILVER BIR 2017 2017 884236 16,25 1,41",
    "BIRCH",
    "122448 CREPE PATOU - 27339A SILVER",
    "02.01.03.00021SILVER BIR 1531 1531 0 55 0",
    "BIRCH",
    "122448 CREPE PATOU - 27355A CASHMERE",
    "02.01.03.00021CASHMERE 122448 CREPE PATOU - 27355A CASHMERE 2381 2381 884516 16,5 1,4",
    "122448 CREPE PATOU - MALVA",
    "02.01.03.00021-TELHA 122448 CREPE PATOU - MALVA 1400 1400 882561\t 8 1,41",
    "4 rolos",
    "Emitido em 12/08/2026 13:10:21 LUCAS RUAS REZENDE Folha 1",
]


def _extrair():
    return FonteVextaEstoquePdf().extrair_de_linhas(LINHAS)


def test_total_registros():
    registros, nao = _extrair()
    assert len(registros) == 4
    assert nao == []


def test_cor_completa_apesar_da_quebra_de_linha():
    """O fragmento '...27339A SILVER' (celula quebrada) nao pode sobrescrever
    o cabecalho verdadeiro '...27339A SILVER BIRCH'."""
    registros, _ = _extrair()
    cores = {r["cor_fornecedor"] for r in registros}
    assert "27339A SILVER BIRCH" in cores
    assert "27339A SILVER" not in cores


def test_metadados_rolo():
    registros, _ = _extrair()
    r = [x for x in registros if x["rolo_id"] == "2017"][0]
    assert r["lote"] == "884236"
    assert r["comprimento_m"] == 16.25
    assert r["largura_m"] == 1.41
    assert r["artigo"] == "122448 CREPE PATOU"
    assert r["reservado"] is False


def test_lote_zero_e_largura_zero_viram_none():
    registros, _ = _extrair()
    r = [x for x in registros if x["rolo_id"] == "1531"][0]
    assert r["lote"] is None
    assert r["largura_m"] is None
    assert r["comprimento_m"] == 55.0


def test_lote_com_lixo_cid_limpo():
    """Tabs no PDF viram '(cid:9)' no pdfplumber -- o lote nao pode carregar isso."""
    linhas = list(LINHAS)
    linhas[12] = "02.01.03.00021-TELHA 122448 CREPE PATOU - MALVA 1400 1400 882561(cid:9) 8 1,41"
    registros, _ = FonteVextaEstoquePdf().extrair_de_linhas(linhas)
    r = [x for x in registros if x["rolo_id"] == "1400"][0]
    assert r["lote"] == "882561"


def test_totalizador_divergente_gera_aviso():
    linhas = [l for l in LINHAS if l != "4 rolos"] + ["9 rolos"]
    registros, nao = FonteVextaEstoquePdf().extrair_de_linhas(linhas)
    assert len(registros) == 4
    assert any("AVISO" in l for l in nao)


@pytest.mark.skipif(not os.path.exists(PDF_ESTOQUE_WIN) or not _pdfplumber_disponivel(),
                    reason="PDF de exemplo ou pdfplumber nao disponivel")
def test_pdf_real_97_rolos():
    registros, nao = FonteVextaEstoquePdf().extrair(PDF_ESTOQUE_WIN)
    assert len(registros) == 97
    assert not [l for l in nao if "AVISO" in l]
    malva = [r for r in registros if r["cor_fornecedor"] == "MALVA"]
    assert len(malva) == 7
    black = [r for r in registros if r["cor_fornecedor"] == "BLACK"]
    assert len(black) == 21
    assert all(r["largura_m"] is None or r["largura_m"] > 1 for r in registros)


def test_deteccao_de_tipo():
    from engine.import_rolos.registry import obter_fonte, FONTES
    assert "vexta_estoque_pdf" in FONTES
    fonte = obter_fonte(tipo="vexta_estoque_pdf")
    assert fonte.nome_fonte() == "Vexta Estoque PDF"


@pytest.mark.skipif(not os.path.exists(PDF_ESTOQUE_WIN) or not _pdfplumber_disponivel(),
                    reason="PDF de exemplo ou pdfplumber nao disponivel")
def test_deteccao_automatica_pelo_conteudo():
    from engine.import_rolos.registry import detectar_tipo_pdf
    assert detectar_tipo_pdf(PDF_ESTOQUE_WIN) == "vexta_estoque_pdf"


def test_grupo_real_que_e_prefixo_do_anterior_nao_e_engolido():
    """'VERDE' depois de 'VERDE MILITAR' e um grupo REAL, nao fragmento."""
    linhas = [
        "122448 CREPE PATOU - VERDE MILITAR",
        "02.01.03.00021VM 122448 CREPE PATOU - VERDE MILITAR 1 1 100 10 1,4",
        "122448 CREPE PATOU - VERDE",
        "02.01.03.00021V 122448 CREPE PATOU - VERDE 2 2 200 20 1,4",
        "2 rolos",
    ]
    registros, _ = FonteVextaEstoquePdf().extrair_de_linhas(linhas)
    cores = {r["rolo_id"]: r["cor_fornecedor"] for r in registros}
    assert cores == {"1": "VERDE MILITAR", "2": "VERDE"}
