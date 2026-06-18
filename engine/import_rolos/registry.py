"""
Registry de adaptadores de fonte de rolos.
Seleciona o adaptador correto com base no tipo informado.
"""

from .fonte_vexta_pdf import FonteVextaPdf
from .fonte_sisplan    import FonteSisplan

# Mapa tipo -> classe adaptadora
FONTES = {
    "vexta_pdf": FonteVextaPdf,
    "sisplan"  : FonteSisplan,
}

_EXTENSOES_PADRAO = {
    ".pdf": "vexta_pdf",
}


def obter_fonte(tipo=None, caminho_arquivo=None):
    """
    Retorna uma instancia do adaptador adequado.

    Args:
        tipo (str | None): 'vexta_pdf', 'sisplan', etc. Se None, infere pela extensao.
        caminho_arquivo (str | None): Usado para inferir o tipo quando tipo=None.

    Returns:
        FonteRolos: Instancia do adaptador.

    Raises:
        ValueError: Se o tipo nao for reconhecido.
    """
    if tipo is None and caminho_arquivo:
        import os
        ext = os.path.splitext(caminho_arquivo)[1].lower()
        tipo = _EXTENSOES_PADRAO.get(ext)

    if tipo is None:
        tipo = "vexta_pdf"  # default

    cls = FONTES.get(tipo)
    if cls is None:
        disponiveis = ", ".join(FONTES.keys())
        raise ValueError(
            f"Fonte '{tipo}' nao reconhecida. Disponiveis: {disponiveis}"
        )
    return cls()
