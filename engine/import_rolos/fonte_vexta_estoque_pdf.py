"""
Adaptador para PDF de Estoque Total de Rolos ("ROLOS") do ERP Vexta.

Este e o SEGUNDO formato de PDF que o ERP gera (o primeiro e a Reserva de
Tecidos, ver fonte_vexta_pdf.py). Aqui aparece o estoque geral de rolos, com
LARGURA -- informacao que a Reserva nao tem.

Estrutura do PDF (descoberta a partir do documento de exemplo
"ESTOQUE TOTAL CREPE PATOU - 12-08-26.pdf"):

  3 CHARTH COMERCIO ... LTDA            ROLOS     <- cabecalho da pagina
  122448 CREPE PATOU - 27339A SILVER BIRCH        <- GRUPO: artigo - cor
  MATERIAL_CODIGO MATERIAL_NOME ID NUMERO Lote SALDO LARGURA   <- cabecalho tabela
  02.01.03.00021SILVER BIR 122448 CREPE PATOU - 27339A SILVER  <- linha de rolo
  BIRCH 2017 2017 884236 16,25 1,41                            <- (pode quebrar em 2)
  ...
  97 rolos                                        <- totalizador final
  Emitido em 12/08/2026 13:10:21 ...  Folha 1     <- rodape

Observacoes importantes:
  - O nome do material pode QUEBRAR de linha; os numeros (ID NUMERO Lote SALDO
    LARGURA) ficam sempre no FINAL de alguma linha. Por isso o parser detecta
    rolos pelo padrao de cauda numerica, independente do que vem antes.
  - Lote "0" = sem lote informado (vira None).
  - LARGURA "0" = sem largura informada (vira None).
  - A cor do fornecedor vem do cabecalho de GRUPO (texto apos o primeiro " - ").

Dependencia: pdfplumber (pip install pdfplumber)
"""

import re

from .base import FonteRolos

try:
    import pdfplumber
    _PDFPLUMBER_OK = True
except ImportError:
    _PDFPLUMBER_OK = False


# Cauda de linha de rolo: ID NUMERO LOTE SALDO LARGURA (5 campos no fim da linha).
# LOTE pode ter lixo de extracao (tabs) colado -- por isso \S+.
_RE_CAUDA_ROLO = re.compile(
    r"(\d+)\s+(\d+)\s+(\S+)\s+(\d[\d.,]*)\s+(\d[\d.,]*)\s*$"
)
# Cabecalho de grupo: codigo do artigo (5-6 digitos) + nome, SEM cauda de rolo.
_RE_GRUPO      = re.compile(r"^(\d{5,6})\s+(.+)$")
_RE_TOTAL      = re.compile(r"^(\d+)\s+rolos?\s*$", re.IGNORECASE)
_RE_CABECALHO  = re.compile(r"MATERIAL_CODIGO", re.IGNORECASE)


def _parse_num(texto):
    """Converte '49,40' ou '49.40' para float. Retorna None se invalido/zero."""
    t = str(texto).strip().replace(",", ".")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def _e_linha_ignorada(linha):
    """Linhas estruturais que nunca sao grupo nem rolo."""
    if not linha.strip():
        return True
    prefixos = ("Emitido", "Folha ", "MATERIAL_CODIGO")
    for p in prefixos:
        if linha.startswith(p):
            return True
    # Cabecalho da empresa (termina com ROLOS)
    if "ROLOS" in linha and ("LTDA" in linha or "COMERCIO" in linha):
        return True
    return False


class FonteVextaEstoquePdf(FonteRolos):
    """
    Extrai rolos do PDF de Estoque Total ("ROLOS") do ERP Vexta.
    Inclui largura_m (o formato Reserva nao tem essa informacao).
    """

    def extrair(self, caminho_arquivo):
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

        artigo_atual = None
        cor_atual    = None
        header_atual = None   # texto original do cabecalho de grupo vigente
        total_pdf    = None   # totalizador "97 rolos" do proprio PDF (validacao)

        for idx, linha_orig in enumerate(linhas):
            linha = linha_orig.strip()
            if not linha:
                continue

            # Totalizador final ("97 rolos")
            m_total = _RE_TOTAL.match(linha)
            if m_total:
                total_pdf = int(m_total.group(1))
                continue

            # Linha de ROLO: detectada pela cauda numerica (o inicio da linha
            # pode ser MATERIAL_CODIGO+nome, ou a continuacao de um nome quebrado).
            m_rolo = _RE_CAUDA_ROLO.search(linha)
            if m_rolo and not linha.startswith("Emitido"):
                metros  = _parse_num(m_rolo.group(4))
                largura = _parse_num(m_rolo.group(5))
                # Limpa lixo de extracao no lote (tabs viram "(cid:9)" no pdfplumber)
                lote    = re.sub(r"\(cid:\d+\)", "", m_rolo.group(3)).strip()
                if lote in ("0", ""):
                    lote = None
                if metros and cor_atual:
                    registros.append({
                        "cor_fornecedor": cor_atual,
                        "comprimento_m" : metros,
                        "rolo_id"       : m_rolo.group(2),
                        "lote"          : lote,
                        "largura_m"     : largura,
                        "artigo"        : artigo_atual,
                        "reservado"     : False,
                        "linha_original": linha_orig,
                    })
                elif metros and not cor_atual:
                    linhas_nao_parseadas.append(linha_orig)
                continue

            if _e_linha_ignorada(linha):
                continue

            # Cabecalho de GRUPO: "122448 CREPE PATOU - 27339A SILVER BIRCH"
            m_grupo = _RE_GRUPO.match(linha)
            if m_grupo:
                # Fragmento de celula quebrada: quando o nome do material quebra
                # de linha, o pdfplumber emite [PREFIXO do cabecalho vigente,
                # linha do rolo, palavra orfa que completa o nome]. Um prefixo
                # SO e tratado como fragmento se o lookahead confirmar esse
                # padrao -- um grupo REAL cujo nome e prefixo do anterior (ex:
                # "VERDE" depois de "VERDE MILITAR") nao pode ser engolido.
                if header_atual and header_atual.startswith(linha) \
                        and len(linha) < len(header_atual):
                    prox  = linhas[idx + 1].strip() if idx + 1 < len(linhas) else ""
                    prox2 = linhas[idx + 2].strip() if idx + 2 < len(linhas) else ""
                    e_fragmento = (_RE_CAUDA_ROLO.search(prox)
                                   and (linha + " " + prox2) == header_atual)
                    if e_fragmento:
                        continue
                header_atual = linha
                nome = m_grupo.group(2).strip()
                if " - " in nome:
                    artigo_nome, cor = nome.split(" - ", 1)
                    artigo_atual = (m_grupo.group(1) + " " + artigo_nome).strip()
                    cor_atual    = cor.strip()
                else:
                    artigo_atual = (m_grupo.group(1) + " " + nome).strip()
                    cor_atual    = nome
                continue

            # Continuacao de nome quebrado sem numeros, ou linha desconhecida.
            # So reporta como nao-parseada se parecer conteudo relevante.
            if any(ch.isdigit() for ch in linha):
                linhas_nao_parseadas.append(linha_orig)

        # Validacao contra o totalizador do proprio PDF.
        if total_pdf is not None and total_pdf != len(registros):
            linhas_nao_parseadas.append(
                f"AVISO: o PDF informa {total_pdf} rolos, mas o parser "
                f"reconheceu {len(registros)}. Confira as linhas nao parseadas."
            )

        return registros, linhas_nao_parseadas

    def nome_fonte(self):
        return "Vexta Estoque PDF"
