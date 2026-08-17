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
# Cabecalho de grupo COM codigo de artigo: "122448 CREPE PATOU - COR".
# Ha relatorios SEM o codigo ("SPINATO RIGATO LUREX - AZUL NEVOA") -- esses
# sao reconhecidos por conterem " - " (tratados no corpo do parser).
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

        artigo_atual  = None
        cor_atual     = None
        header_atual  = None   # texto original do cabecalho de grupo vigente
        total_pdf     = None   # totalizador "97 rolos" do proprio PDF (validacao)
        rolos_zerados = 0      # rolos com saldo 0 (contam no totalizador)

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

                # Cor embutida NA PROPRIA linha: o MATERIAL_NOME "ARTIGO - COR"
                # vem antes dos numeros. E o caminho mais confiavel -- funciona
                # inclusive em relatorios SEM cabecalho de grupo. So falta
                # quando o nome quebrou de linha (dai vale o cabecalho vigente).
                prefixo = linha[:m_rolo.start()].strip()
                cor_row = None
                if " - " in prefixo:
                    cor_row = prefixo.split(" - ", 1)[1].strip() or None
                # Guarda contra truncamento: cor da linha que e prefixo estrito
                # da cor do cabecalho = nome quebrado -> usa a do cabecalho.
                if (cor_row and cor_atual and cor_atual.startswith(cor_row)
                        and len(cor_row) < len(cor_atual)):
                    cor_row = None
                cor    = cor_row or cor_atual
                artigo = artigo_atual if (cor_row is None or cor_row == cor_atual) \
                         else None

                if metros is None:
                    # Saldo 0 = rolo vazio no ERP: nao importa tecido nenhum,
                    # mas CONTA no totalizador "N rolos" do proprio PDF.
                    rolos_zerados += 1
                    continue
                if cor:
                    registros.append({
                        "cor_fornecedor": cor,
                        "comprimento_m" : metros,
                        "rolo_id"       : m_rolo.group(2),
                        "lote"          : lote,
                        "largura_m"     : largura,
                        "artigo"        : artigo,
                        "reservado"     : False,
                        "linha_original": linha_orig,
                    })
                else:
                    linhas_nao_parseadas.append(linha_orig)
                continue

            if _e_linha_ignorada(linha):
                continue

            # Cabecalho de GRUPO. Duas formas reais:
            #   "122448 CREPE PATOU - 27339A SILVER BIRCH"  (com codigo de artigo)
            #   "SPINATO RIGATO LUREX - AZUL NEVOA"         (sem codigo)
            m_grupo = _RE_GRUPO.match(linha)
            if m_grupo or " - " in linha:
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
                if m_grupo:
                    codigo = m_grupo.group(1) + " "
                    nome   = m_grupo.group(2).strip()
                else:
                    codigo = ""
                    nome   = linha
                if " - " in nome:
                    artigo_nome, cor = nome.split(" - ", 1)
                    artigo_atual = (codigo + artigo_nome).strip()
                    cor_atual    = cor.strip()
                else:
                    artigo_atual = (codigo + nome).strip()
                    cor_atual    = nome
                continue

            # Continuacao de nome quebrado sem numeros, ou linha desconhecida.
            # So reporta como nao-parseada se parecer conteudo relevante.
            if any(ch.isdigit() for ch in linha):
                linhas_nao_parseadas.append(linha_orig)

        # Validacao contra o totalizador do proprio PDF (rolos com saldo 0
        # contam no total do relatorio, mas nao viram registro importavel).
        reconhecidos = len(registros) + rolos_zerados
        if total_pdf is not None and total_pdf != reconhecidos:
            linhas_nao_parseadas.append(
                f"AVISO: o PDF informa {total_pdf} rolos, mas o parser "
                f"reconheceu {reconhecidos} ({len(registros)} com saldo"
                + (f" + {rolos_zerados} zerados" if rolos_zerados else "")
                + "). Confira as linhas nao parseadas."
            )

        return registros, linhas_nao_parseadas

    def nome_fonte(self):
        return "Vexta Estoque PDF"
