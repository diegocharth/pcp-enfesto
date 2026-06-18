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
        score += min(prop_grade, prop_mapa)
    return score * total_mapa


def priorizar_mapas(mapas: list, grade_total: dict, tamanhos: list, top_n: int = 300) -> list:
    """
    Retorna os top_n mapas mais promissores para o solver.

    Estrategia de ordenação:
      1. N_COMMON melhores mapas "âncora" (cobrem tamanhos dominantes, sem raros).
      2. Mapas LEVES (1 peça de um único tamanho): essenciais para enfestos
         combinados multi-ref. Quando N=4 refs dividem 10m de mesa, cada ref
         ocupa ~2,5m — ou seja, apenas 1 peça por mapa. Sem mapas leves no
         top-K, valid_combis fica vazia e o solver falha. Inseridos logo após
         as âncoras para garantir presença no top-12 de qualquer N.
      3. N_RARE melhores mapas cobrindo cada tamanho raro (< 15% da grade).
      4. Restante em ordem de score descendente.
      5. Mapas históricos injetados no topo (aprendizado entre sessões).
    """
    if not mapas:
        return []

    scored = [(score_mapa(m, grade_total, tamanhos), m) for m in mapas]
    scored.sort(key=lambda x: -x[0])

    total_grade = sum(grade_total.get(t, 0) for t in tamanhos)
    if total_grade == 0:
        return [m for _, m in scored[:top_n]]

    raridade_thresh = total_grade * 0.15
    tams_raros = {t for t in tamanhos if 0 < grade_total.get(t, 0) < raridade_thresh}
    tams_com_volume = [t for t in tamanhos if grade_total.get(t, 0) > 0]

    # ── Mapas leves: {tamanho_X: 1, outros: 0} para cada tamanho com volume ──
    # Candidatos fracos para ref individual mas excelentes para multi-ref:
    # 1 peca × consumo_ref deixa espaço para as outras N-1 refs na mesma mesa.
    mapas_existentes = {tuple(sorted(m.items())) for m in mapas}
    leves = []
    leves_keys = set()
    for t in tams_com_volume:
        m_leve = {t2: (1 if t2 == t else 0) for t2 in tamanhos}
        mkey = tuple(sorted(m_leve.items()))
        if mkey in mapas_existentes and mkey not in leves_keys:
            leves.append(m_leve)
            leves_keys.add(mkey)

    N_COMMON = 5
    N_RARE   = 10

    common_maps = []
    rare_maps_per_tam = {t: [] for t in tams_raros}
    for sc, m in scored:
        if tams_raros and not any(m.get(t, 0) > 0 for t in tams_raros):
            common_maps.append(m)
        for t in tams_raros:
            if m.get(t, 0) > 0:
                rare_maps_per_tam[t].append(m)

    result = []
    in_result = set()

    # 1. Âncoras comuns
    src_common = common_maps if tams_raros else [m for _, m in scored]
    for m in src_common[:N_COMMON]:
        mkey = tuple(sorted(m.items()))
        if mkey not in in_result:
            result.append(m)
            in_result.add(mkey)

    # 2. Mapas leves (posições N_COMMON .. N_COMMON+len(tams_com_volume)-1)
    for m in leves:
        mkey = tuple(sorted(m.items()))
        if mkey not in in_result:
            result.append(m)
            in_result.add(mkey)

    # 3. Cobertores de tamanhos raros
    for t in sorted(tams_raros, key=lambda t: grade_total.get(t, 0)):
        count = 0
        for m in rare_maps_per_tam[t]:
            mkey = tuple(sorted(m.items()))
            if mkey not in in_result and count < N_RARE:
                result.append(m)
                in_result.add(mkey)
                count += 1

    # 4. Restante em ordem de score
    for sc, m in scored:
        mkey = tuple(sorted(m.items()))
        if mkey not in in_result:
            result.append(m)
            in_result.add(mkey)

    # 5. Mapas históricos no início
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
