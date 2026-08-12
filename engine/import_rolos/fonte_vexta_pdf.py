"""
Adaptador para PDF de Reserva de Tecidos do ERP Vexta.

Estrutura do PDF (dois documentos reais de referencia: OP 6785 CALCA NAS e
OP 6925 VESTIDO LIDIANE):

  OP: 6925
  RESERVA DE TECIDOS
  VESTIDO LIDIANE                 <- nome da OP (repete no topo de cada pagina)

  1 - Reservados
    P11AC0012 CETIM COM ELASTANO NEW   <- ARTIGO (codigo alfanumerico OU sem codigo)
      409251 PINK LADY                 <- COR (pode ter codigo numerico!)
        Num Rolo  Lote  Qt Reservada  Requisicao
        4347      3014383979    54,00
        Requisicao: 83,74   87,00      <- totalizador fecha a tabela

      OFF WHITE                        <- outra cor do MESMO artigo
        Num Rolo ...

  2 - Nao Reservados                   <- cores com demanda mas sem rolos

REGRA DE PARSING (importante): artigo e cor NAO sao distinguiveis pelo texto
(ha artigos sem codigo, como "LINHO SUPREME", e cores com codigo numerico,
como "409251 PINK LADY"). O que distingue e a POSICAO: as linhas de texto
imediatamente antes do cabecalho "Num Rolo ..." sao:
  - 2 linhas -> [artigo, cor]  (comecou um artigo novo)
  - 1 linha  -> [cor]          (outra cor do mesmo artigo)
Por isso o parser acumula linhas "pendentes" e resolve ao ver o cabecalho.

Dependencia: pdfplumber (pip install pdfplumber)
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
_RE_SECAO_RES  = re.compile(r"^\d+\s*-\s*Reservados", re.IGNORECASE)
_RE_SECAO_NRES = re.compile(r"^\d+\s*-\s*N", re.IGNORECASE)  # "Nao Reservados" (c/ ou s/ acento garbled)
_RE_OP         = re.compile(r"^OP\s*:", re.IGNORECASE)


def _parse_metros(texto):
    """Converte '49,40' ou '49.40' para float. Retorna None se invalido."""
    t = str(texto).strip().replace(",", ".")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def _e_linha_ignorada(linha):
    """Linhas estruturais do documento (cabecalho/rodape) que nunca sao artigo/cor."""
    prefixos = ("Emitido", "Folha ", "RESERVA DE", "Qt Reservada", "Lote",
                "Num Rolo", "Requisi")
    for p in prefixos:
        if linha.startswith(p):
            return True
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
            - registros: list[dict] com cor_fornecedor, comprimento_m, rolo_id,
              lote, largura_m (sempre None neste formato), etc.
            - linhas_nao_parseadas: list[str] linhas nao reconhecidas (aviso na UI).
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

        return self.extrair_de_linhas(todas_linhas)

    def extrair_de_linhas(self, linhas):
        """
        Nucleo do parser, testavel sem PDF: recebe as linhas de texto extraidas.

        Returns:
            (registros, linhas_nao_parseadas) -- mesmo contrato de extrair().
        """
        registros            = []
        linhas_nao_parseadas = []

        secao_reservados = True   # False = secao "Nao Reservados"
        artigo_atual     = None   # ex: "P11AC0019 GLOSS SPAN"
        cor_atual        = None   # ex: "409251 PINK LADY"
        em_tabela        = False  # True apos cabecalho "Num Rolo ..."
        pendentes        = []     # linhas de texto aguardando o proximo cabecalho
        nome_op          = None   # titulo da OP (repete no topo de cada pagina)
        topo_pagina      = 0      # >0: proximas linhas sao o cabecalho da pagina

        def _descartar_pendentes():
            # Pendentes descartadas por um marcador estrutural sao linhas que o
            # parser NAO entendeu (ex: rolo com lote nao-numerico dentro da
            # tabela). Precisam aparecer como aviso, nunca sumir em silencio.
            if pendentes:
                linhas_nao_parseadas.extend(pendentes)
                del pendentes[:]

        for linha_orig in linhas:
            linha = linha_orig.strip()
            if not linha:
                continue

            # --- Cabecalho de pagina: "OP: 6925" e depois o nome da OP ---
            if _RE_OP.match(linha):
                topo_pagina = 2   # as 1-2 linhas seguintes sao o titulo da pagina
                continue
            if linha.startswith(("Emitido", "Folha ", "RESERVA DE")):
                continue
            if topo_pagina > 0:
                # Logo apos "OP:": captura (1a pagina) ou pula (paginas seguintes)
                # o titulo da OP. So AQUI o titulo e filtrado -- uma cor com o
                # mesmo nome do titulo no meio do documento nao pode ser engolida.
                eh_estrutural = (_RE_SECAO_RES.match(linha)
                                 or (_RE_SECAO_NRES.match(linha) and "-" in linha)
                                 or _RE_CABECALHO.search(linha)
                                 or _RE_REQUISICAO.match(linha))
                if eh_estrutural:
                    topo_pagina = 0   # pagina sem titulo: nada a capturar
                elif nome_op is None:
                    nome_op = linha
                    topo_pagina = 0
                    continue
                elif linha == nome_op:
                    topo_pagina = 0
                    continue
                else:
                    topo_pagina -= 1
                # linha nao-titulo: processa normalmente (cai abaixo)

            # --- Secao reservados ---
            if _RE_SECAO_RES.match(linha):
                secao_reservados = True
                em_tabela        = False
                _descartar_pendentes()
                artigo_atual     = None
                cor_atual        = None
                continue

            # --- Secao nao reservados ---
            if _RE_SECAO_NRES.match(linha) and "-" in linha:
                secao_reservados = False
                em_tabela        = False
                _descartar_pendentes()
                continue

            # --- Requisicao totalizador: fecha a tabela da cor atual ---
            if _RE_REQUISICAO.match(linha):
                em_tabela = False
                _descartar_pendentes()
                continue

            # --- Cabecalho da tabela: resolve artigo/cor das linhas pendentes ---
            if _RE_CABECALHO.search(linha):
                if len(pendentes) == 1:
                    cor_atual = pendentes[0]          # outra cor do mesmo artigo
                elif len(pendentes) >= 2:
                    artigo_atual = pendentes[-2]      # artigo novo + primeira cor
                    cor_atual    = pendentes[-1]
                    linhas_nao_parseadas.extend(pendentes[:-2])
                # 0 pendentes: mantem artigo/cor atuais (nao deve ocorrer)
                pendentes = []
                em_tabela = True
                continue

            # --- Linha de rolo (tres campos numericos) ---
            m_rolo = _RE_ROLO.match(linha)
            if m_rolo and em_tabela:
                if secao_reservados and cor_atual:
                    metros = _parse_metros(m_rolo.group(3))
                    if metros:
                        lote = m_rolo.group(2).strip()
                        registros.append({
                            "cor_fornecedor": cor_atual,
                            "comprimento_m" : metros,
                            "rolo_id"       : m_rolo.group(1),
                            "lote"          : None if lote in ("0", "") else lote,
                            "largura_m"     : None,  # a Reserva nao informa largura
                            "artigo"        : artigo_atual,
                            "reservado"     : True,
                            "linha_original": linha_orig,
                        })
                continue

            # --- Fragmentos de cabecalho de tabela soltos ---
            if linha.startswith(("Qt Reservada", "Lote")):
                continue

            # --- Qualquer outra linha: candidata a artigo/cor (resolve no cabecalho) ---
            pendentes.append(linha)

        # Sobras de pendentes no fim do documento (nao houve cabecalho depois)
        linhas_nao_parseadas.extend(pendentes)

        return registros, linhas_nao_parseadas

    def nome_fonte(self):
        return "Vexta PDF"
