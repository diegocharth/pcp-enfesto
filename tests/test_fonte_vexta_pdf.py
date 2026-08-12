"""
Testes do parser Vexta PDF.

O PDF de exemplo tem 5 cores reservadas (com rolos) e 2 nao reservadas:
  Reservados:
    27339A SILVER BIRCH  -> rolos: 9, 49, 49, 49.40, 32          (5 rolos)
    27355A CASHMERE      -> rolos: 23, 18, 25, 14                 (4 rolos)
    27526A BIJOU BLUE    -> rolos: 49.60, 43, 59, 48.70, 10       (5 rolos)
    71 MANTEIGA          -> rolos: 26, 50, 54.60, 54.80           (4 rolos)
    BLACK                -> rolos: 22, 53, 56, 51                 (4 rolos)
  Nao reservados:
    27040A AMARELO CREME -> sem rolos
    27358B PALE LILAC    -> sem rolos

Total de registros esperados: 5+4+5+4+4 = 22 rolos.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

PDF_EXEMPLO = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "Downloads",
    "RESERVA ROLOS - CALCA NAS - OP 6785.pdf"
)
# Caminho alternativo (Windows)
PDF_EXEMPLO_WIN = "C:\\Users\\CHARTH DIEGO\\Downloads\\RESERVA ROLOS - CALÇA NAS - OP 6785.pdf"


def _get_pdf_path():
    if os.path.exists(PDF_EXEMPLO_WIN):
        return PDF_EXEMPLO_WIN
    if os.path.exists(PDF_EXEMPLO):
        return PDF_EXEMPLO
    return None


def _pdfplumber_disponivel():
    try:
        import pdfplumber
        return True
    except ImportError:
        return False


SKIP_PDF = pytest.mark.skipif(
    not _get_pdf_path() or not _pdfplumber_disponivel(),
    reason="PDF de exemplo ou pdfplumber nao disponivel"
)


@SKIP_PDF
def test_total_rolos_extraidos():
    """O PDF de exemplo deve retornar exatamente 22 registros de rolos reservados."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, nao_parseadas = fonte.extrair(_get_pdf_path())
    assert len(registros) == 22, f"Esperava 22 registros, got {len(registros)}"


@SKIP_PDF
def test_todos_reservados():
    """Todos os registros extraidos devem ser 'reservado=True'."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, _ = fonte.extrair(_get_pdf_path())
    for reg in registros:
        assert reg["reservado"] is True


@SKIP_PDF
def test_comprimentos_positivos():
    """Todos os comprimentos devem ser > 0."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, _ = fonte.extrair(_get_pdf_path())
    for reg in registros:
        assert reg["comprimento_m"] > 0, f"Comprimento invalido: {reg}"


@SKIP_PDF
def test_cor_black_encontrada():
    """Cor 'BLACK' (sem codigo) deve ser extraida corretamente."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, _ = fonte.extrair(_get_pdf_path())
    cors = [r["cor_fornecedor"].upper() for r in registros]
    assert any("BLACK" in c for c in cors), f"BLACK nao encontrada. Cores: {set(cors)}"


@SKIP_PDF
def test_comprimentos_black():
    """Rolos da cor BLACK devem ser 22, 53, 56, 51."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, _ = fonte.extrair(_get_pdf_path())
    black = [r["comprimento_m"] for r in registros if "BLACK" in r["cor_fornecedor"].upper()]
    assert sorted(black) == sorted([22.0, 53.0, 56.0, 51.0]), f"Comprimentos BLACK: {sorted(black)}"


@SKIP_PDF
def test_comprimentos_silver_birch():
    """Rolos de SILVER BIRCH devem ser 9, 49, 49, 49.40, 32."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, _ = fonte.extrair(_get_pdf_path())
    birch = [r["comprimento_m"] for r in registros if "SILVER BIRCH" in r["cor_fornecedor"].upper()]
    assert sorted(birch) == sorted([9.0, 49.0, 49.0, 49.40, 32.0]), f"Got: {sorted(birch)}"


@SKIP_PDF
def test_sem_rolos_nao_reservados():
    """Cores nao reservadas (AMARELO CREME, PALE LILAC) nao devem gerar registros."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    fonte = FonteVextaPdf()
    registros, _ = fonte.extrair(_get_pdf_path())
    cors = [r["cor_fornecedor"].upper() for r in registros]
    assert not any("AMARELO CREME" in c for c in cors)
    assert not any("PALE LILAC" in c for c in cors)


# ---------------------------------------------------------------------------
# Testes sem PDF (logica do parser)
# ---------------------------------------------------------------------------

def test_parse_metros():
    from engine.import_rolos.fonte_vexta_pdf import _parse_metros
    assert _parse_metros("49,40") == 49.40
    assert _parse_metros("9,00") == 9.0
    assert _parse_metros("142.5") == 142.5
    assert _parse_metros("0") is None
    assert _parse_metros("abc") is None


def test_arquivo_inexistente():
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    if not _pdfplumber_disponivel():
        pytest.skip("pdfplumber nao disponivel")
    fonte = FonteVextaPdf()
    with pytest.raises(FileNotFoundError):
        fonte.extrair("/caminho/que/nao/existe.pdf")


# ---------------------------------------------------------------------------
# Testes sinteticos do formato novo (OP 6925): artigo alfanumerico ou sem
# codigo, cor com codigo numerico, titulo da OP repetido por pagina.
# ---------------------------------------------------------------------------

LINHAS_OP_6925 = [
    "OP: 6925",
    "RESERVA DE TECIDOS",
    "VESTIDO LIDIANE",
    "1 - Reservados",
    "P11AC0012 CETIM COM ELASTANO NEW",
    "409251 PINK LADY",
    "Num Rolo Lote Qt Reservada Requisicao",
    "4347 3014383979 54,00",
    "4348 3014383983 33,00",
    "Requisicao: 83,74 87,00",
    "OFF WHITE",
    "Num Rolo Lote Qt Reservada Requisicao",
    "3082 2 71,00",
    "Requisicao: 67,94 71,00",
    "LINHO SUPREME",
    "FRAPE",
    "Num Rolo Lote Qt Reservada Requisicao",
    "4370 3554557 63,00",
    "Emitido em 11/08/2026 14:35:07 LUCAS RUAS REZENDE Folha 1",
    "OP: 6925",
    "RESERVA DE TECIDOS",
    "VESTIDO LIDIANE",
    "Requisicao: 162,18 162,00",
    "2 - Nao Reservados",
    "P11AC0019 GLOSS SPAN",
    "00070 BLUE SPACE",
    "Num Rolo Lote Qt Reservada Requisicao",
    "Requisicao: 117,71",
    "Emitido em 11/08/2026 14:35:07 LUCAS RUAS REZENDE Folha 2",
]


def _extrair_sintetico():
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    return FonteVextaPdf().extrair_de_linhas(LINHAS_OP_6925)


def test_sintetico_total_e_sem_nao_parseadas():
    registros, nao = _extrair_sintetico()
    assert len(registros) == 4
    assert nao == []


def test_sintetico_cor_com_codigo_numerico_nao_vira_artigo():
    """'409251 PINK LADY' e uma COR (apesar do codigo de 6 digitos)."""
    registros, _ = _extrair_sintetico()
    pink = [r for r in registros if r["cor_fornecedor"] == "409251 PINK LADY"]
    assert len(pink) == 2
    assert pink[0]["artigo"] == "P11AC0012 CETIM COM ELASTANO NEW"
    assert pink[0]["rolo_id"] == "4347"
    assert pink[0]["lote"] == "3014383979"
    assert pink[0]["largura_m"] is None


def test_sintetico_segunda_cor_do_mesmo_artigo():
    registros, _ = _extrair_sintetico()
    off = [r for r in registros if r["cor_fornecedor"] == "OFF WHITE"]
    assert len(off) == 1
    assert off[0]["artigo"] == "P11AC0012 CETIM COM ELASTANO NEW"


def test_sintetico_artigo_sem_codigo():
    registros, _ = _extrair_sintetico()
    frape = [r for r in registros if r["cor_fornecedor"] == "FRAPE"]
    assert len(frape) == 1
    assert frape[0]["artigo"] == "LINHO SUPREME"


def test_sintetico_nao_reservados_sem_registros():
    registros, _ = _extrair_sintetico()
    assert not any("BLUE SPACE" in r["cor_fornecedor"] for r in registros)


def test_sintetico_tabela_atravessa_pagina():
    """Rolos antes da quebra de pagina sao registrados; o titulo da OP repetido
    no topo da pagina 2 nao vira cor."""
    registros, _ = _extrair_sintetico()
    cores = {r["cor_fornecedor"] for r in registros}
    assert "VESTIDO LIDIANE" not in cores


def test_linha_malformada_dentro_da_tabela_vira_aviso():
    """Rolo com lote nao-numerico nao pode sumir em silencio: vira aviso."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    linhas = [
        "OP: 1", "RESERVA DE TECIDOS", "PECA X", "1 - Reservados",
        "ARTIGO Y", "COR Z",
        "Num Rolo Lote Qt Reservada Requisicao",
        "1732 883555 22,00",
        "1740 88355A 53,00",
        "Requisicao: 75,00 75,00",
    ]
    registros, nao = FonteVextaPdf().extrair_de_linhas(linhas)
    assert len(registros) == 1
    assert any("88355A" in l for l in nao)


def test_cor_igual_ao_titulo_da_op_nao_e_engolida():
    """Uma cor com o mesmo nome do titulo da OP so e filtrada no topo da pagina."""
    from engine.import_rolos.fonte_vexta_pdf import FonteVextaPdf
    linhas = [
        "OP: 2", "RESERVA DE TECIDOS", "NATURAL",   # titulo da OP = NATURAL
        "1 - Reservados",
        "LINHO SUPREME", "FRAPE",
        "Num Rolo Lote Qt Reservada Requisicao",
        "1 10 10,00",
        "Requisicao: 10,00 10,00",
        "NATURAL",                                    # cor NATURAL (nao e titulo!)
        "Num Rolo Lote Qt Reservada Requisicao",
        "2 20 20,00",
        "Requisicao: 20,00 20,00",
    ]
    registros, _ = FonteVextaPdf().extrair_de_linhas(linhas)
    cores = {r["cor_fornecedor"]: r["rolo_id"] for r in registros}
    assert cores == {"FRAPE": "1", "NATURAL": "2"}
