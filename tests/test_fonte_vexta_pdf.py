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
