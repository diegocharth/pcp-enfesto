"""
Gerador de composições de mapa (encaixe).
Um mapa define quantas peças de cada tamanho cabem num único encaixe.
O comprimento total do mapa = soma(pecas_por_tam) × consumo_por_peca.
"""

import math
from itertools import product as iproduct

# Injeção de mapas históricos: main.py pode setar esta lista antes de chamar
# o solver. priorizar_mapas coloca esses mapas no topo da lista de prioridades,
# acelerando a busca para grades já vistas anteriormente.
_mapas_historicos_injetar: list = []


def max_pecas_por_mapa(comprimento_mesa: float, consumo: float) -> int:
    """Número máximo de peças que cabem num mapa dado o comprimento da mesa."""
    return int(math.floor(comprimento_mesa / consumo))


def gerar_mapas(tamanhos: list, max_pecas: int, min_pecas: int = 1) -> list:
    """
    Gera todas as composições possíveis de mapa com até max_pecas peças.
    Cada composição é um dict {tamanho: qtd}.
    
    tamanhos : lista de strings, ex: ['XPP', 'PP', 'P', 'M', 'G']
    max_pecas: limite máximo de peças por mapa
    min_pecas: mínimo de peças no mapa (default 1)
    
    Retorna lista de dicts ordenada por total desc (mapas maiores primeiro).
    """
    n = len(tamanhos)
    mapas = []

    # Gerar todas as partições de 1..max_pecas em n partes não-negativas
    def _gerador(tam_idx, restante, atual):
        if tam_idx == n - 1:
            atual.append(restante)
            total = sum(atual)
            if total >= min_pecas:
                mapas.append(dict(zip(tamanhos, atual)))
            atual.pop()
            return
        for v in range(0, restante + 1):
            atual.append(v)
            _gerador(tam_idx + 1, restante - v, atual)
            atual.pop()

    for total in range(min_pecas, max_pecas + 1):
        _gerador(0, total, [])

    # Ordenar: maior total primeiro (mapas maiores têm encaixe mais eficiente)
    mapas.sort(key=lambda m: -sum(m.values()))
    return mapas


def filtrar_mapas_relevantes(mapas: list, grade_total: dict, tamanhos: list) -> list:
    """
    Remove mapas que claramente não contribuem para cobrir a grade.
    Um mapa é relevante se tem pelo menos 1 tamanho com volume na grade total.
    """
    tams_com_volume = {t for t in tamanhos if grade_total.get(t, 0) > 0}
    filtrados = []
    for m in mapas:
        if any(m.get(t, 0) > 0 for t in tams_com_volume):
            filtrados.append(m)
    return filtrados


def score_mapa(mapa: dict, grade_total: dict, tamanhos: list) -> float:
    """
    Score heurístico de um mapa: quão bem ele se alinha com as proporções da grade.
    Usado para priorizar mapas na busca.
    """
    total_grade = sum(grade_total.get(t, 0) for t in tamanhos)
    total_mapa = sum(mapa.get(t, 0) for t in tamanhos)
    if total_grade == 0 or total_mapa == 0:
        return 0.0

    score = 0.0
    for t in tamanhos:
        prop_grade = grade_total.get(t, 0) / total_grade
        prop_mapa = mapa.get(t, 0) / total_mapa
        score += min(prop_grade, prop_mapa)  # intersecção de proporções
    return score * total_mapa  # premia mapas maiores e mais alinhados


def priorizar_mapas(mapas: list, grade_total: dict, tamanhos: list, top_n: int = 300) -> list:
    """
    Retorna os top_n mapas mais promissores para o solver.

    Por que a ordem importa:
      combinations(prior[:200], 3) percorre em ordem lexicografica. O mapa na
      posicao 0 ancora ~19.700 combinacoes. Se esse mapa for incompativel com
      todas as solucoes validas, o budget de 30 s e desperdicado ali.

    Estrategia:
      1. Tamanhos raros (< 20% do total) sao detectados automaticamente.
      2. Os N_COMMON melhores mapas "sem raros" ocupam as posicoes 0..N_COMMON-1
         como ancoras eficientes (cobrem os tamanhos dominantes).
      3. Em seguida, os N_RARE melhores mapas cobrindo cada tamanho raro,
         do mais raro ao menos raro.
      4. O restante preenche em ordem de score descendente.

    Resultado para grades sem tamanhos raros: comportamento identico ao score puro.

    Aprendizado historico:
      Se _mapas_historicos_injetar estiver preenchido (por main.py antes do solve),
      esses mapas sao colocados ANTES de tudo. O solver testa a combinacao historica
      na iteracao 1 — se ela ainda for valida, ja encontra o resultado otimo imediatamente.
    """
    if not mapas:
        return []

    scored = [(score_mapa(m, grade_total, tamanhos), m) for m in mapas]
    scored.sort(key=lambda x: -x[0])

    total_grade = sum(grade_total.get(t, 0) for t in tamanhos)
    if total_grade == 0:
        return [m for _, m in scored[:top_n]]

    # 15% em vez de 20%: M tipico (19%) fica como ancora, apenas G e XPP sao raros
    raridade_thresh = total_grade * 0.15
    tams_raros = {t for t in tamanhos if 0 < grade_total.get(t, 0) < raridade_thresh}

    if not tams_raros:
        return [m for _, m in scored[:top_n]]

    # Separar mapas que cobrem apenas tamanhos comuns dos que cobrem raros
    common_maps = []
    rare_maps_per_tam = {t: [] for t in tams_raros}

    for sc, m in scored:
        cobre_raro = any(m.get(t, 0) > 0 for t in tams_raros)
        if not cobre_raro:
            common_maps.append(m)
        for t in tams_raros:
            if m.get(t, 0) > 0:
                rare_maps_per_tam[t].append(m)

    N_COMMON = 5   # ancoras nas posicoes 0..4
    N_RARE   = 10  # cobertores de raros apos as ancoras

    result = []
    in_result = set()

    # 1. Ancoras: melhores mapas sem tamanhos raros (em ordem de score)
    for m in common_maps[:N_COMMON]:
        mkey = tuple(sorted(m.items()))
        if mkey not in in_result:
            result.append(m)
            in_result.add(mkey)

    # 2. Cobertores de raros, do tamanho mais raro ao menos raro
    for t in sorted(tams_raros, key=lambda t: grade_total.get(t, 0)):
        count = 0
        for m in rare_maps_per_tam[t]:
            mkey = tuple(sorted(m.items()))
            if mkey not in in_result and count < N_RARE:
                result.append(m)
                in_result.add(mkey)
                count += 1

    # 3. Restante em ordem de score descendente
    for sc, m in scored:
        mkey = tuple(sorted(m.items()))
        if mkey not in in_result:
            result.append(m)
            in_result.add(mkey)

    # 4. Injetar mapas historicos no INICIO (aprendizado entre sessoes)
    global _mapas_historicos_injetar
    if _mapas_historicos_injetar:
        mapas_set = {tuple(sorted(m.items())) for m in mapas}
        hist_valid = [m for m in _mapas_historicos_injetar
                      if tuple(sorted(m.items())) in mapas_set]
        if hist_valid:
            hist_keys = {tuple(sorted(m.items())) for m in hist_valid}
            resto = [m for m in result if tuple(sorted(m.items())) not in hist_keys]
            result = hist_valid + resto

    return result[:top_n]
