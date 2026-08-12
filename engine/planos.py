"""
Plano de corte portatil (.plano.json) -- formato ADICIONAL de salvamento.

Motivacao: a alocacao de rolos precisava do plano recem-calculado em memoria.
Com este formato o plano calculado num dia pode ser reaberto em outro dia (ou
em outra maquina) so para fazer a alocacao de rolos, sem recalcular nada.

O formato NAO substitui nada: as planilhas .xlsx continuam sendo geradas
exatamente como antes. O .plano.json e salvo ao lado delas.

Estrutura do arquivo:
  {
    "formato": "pcp-enfestos-plano/1",
    "versao_app": "2.13.0",
    "referencia": "VESTIDO LIDIANE",
    "origem": "single" | "multiref",
    "criado_em": "2026-08-12 14:33:00",
    "plano": {
      "mapas":   [{"id": 1, "composicao": {"P": 2}, "n_pecas": 2,
                   "comp_camada_m": 2.13, "comp_calc_m": 2.13}, ...],
      "camadas": {"COR": {"1": 25, "2": 10}, ...},
      "consumo_peca": 1.06
    },
    "cores": ["COR", ...]
  }
"""

import json
import os
import re
import time

FORMATO = "pcp-enfestos-plano/1"


def validar_plano(plano):
    """
    Valida e normaliza o nucleo do plano (o dict 'plano' do arquivo).
    Retorna o plano normalizado ou lanca ValueError com mensagem clara.
    """
    if not isinstance(plano, dict):
        raise ValueError("Plano invalido: esperado um objeto.")

    mapas = plano.get("mapas")
    if not isinstance(mapas, list) or not mapas:
        raise ValueError("Plano invalido: campo 'mapas' vazio ou ausente.")
    mapas_norm = []
    for m in mapas:
        if not isinstance(m, dict) or "id" not in m:
            raise ValueError("Plano invalido: mapa sem campo 'id'.")
        try:
            mid = int(m["id"])
        except (TypeError, ValueError):
            raise ValueError(f"Plano invalido: id de mapa nao numerico ({m.get('id')!r}).")
        comp = m.get("composicao") or {}
        if not isinstance(comp, dict):
            raise ValueError(f"Plano invalido: composicao do mapa {mid} invalida.")
        try:
            n_pecas = int(m.get("n_pecas") or sum(int(v) for v in comp.values()))
        except (TypeError, ValueError):
            raise ValueError(f"Plano invalido: n_pecas do mapa {mid} invalido.")
        novo = {"id": mid, "composicao": comp, "n_pecas": n_pecas}
        for chave in ("comp_camada_m", "comp_calc_m"):
            if m.get(chave) is not None:
                try:
                    novo[chave] = float(m[chave])
                except (TypeError, ValueError):
                    raise ValueError(f"Plano invalido: {chave} do mapa {mid} invalido.")
        mapas_norm.append(novo)

    camadas = plano.get("camadas")
    if not isinstance(camadas, dict) or not camadas:
        raise ValueError("Plano invalido: campo 'camadas' vazio ou ausente.")
    ids_validos = {m["id"] for m in mapas_norm}
    camadas_norm = {}
    for cor, por_mapa in camadas.items():
        if not isinstance(por_mapa, dict):
            raise ValueError(f"Plano invalido: camadas da cor {cor} invalidas.")
        norm = {}
        for k, v in por_mapa.items():
            try:
                mid, n = int(k), int(v)
            except (TypeError, ValueError):
                raise ValueError(f"Plano invalido: camadas da cor {cor} invalidas.")
            if mid not in ids_validos:
                raise ValueError(
                    f"Plano invalido: cor {cor} referencia mapa {mid} inexistente.")
            if n > 0:
                norm[mid] = n
        if norm:
            camadas_norm[str(cor)] = norm
    if not camadas_norm:
        raise ValueError("Plano invalido: nenhuma camada > 0.")

    try:
        consumo = float(plano.get("consumo_peca", 0) or 0)
    except (TypeError, ValueError):
        consumo = 0.0
    if consumo <= 0:
        raise ValueError("Plano invalido: consumo_peca deve ser maior que zero.")

    return {"mapas": mapas_norm, "camadas": camadas_norm, "consumo_peca": consumo}


def _sanitizar_nome(referencia):
    ref = re.sub(r"[^A-Za-z0-9_ .-]+", "", str(referencia or "REF")).strip()
    return (ref.replace(" ", "_") or "REF")[:40]


def salvar_plano(plano, referencia, pasta, versao_app="", origem=""):
    """
    Salva o plano portatil em `pasta` e retorna o caminho do arquivo.
    O plano e validado antes de salvar.
    """
    nucleo = validar_plano(plano)
    os.makedirs(pasta, exist_ok=True)
    ts   = time.strftime("%Y%m%d_%H%M%S")
    nome = f"plano_corte_{_sanitizar_nome(referencia)}_{ts}.plano.json"
    caminho = os.path.join(pasta, nome)
    doc = {
        "formato"   : FORMATO,
        "versao_app": versao_app,
        "referencia": str(referencia or "REF"),
        "origem"    : origem or "",
        "criado_em" : time.strftime("%Y-%m-%d %H:%M:%S"),
        "plano"     : nucleo,
        "cores"     : sorted(nucleo["camadas"].keys()),
    }
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
    return caminho


def parsear_plano_doc(doc):
    """
    Valida um documento .plano.json ja carregado (dict) e devolve o documento
    com o nucleo normalizado. Lanca ValueError se invalido.
    """
    if not isinstance(doc, dict):
        raise ValueError("Arquivo de plano invalido.")
    if doc.get("formato") != FORMATO:
        raise ValueError(
            "Arquivo nao reconhecido como plano de corte "
            f"(esperado formato '{FORMATO}').")
    doc = dict(doc)
    doc["plano"] = validar_plano(doc.get("plano"))
    doc["cores"] = sorted(doc["plano"]["camadas"].keys())
    return doc


def parsear_plano_json(texto):
    """Como parsear_plano_doc, mas a partir do texto JSON."""
    try:
        doc = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalido: {e}")
    return parsear_plano_doc(doc)


def listar_planos(pasta, limite=50):
    """
    Lista os planos portateis salvos em `pasta`, do mais recente para o mais
    antigo. Ignora arquivos corrompidos.
    """
    if not os.path.isdir(pasta):
        return []
    arquivos = [n for n in os.listdir(pasta) if n.endswith(".plano.json")]
    arquivos.sort(key=lambda n: os.path.getmtime(os.path.join(pasta, n)),
                  reverse=True)
    saida = []
    for nome in arquivos[:limite]:
        try:
            with open(os.path.join(pasta, nome), encoding="utf-8") as f:
                doc = json.load(f)
            nucleo = doc.get("plano") or {}
            saida.append({
                "nome"      : nome,
                "referencia": doc.get("referencia", ""),
                "criado_em" : doc.get("criado_em", ""),
                "origem"    : doc.get("origem", ""),
                "n_mapas"   : len(nucleo.get("mapas") or []),
                "cores"     : sorted((nucleo.get("camadas") or {}).keys()),
            })
        except Exception:
            continue
    return saida


def carregar_plano(pasta, nome):
    """
    Carrega e valida um plano salvo. `nome` deve ser um nome de arquivo direto
    (sem separadores de caminho -- protecao contra path traversal).
    """
    if (not nome or "/" in nome or "\\" in nome or ".." in nome
            or not nome.endswith(".plano.json")):
        raise ValueError("Nome de arquivo de plano invalido.")
    caminho = os.path.join(pasta, nome)
    if not os.path.isfile(caminho):
        raise ValueError(f"Plano nao encontrado: {nome}")
    with open(caminho, encoding="utf-8") as f:
        texto = f.read()
    return parsear_plano_json(texto)
