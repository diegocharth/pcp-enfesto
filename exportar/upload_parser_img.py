"""
OCR de imagem via Claude API.
Separado do upload_parser principal para facilitar manutenção.
"""
import json
import urllib.request
import urllib.error


def extrair_grade_de_imagem(b64_data: str, mime_type: str, api_key: str) -> dict:
    """
    Envia imagem para a API do Claude e extrai grade de peças.
    Retorna: {grade, tamanhos, referencia, n_cores, erro}
    """
    if not api_key:
        return {"erro": "API key não configurada. Adicione 'anthropic_api_key' no config.json."}

    prompt = """Você é um sistema de leitura de ordens de corte de confecção.
Analise a imagem e extraia a grade de peças com quantidades por cor e tamanho.

Retorne SOMENTE um JSON válido neste formato exato:
{
  "referencia": "nome da referencia se visivel, senao string vazia",
  "tamanhos": ["XPP","PP","P","M","G"],
  "grade": {
    "BLUES": {"XPP": 1, "PP": 23, "P": 34, "M": 25, "G": 9},
    "JAZZ":  {"XPP": 2, "PP": 24, "P": 36, "M": 25, "G": 7}
  }
}

Regras importantes:
- Tamanhos usuais: XPP, PP, P, M, G, GG, XG ou numericos (34,36,38,40,42,44,46)
- Inclua apenas os tamanhos que aparecem na imagem
- Nomes de cores em MAIUSCULAS
- Valores numericos inteiros, 0 se ilegivel
- SOMENTE o JSON, sem texto antes ou depois"""

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1500,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime_type, "data": b64_data}
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
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
            texto = data["content"][0]["text"].strip()
            texto = texto.replace("```json", "").replace("```", "").strip()
            resultado = json.loads(texto)
            grade = resultado.get("grade", {})
            if not grade:
                return {"erro": "Nenhuma grade encontrada na imagem. Verifique se a foto mostra claramente os tamanhos e quantidades."}
            return {
                "grade"     : grade,
                "tamanhos"  : resultado.get("tamanhos", []),
                "referencia": resultado.get("referencia", ""),
                "n_cores"   : len(grade),
                "erro"      : None,
                "fonte"     : "ocr_imagem"
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            return {"erro": "API key inválida ou expirada. Verifique 'anthropic_api_key' no config.json."}
        if e.code == 400:
            return {"erro": "Imagem não reconhecida ou formato inválido. Tente .jpg ou .png nítido."}
        return {"erro": f"Erro da API ({e.code}): {body[:300]}"}
    except json.JSONDecodeError:
        return {"erro": "Resposta da API não está em formato JSON válido. Tente outra foto."}
    except Exception as e:
        return {"erro": f"Erro ao processar imagem: {str(e)}"}
