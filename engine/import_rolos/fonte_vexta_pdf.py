"""
Adaptador para PDF de Reserva de Tecidos do ERP Vexta.

Estrutura do PDF (descoberta a partir do documento de exemplo):

  OP: 6785
  CALÇA NAS

  1 - Reservados
    122448 CREPE PATOU            <- ARTIGO: 5-6 digitos numericos + nome
      27339A SILVER BIRCH         <- COR: codigo alfanumerico + nome (codigo opcional)
        Num Rolo  Lote  Qt Reservada  Requisicao
        4149      885594    9,00
        4158      885594   49,00
        Requisicao: 187,25   188,40  <- totalizador; proxima linha = outra cor do mesmo artigo

      27355A CASHMERE             <- outra cor do mesmo artigo
        ...

  2 - Nao Reservados             <- cores com demanda mas sem rolos alocados
    (mesmo formato, mas tabela de rolos fica vazia)

Dependencia: pdfplumber (pip install pdfplumber)

Estado de parsing (maquina de estados simplificada):
  INICIO
    - Linha secao (1-Reservados / 2-NaoReservados): define secao_atual, espera artigo
    - Linha artigo (codigo 5-6 digitos): define artigo_atual, espera cor
  ARTIGO_VISTO (espera cor)
    - Qualquer linha nao-especial: define cor_atual, espera cabecalho
  COR_VISTA (espera cabecalho ou nova cor/artigo)
    - CABECALHO: entra em EM_TABELA
  EM_TABELA (processa rolos)
    - ROLO: registra rolo (se secao = reservados)
    - REQUISICAO: sai da tabela, volta a esperar nova cor (mesmo artigo)
"""

import re

from .base import FonteRolos

try:
    import pdfplumber
    _PDFPLUMBER_OK = True
except ImportError:
    _PDFPLUMBER_OK = False


_RE_ROLO       = re.compile(r"^(\d+)\s+(\d+)\s+([\d.,]+)\s*$")
_RE_CABECALHO  = re.compile(r"Num\s+Rolo", re.IGNORECASE)
_RE_REQUISICAO = re.compile(r"^Requisi", re.IGNORECASE)
_RE_ARTIGO     = re.compile(r"^(\d{5,6})\s+(.+)$")   # codigo puramente numerico 5-6 digitos
_RE_SECAO_RES  = re.compile(r"^\d+\s*-\s*Reservados", re.IGNORECASE)
_RE_SECAO_NRES = re.compile(r"^\d+\s*-\s*N", re.IGNORECASE)  # "Nao Reservados" (c/ ou s/ acento garbled)


def _parse_metros(texto):
    """Converte '49,40' ou '49.40' para float. Retorna None se invalido."""
    t = str(texto).strip().replace(",", ".")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def _e_linha_ignorada(linha):
    """Retorna True para linhas que nunca sao artigo/cor (cabecalho do doc, rodape, etc.)."""
    prefixos = ("OP:", "Emitido", "Folha ", "RESERVA DE", "Qt Reservada", "Lote",
                "Num Rolo", "Requisi")
    for p in prefixos:
        if linha.startswith(p):
            return True
    # Linha vazia ou so numeros (pode ser lote solto)
    if not linha.strip():
        return True
    return False


class FonteVextaPdf(FonteRolos):
    """
    Extrai rolos de tecido do PDF de Reserva de Tecidos do ERP Vexta.
    """

    def extrair(self, caminho_arquivo):
        """
        Returns:
            (registros, linhas_nao_parseadas)
            - registros: list[dict] com cor_fornecedor, comprimento_m, rolo_id, lote, etc.
            - linhas_nao_parseadas: list[str] linhas nao reconhecidas (para aviso na UI)
        """
        if not _PDFPLUMBER_OK:
            raise ImportError(
                "pdfplumber nao esta instalado. Execute: pip install pdfplumber"
            )

        import os
        if not os.path.exists(caminho_arquivo):
            raise FileNotFoundError(f"Arquivo nao encontrado: {caminho_arquivo}")

        try:
            with pdfplumber.open(caminho_arquivo) as pdf:
                todas_linhas = []
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if texto:
                        todas_linhas.extend(texto.splitlines())
        except Exception as e:
            raise ValueError(f"Erro ao ler PDF: {e}")

        registros            = []
        linhas_nao_parseadas = []

        secao_reservados = True   # False = estamos na secao "Nao Reservados"
        artigo_atual     = None   # ex: "122448 CREPE PATOU"
        cor_atual        = None   # ex: "27339A SILVER BIRCH"
        em_tabela        = False  # True apos cabecalho "Num Rolo ..."
        espera_cor       = False  # True quando proximo passo esperado e uma cor

        for linha_orig in todas_linhas:
            linha = linha_orig.strip()
            if not linha:
                continue

            # --- Secao reservados ---
            if _RE_SECAO_RES.match(linha):
                secao_reservados = True
                em_tabela        = False
                espera_cor       = False
                artigo_atual     = None
                cor_atual        = None
                continue

            # --- Secao nao reservados ---
            # Detecta pelo padrao "2 - N..." (o "N" inicia "Nao" com ou sem acento garbled)
            if _RE_SECAO_NRES.match(linha) and "-" in linha:
                secao_reservados = False
                em_tabela        = False
                espera_cor       = False
                continue

            # --- Requisicao totalizador ---
            if _RE_REQUISICAO.match(linha):
                em_tabela  = False
                espera_cor = True   # proxima linha e outra cor do mesmo artigo
                continue

            # --- Cabecalho da tabela ---
            if _RE_CABECALHO.search(linha):
                em_tabela  = True
                espera_cor = False
                continue

            # --- Linha de rolo (tres campos numericos) ---
            m_rolo = _RE_ROLO.match(linha)
            if m_rolo and em_tabela:
                if secao_reservados and cor_atual:
                    metros = _parse_metros(m_rolo.group(3))
                    if metros:
                        registros.append({
                            "cor_fornecedor": cor_atual,
                            "comprimento_m" : metros,
                            "rolo_id"       : m_rolo.group(1),
                            "lote"          : m_rolo.group(2),
                            "artigo"        : artigo_atual,
                            "reservado"     : True,
                            "linha_original": linha_orig,
                        })
                continue

            # --- Linha de artigo (codigo 5-6 digitos puros + nome) ---
            m_artigo = _RE_ARTIGO.match(linha)
            if m_artigo:
                artigo_atual = (m_artigo.group(1) + " " + m_artigo.group(2)).strip()
                cor_atual    = None
                em_tabela    = False
                espera_cor   = True   # proxima linha e uma cor
                continue

            # --- Linha de cor ---
            # Qualquer linha que chegue aqui e nao seja especial e uma cor,
            # DESDE QUE estejamos esperando cor (logo apos artigo ou Requisicao).
            if espera_cor and artigo_atual and not _e_linha_ignorada(linha):
                cor_atual    = linha
                em_tabela    = False
                espera_cor   = False
                continue

            # --- Linha nao reconhecida ---
            if not _e_linha_ignorada(linha) and linha not in ("RESERVA DE TECIDOS",):
                linhas_nao_parseadas.append(linha_orig)

        return registros, linhas_nao_parseadas

    def nome_fonte(self):
        return "Vexta PDF"
