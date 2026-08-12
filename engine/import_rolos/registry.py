"""
Registry de adaptadores de fonte de rolos.
Seleciona o adaptador correto com base no tipo informado ou no CONTEUDO do
arquivo (o ERP Vexta gera dois PDFs diferentes: Reserva de Tecidos e
Estoque Total de Rolos -- a deteccao automatica le a primeira pagina).
"""

from .fonte_vexta_pdf         import FonteVextaPdf
from .fonte_vexta_estoque_pdf import FonteVextaEstoquePdf
from .fonte_sisplan           import FonteSisplan

# Mapa tipo -> classe adaptadora
FONTES = {
    "vexta_pdf"         : FonteVextaPdf,
    "vexta_estoque_pdf" : FonteVextaEstoquePdf,
    "sisplan"           : FonteSisplan,
}


def detectar_tipo_pdf(caminho_arquivo):
    """
    Le a primeira pagina do PDF e decide qual dos dois formatos Vexta e:
      - 'RESERVA DE TECIDOS'            -> vexta_pdf (reserva por OP)
      - 'MATERIAL_CODIGO' + 'LARGURA'   -> vexta_estoque_pdf (estoque geral)
    Fallback: vexta_pdf (formato historico).
    """
    try:
        import pdfplumber
        with pdfplumber.open(caminho_arquivo) as pdf:
            if not pdf.pages:
                return "vexta_pdf"
            texto = (pdf.pages[0].extract_text() or "").upper()
    except Exception:
        return "vexta_pdf"

    if "MATERIAL_CODIGO" in texto or ("SALDO" in texto and "LARGURA" in texto):
        return "vexta_estoque_pdf"
    if "RESERVA DE TECIDOS" in texto:
        return "vexta_pdf"
    return "vexta_pdf"


def obter_fonte(tipo=None, caminho_arquivo=None):
    """
    Retorna uma instancia do adaptador adequado.

    Args:
        tipo (str | None): 'vexta_pdf', 'vexta_estoque_pdf', 'sisplan', etc.
            Se None, detecta pelo conteudo (PDF) ou usa o default.
        caminho_arquivo (str | None): usado para detectar o tipo quando tipo=None.

    Returns:
        FonteRolos: Instancia do adaptador.

    Raises:
        ValueError: Se o tipo nao for reconhecido.
    """
    if tipo is None and caminho_arquivo:
        import os
        ext = os.path.splitext(caminho_arquivo)[1].lower()
        if ext == ".pdf":
            tipo = detectar_tipo_pdf(caminho_arquivo)

    if tipo is None:
        tipo = "vexta_pdf"  # default

    cls = FONTES.get(tipo)
    if cls is None:
        disponiveis = ", ".join(FONTES.keys())
        raise ValueError(
            f"Fonte '{tipo}' nao reconhecida. Disponiveis: {disponiveis}"
        )
    return cls()
