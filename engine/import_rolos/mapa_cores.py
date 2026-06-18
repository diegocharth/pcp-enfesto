"""
Mapeamento de cor de fornecedor para cor comercial.

Problema: o ERP usa nomes de cor do fornecedor (ex: '27339A SILVER BIRCH'),
mas os enfestos usam a cor comercial da empresa (ex: 'OFFWHITE').
O mesmo nome comercial pode ter varios nomes de fornecedor.

Persistencia: dados/mapa_cores.json
  {
    "OFFWHITE":  {"fornecedores": ["27339A SILVER BIRCH", "BRANCO NEVE 23A"]},
    "PRETO":     {"fornecedores": ["BLACK", "PRETO TOTAL", "BLACK-001"]}
  }

Fluxo de uso:
  1. resolver_cor() busca a cor comercial para um nome de fornecedor.
  2. Se nao encontrar, retorna None (interface pergunta ao usuario).
  3. adicionar_mapeamento() grava a resposta do usuario no JSON.
  4. Proximas vezes, o mapeamento e automatico.
"""

import json
import os
import re


def _normalizar(texto):
    """Normaliza para comparacao: maiusculas, sem espacos extras."""
    return re.sub(r"\s+", " ", str(texto).strip().upper())


def carregar_mapa(caminho_json):
    """Carrega o mapa de cores do arquivo JSON. Retorna {} se nao existir."""
    if not os.path.exists(caminho_json):
        return {}
    try:
        with open(caminho_json, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def salvar_mapa(mapa, caminho_json):
    """Persiste o mapa de cores no arquivo JSON."""
    os.makedirs(os.path.dirname(caminho_json), exist_ok=True)
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2, sort_keys=True)


def resolver_cor(cor_fornecedor, caminho_json):
    """
    Busca a cor comercial para um nome de fornecedor (case-insensitive).

    Returns:
        str | None: Nome da cor comercial, ou None se nao encontrado.
    """
    mapa    = carregar_mapa(caminho_json)
    busca   = _normalizar(cor_fornecedor)
    for cor_comercial, dados in mapa.items():
        for fornecedor in dados.get("fornecedores", []):
            if _normalizar(fornecedor) == busca:
                return cor_comercial
    return None


def adicionar_mapeamento(cor_fornecedor, cor_comercial, caminho_json):
    """
    Grava a associacao cor_fornecedor -> cor_comercial no JSON.
    Nao sobrescreve: se o mapeamento ja existir (mesmo comercial), ignora.
    Se o fornecedor ja estiver mapeado para OUTRO comercial, levanta ValueError.

    Returns:
        bool: True se gravou novo mapeamento, False se ja existia (identico).
    """
    mapa    = carregar_mapa(caminho_json)
    busca   = _normalizar(cor_fornecedor)
    comercial_norm = cor_comercial.strip().upper()

    # Verifica se ja existe mapeamento para este fornecedor
    for cc, dados in mapa.items():
        for forn in dados.get("fornecedores", []):
            if _normalizar(forn) == busca:
                if cc.upper() == comercial_norm:
                    return False  # ja existe, identico
                raise ValueError(
                    f"Cor '{cor_fornecedor}' ja esta mapeada para '{cc}'. "
                    f"Para alterar, remova o mapeamento existente primeiro."
                )

    # Adiciona ao comercial (cria entrada se necessario)
    if comercial_norm not in mapa:
        mapa[comercial_norm] = {"fornecedores": []}
    if cor_fornecedor not in mapa[comercial_norm]["fornecedores"]:
        mapa[comercial_norm]["fornecedores"].append(cor_fornecedor)

    salvar_mapa(mapa, caminho_json)
    return True


def aplicar_mapa(registros, caminho_json):
    """
    Aplica o mapeamento de cores a uma lista de registros extraidos do ERP.

    Args:
        registros: list[dict] com 'cor_fornecedor' (saida de FonteRolos.extrair)
        caminho_json: caminho para mapa_cores.json

    Returns:
        (rolos_por_cor, cores_nao_reconhecidas)
        - rolos_por_cor: {"COR_COMERCIAL": [comprimento1, comprimento2, ...]}
        - cores_nao_reconhecidas: list[str] cores de fornecedor sem mapeamento
    """
    rolos_por_cor       = {}
    nao_reconhecidas    = set()

    for reg in registros:
        cf  = reg.get("cor_fornecedor", "")
        cor = resolver_cor(cf, caminho_json)
        if cor:
            rolos_por_cor.setdefault(cor, []).append(reg["comprimento_m"])
        else:
            nao_reconhecidas.add(cf)

    return rolos_por_cor, sorted(nao_reconhecidas)
