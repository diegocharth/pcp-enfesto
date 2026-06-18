"""
Parser de upload de ordem de produção.
Suporta .xlsx e .csv.

Formato esperado (flexível):
- Coluna de COR / REFERÊNCIA (primeira coluna com texto)
- Colunas de TAMANHO (XPP, PP, P, M, G, GG, XG — detectadas automaticamente)
- Linhas de dados: uma por cor

Exemplo:
  | Cor    | XPP | PP | P  | M  | G |
  | BLUES  |  1  | 23 | 34 | 25 | 9 |
  | JAZZ   |  2  | 24 | 36 | 25 | 7 |
"""

import io
import csv
import re

TAMANHOS_CONHECIDOS = ['XPP','PP','P','M','G','GG','XG','EXG','UNICO','U','34','36','38','40','42','44','46','48']


def _normalizar_header(h):
    """Normaliza cabeçalho para comparação."""
    return re.sub(r'\s+','', str(h)).upper().strip()


def _detectar_tamanhos(headers):
    """Retorna lista de (índice_coluna, nome_tamanho) dos tamanhos encontrados."""
    resultado = []
    for i, h in enumerate(headers):
        norm = _normalizar_header(h)
        if norm in TAMANHOS_CONHECIDOS:
            resultado.append((i, norm))
    return resultado


def _detectar_coluna_cor(headers):
    """Retorna índice da coluna de cor/referência."""
    palavras_chave = ['COR','CORES','REFERENCIA','REF','PRODUTO','VARIANTE','NOME','MODELO']
    for i, h in enumerate(headers):
        norm = _normalizar_header(h)
        if any(p in norm for p in palavras_chave):
            return i
    return 0  # default: primeira coluna


def _parse_rows(rows):
    """
    Dado rows (lista de listas de strings), detecta estrutura e extrai dados.
    Retorna: {cor: {tamanho: qtd}}, tamanhos_encontrados, referencia_sugerida
    """
    if not rows:
        return {}, [], ''

    # Procurar linha de cabeçalho (tem pelo menos 1 tamanho conhecido)
    header_idx = None
    for i, row in enumerate(rows[:10]):
        tams = _detectar_tamanhos(row)
        if tams:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Não foi possível encontrar uma linha de cabeçalho com tamanhos (XPP, PP, P, M, G, etc.)")

    headers = rows[header_idx]
    tams_cols = _detectar_tamanhos(headers)
    cor_col   = _detectar_coluna_cor(headers)
    tam_nomes = [t for _, t in tams_cols]

    grade = {}
    referencia = ''

    for row in rows[header_idx + 1:]:
        if not row or all(str(c).strip() == '' for c in row):
            continue

        # Verificar se é linha de totalização (ignora)
        primeira = str(row[0] if len(row) > 0 else '').upper().strip()
        if any(p in primeira for p in ['TOTAL','SUBTOTAL','SOMA','SUM']):
            continue

        cor_val = str(row[cor_col]).strip().upper() if cor_col < len(row) else ''
        if not cor_val or cor_val == '':
            continue

        qtds = {}
        for col_idx, tam_nome in tams_cols:
            if col_idx < len(row):
                val = str(row[col_idx]).strip().replace(',', '.').replace(' ', '')
                try:
                    qtds[tam_nome] = int(float(val)) if val else 0
                except (ValueError, TypeError):
                    qtds[tam_nome] = 0
            else:
                qtds[tam_nome] = 0

        # Só adiciona se tiver pelo menos 1 quantidade > 0
        if any(v > 0 for v in qtds.values()):
            grade[cor_val] = qtds

    return grade, tam_nomes, referencia


def parse_xlsx(conteudo_bytes):
    """Parse de arquivo .xlsx. Retorna (grade, tamanhos, referencia)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), data_only=True)
        ws = wb.active

        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(c) if c is not None else '' for c in row])

        # Tentar extrair nome da referência da primeira linha
        referencia = ''
        if rows:
            primeira = ' '.join(str(c) for c in rows[0] if c and str(c).strip())
            # Se a primeira linha não tem tamanhos, é provavelmente o nome
            if not _detectar_tamanhos(rows[0]) and primeira.strip():
                referencia = primeira.strip()

        grade, tamanhos, _ = _parse_rows(rows)
        return grade, tamanhos, referencia

    except ImportError:
        raise ImportError("openpyxl não instalado. Execute: pip install openpyxl")


def parse_csv(conteudo_bytes):
    """Parse de arquivo .csv. Retorna (grade, tamanhos, referencia)."""
    # Tentar detectar encoding
    for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
        try:
            texto = conteudo_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = conteudo_bytes.decode('latin-1', errors='replace')

    # Detectar delimitador
    sample = texto[:2000]
    delim = ';' if sample.count(';') > sample.count(',') else ','

    reader = csv.reader(io.StringIO(texto), delimiter=delim)
    rows = list(reader)

    referencia = ''
    if rows and not _detectar_tamanhos(rows[0]):
        referencia = str(rows[0][0]).strip() if rows[0] else ''

    grade, tamanhos, _ = _parse_rows(rows)
    return grade, tamanhos, referencia


def parse_arquivo(nome_arquivo, conteudo_bytes):
    """
    Ponto de entrada: recebe nome e bytes do arquivo.
    Retorna dict com grade, tamanhos, referencia e erros.
    """
    nome_lower = nome_arquivo.lower()
    try:
        if nome_lower.endswith('.xlsx') or nome_lower.endswith('.xls'):
            grade, tamanhos, referencia = parse_xlsx(conteudo_bytes)
        elif nome_lower.endswith('.csv'):
            grade, tamanhos, referencia = parse_csv(conteudo_bytes)
        else:
            return {'erro': f'Formato não suportado: {nome_arquivo}. Use .xlsx ou .csv'}

        if not grade:
            return {'erro': 'Nenhuma cor encontrada no arquivo. Verifique se há tamanhos (XPP, PP, P, M, G) no cabeçalho.'}

        return {
            'grade'     : grade,
            'tamanhos'  : tamanhos,
            'referencia': referencia,
            'n_cores'   : len(grade),
            'erro'      : None
        }

    except Exception as e:
        return {'erro': str(e)}


def parse_imagem_base64(b64_data: str, mime_type: str = "image/jpeg") -> dict:
    """
    Usa a API do Claude para extrair grade de peças de uma imagem (foto da ordem).
    Retorna mesmo formato que parse_arquivo: {grade, tamanhos, referencia, erro}
    """
    import urllib.request
    import json

    prompt = """Analise esta imagem de uma ordem de produção/corte de confecção.
Extraia a grade de peças com as quantidades por cor e tamanho.

Retorne APENAS um JSON no formato:
{
  "referencia": "nome da referência se visível, senão string vazia",
  "tamanhos": ["XPP","PP","P","M","G"],
  "grade": {
    "NOME_COR": {"XPP": 0, "PP": 23, "P": 34, "M": 25, "G": 9},
    "OUTRA_COR": {"XPP": 2, "PP": 24, "P": 36, "M": 25, "G": 7}
  }
}

Regras:
- Os nomes dos tamanhos são geralmente: XPP, PP, P, M, G, GG, XG ou números (34,36,38...)
- Inclua apenas tamanhos que aparecem na imagem com valores > 0
- Se um valor não for legível, use 0
- Normalize os nomes das cores para MAIÚSCULAS
- Retorne SOMENTE o JSON, sem texto adicional"""

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_data
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            texto = data["content"][0]["text"].strip()
            # Limpar possíveis marcadores de código
            texto = texto.replace("```json", "").replace("```", "").strip()
            resultado = json.loads(texto)
            grade = resultado.get("grade", {})
            if not grade:
                return {"erro": "Não foi possível extrair a grade da imagem."}
            return {
                "grade"     : grade,
                "tamanhos"  : resultado.get("tamanhos", []),
                "referencia": resultado.get("referencia", ""),
                "n_cores"   : len(grade),
                "erro"      : None
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "401" in str(e.code):
            return {"erro": "API key inválida. Verifique o arquivo config.json."}
        return {"erro": f"Erro na API: {e.code} — {body[:200]}"}
    except Exception as e:
        return {"erro": f"Erro ao processar imagem: {str(e)}"}
