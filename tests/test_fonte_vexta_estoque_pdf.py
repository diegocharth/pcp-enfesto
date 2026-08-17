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


# ---------------------------------------------------------------------------
# Variantes do formato descobertas em 17/08/2026 (ESTOQUE SPINATO RIGATO LUREX)
# ---------------------------------------------------------------------------

LINHAS_SPINATO = [
    "3 CHARTH COMERCIO DE ARTIGOS DE VESTUARIO E ACESSORIOS LTDA ROLOS",
    "SPINATO RIGATO LUREX - AZUL NEVOA",                                   # header SEM codigo
    "MATERIAL_CODIGO MATERIAL_NOME ID NUMERO Lote SALDO LARGURA",
    "02.01.03.00302AZUL NEVOA SPINATO RIGATO LUREX - AZUL NEVOA 5252 5252 1 72,38 1,5",
    "02.01.03.00302AZUL NEVOA SPINATO RIGATO LUREX - AZUL NEVOA 5239 5239 1 0 1,5",   # saldo 0
    "SPINATO RIGATO LUREX - ROSA SECO",
    "02.01.03.00302-ROSA SECO SPINATO RIGATO LUREX - ROSA SECO 5271 5271 1 41,33 1,5",
    "3 rolos",
    "Emitido em 17/08/2026 16:59:10 LUCAS RUAS REZENDE Folha 1",
]


def test_header_sem_codigo_de_artigo():
    """Formato SPINATO: cabecalho de grupo sem o codigo numerico do artigo."""
    registros, nao = FonteVextaEstoquePdf().extrair_de_linhas(LINHAS_SPINATO)
    assert len(registros) == 2
    assert nao == []
    cores = {r["rolo_id"]: r["cor_fornecedor"] for r in registros}
    assert cores == {"5252": "AZUL NEVOA", "5271": "ROSA SECO"}
    assert registros[0]["artigo"] == "SPINATO RIGATO LUREX"
    assert registros[0]["largura_m"] == 1.5


def test_saldo_zero_conta_no_totalizador_sem_aviso():
    """Rolos com saldo 0 nao viram registro, mas contam no 'N rolos' do PDF."""
    registros, nao = FonteVextaEstoquePdf().extrair_de_linhas(LINHAS_SPINATO)
    assert len(registros) == 2          # 3 rolos no PDF = 2 com saldo + 1 zerado
    assert not any("AVISO" in str(l) for l in nao)


def test_sem_header_nenhum_cor_vem_da_propria_linha():
    """Formato filtrado por cor: vai direto do cabecalho da tabela para as linhas."""
    linhas = [
        "3 CHARTH COMERCIO DE ARTIGOS DE VESTUARIO E ACESSORIOS LTDA ROLOS",
        "MATERIAL_CODIGO MATERIAL_NOME ID NUMERO Lote SALDO LARGURA",
        "02.01.03.00302AZUL NEVOA SPINATO RIGATO LUREX - AZUL NEVOA 5235 5235 1 73,22 1,5",
        "02.01.03.00302AZUL NEVOA SPINATO RIGATO LUREX - AZUL NEVOA 1769 1769 0 18 0",
        "2 rolos",
    ]
    registros, nao = FonteVextaEstoquePdf().extrair_de_linhas(linhas)
    assert len(registros) == 2
    assert nao == []
    assert all(r["cor_fornecedor"] == "AZUL NEVOA" for r in registros)
    r1769 = [r for r in registros if r["rolo_id"] == "1769"][0]
    assert r1769["lote"] is None and r1769["largura_m"] is None
    assert r1769["comprimento_m"] == 18.0


def test_cor_da_linha_truncada_usa_cabecalho():
    """Se o nome na linha quebrou (prefixo da cor do cabecalho), vale o cabecalho."""
    linhas = [
        "122448 CREPE PATOU - 27040A AMARELO CREME",
        "02.01.03.00021AMARELO CR 122448 CREPE PATOU - 27040A AMARELO 4685 4685 886700 64,94 1,4",
        "CREME",
        "1 rolos",
    ]
    registros, _ = FonteVextaEstoquePdf().extrair_de_linhas(linhas)
    assert len(registros) == 1
    assert registros[0]["cor_fornecedor"] == "27040A AMARELO CREME"


PDF_SPINATO_1 = r"C:\Users\CHARTH DIEGO\Downloads\ESTOQUE SPINATO RIGATO LUREX.pdf"
PDF_SPINATO_2 = r"C:\Users\CHARTH DIEGO\Downloads\ESTOQUE SPINATO RIGATO LUREX - AZUL NEVOA (1).pdf"


@pytest.mark.skipif(not os.path.exists(PDF_SPINATO_1) or not _pdfplumber_disponivel(),
                    reason="PDF de exemplo ou pdfplumber nao disponivel")
def test_pdf_real_spinato_geral():
    registros, nao = FonteVextaEstoquePdf().extrair(PDF_SPINATO_1)
    assert not any("AVISO" in str(l) for l in nao)
    cores = {}
    for r in registros:
        cores.setdefault(r["cor_fornecedor"], []).append(r)
    assert len(cores["AZUL NEVOA"]) == 17
    assert len(cores["ROSA SECO"]) == 16


@pytest.mark.skipif(not os.path.exists(PDF_SPINATO_2) or not _pdfplumber_disponivel(),
                    reason="PDF de exemplo ou pdfplumber nao disponivel")
def test_pdf_real_spinato_uma_cor_sem_header():
    registros, nao = FonteVextaEstoquePdf().extrair(PDF_SPINATO_2)
    assert not any("AVISO" in str(l) for l in nao)
    assert len(registros) == 24
    assert all(r["cor_fornecedor"] == "AZUL NEVOA" for r in registros)
