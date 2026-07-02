"""
PCP Enfestos — Multi-Ref: capacidade e pool de composições conjuntas
====================================================================

Funções puras usadas pelo solver_multiref:

- _max_pecas_camada / _piso_capacidade: prova matemática barata do MÍNIMO de
  enfestos que um grupo precisa (nenhuma busca pode fazer melhor). Usada para
  descartar grupos e níveis impossíveis em milissegundos.
- _pool_composicoes: gera composições conjuntas (uma composição por referência
  no mesmo enfesto) enumerando os vetores de peças que cabem na mesa e
  dividindo as peças por tamanho guiado pela grade de cada ref.
"""

import math
from itertools import product as iproduct

from engine.mapas import score_mapa


def _max_pecas_camada(consumos, mesa):
    """Máximo de peças (todas as refs somadas) numa camada combinada que cabe
    na mesa. DP de moedas em centímetros.

    USO EM PROVA DE PISO: este valor alimenta um lower bound ("precisa de pelo
    menos N enfestos"), então a capacidade tem que ser SUPERestimada, nunca
    subestimada — consumo arredonda para BAIXO (floor) e a mesa para CIMA.
    Subestimar a capacidade infla o piso e descartaria grupos viáveis."""
    cap = int(math.ceil(mesa * 100 - 1e-9))
    cons = sorted({max(1, int(c * 100)) for c in consumos})
    if not cons or cons[0] > cap:
        return 0
    dp = [0] * (cap + 1)
    for x in range(cons[0], cap + 1):
        best = 0
        for c in cons:
            if c > x:
                break
            v = dp[x - c] + 1
            if v > best:
                best = v
        dp[x] = best
    return dp[cap]


def _piso_capacidade(refs_data, tamanhos, mesa, max_folhas):
    """(min_enfestos, min_folhas, max_pecas) provados por capacidade.

    A demanda mínima de uma cor = soma de max(0, grade+lo) sobre (ref, tamanho)
    — cortar menos que isso viola a tolerância inferior. Cada folha corta no
    máximo max_pecas peças dessa cor, então a cor exige ceil(dem/max_pecas)
    folhas. A soma sobre as cores, dividida pelo cap de folhas por enfesto,
    dá o mínimo de enfestos FÍSICO."""
    maxp = _max_pecas_camada([float(r.get("consumo", 1.0645)) for r in refs_data], mesa)
    if maxp < 1:
        return 999, 0, 0
    cores, vistas = [], set()
    for ref in refs_data:
        for cor in ref["grade"]:
            if cor not in vistas:
                vistas.add(cor)
                cores.append(cor)
    min_folhas = 0
    for cor in cores:
        dem = 0
        for ref in refs_data:
            gc = ref["grade"].get(cor)
            if not gc:
                continue
            lim = ref.get("limites", {}).get(cor, {})
            for t in tamanhos:
                lo = lim.get(t, (0, 0))[0]
                dem += max(0, gc.get(t, 0) + lo)
        min_folhas += -(-dem // maxp)
    min_enf = -(-min_folhas // max_folhas) if min_folhas > 0 else 1
    return max(1, min_enf), min_folhas, maxp


def _vetores_pecas(consumos, mesa):
    """Todos os vetores (k_0..k_{R-1}) de peças por ref que cabem na mesa.

    Validação em FLOAT real, sem arredondar o consumo: um vetor aceito aqui
    vira composição e depois camada FÍSICA — passar da mesa é proibido (e o
    arredondamento para cm chegou a aceitar 9x1,1149m = 10,03m numa mesa de
    10m antes desta correção)."""
    R = len(consumos)
    out = []

    def rec(i, rem, cur):
        if i == R:
            if any(cur):
                out.append(tuple(cur))
            return
        kmax = int((rem + 1e-9) // consumos[i]) if consumos[i] > 0 else 0
        for k in range(kmax + 1):
            cur.append(k)
            rec(i + 1, rem - k * consumos[i], cur)
            cur.pop()

    rec(0, float(mesa), [])
    return out


def _splits_tamanho(k, grade_tot, tamanhos, max_var=8):
    """Variantes de divisão de k peças de UMA ref entre os tamanhos, guiadas
    pela grade. Retorna lista de dicts {tam: n} sem duplicatas."""
    if k == 0:
        return [{}]
    total = sum(grade_tot.get(t, 0) for t in tamanhos)
    tams_v = [t for t in tamanhos if grade_tot.get(t, 0) > 0]
    if total == 0 or not tams_v:
        return []
    variantes, vistos = [], set()

    def add(d):
        d = {t: v for t, v in d.items() if v > 0}
        if sum(d.values()) != k:
            return
        key = tuple(sorted(d.items()))
        if key not in vistos:
            vistos.add(key)
            variantes.append(d)

    def proporcional(tams):
        tot = sum(grade_tot[t] for t in tams)
        if tot == 0:
            return None
        quotas = [(t, k * grade_tot[t] / tot) for t in tams]
        base = {t: int(q) for t, q in quotas}
        resto = k - sum(base.values())
        for t, q in sorted(quotas, key=lambda x: -(x[1] - int(x[1]))):
            if resto <= 0:
                break
            base[t] += 1
            resto -= 1
        return base

    doms = sorted(tams_v, key=lambda t: -grade_tot[t])
    # a) proporcional em todos os tamanhos com volume
    p = proporcional(tams_v)
    if p:
        add(p)
    # b) proporcional só nos dominantes (top-2 e top-3)
    for nd in (2, 3):
        if len(doms) >= nd:
            p2 = proporcional(doms[:nd])
            if p2:
                add(p2)
    # c) tamanho único (mapas "leves"/puros) nos dominantes
    for t in doms[:3]:
        add({t: k})
    # d) portadores de tamanhos raros + e) vizinhança de 1 shift
    raros = [t for t in tams_v if grade_tot[t] < 0.15 * total]
    base = proporcional(tams_v)
    if base:
        maior = max(base, key=lambda t: base.get(t, 0), default=None)
        for t in raros:
            if maior and base.get(maior, 0) > 0 and base.get(t, 0) == 0:
                d = dict(base)
                d[maior] -= 1
                d[t] = d.get(t, 0) + 1
                add(d)
        for t1 in tams_v:
            if len(variantes) >= max_var:
                break
            for t2 in tams_v:
                if t1 == t2 or base.get(t1, 0) <= 0:
                    continue
                d = dict(base)
                d[t1] -= 1
                d[t2] = d.get(t2, 0) + 1
                add(d)
    return variantes[:max_var]


def _pool_composicoes(refs_data, tamanhos, mesa, pool_max=150, por_vetor=12):
    """Pool de composições conjuntas: lista de tuplas (mapa_ref0, mapa_ref1...),
    ranqueadas por aderência às grades, com diversidade garantida por vetor de
    peças (round-robin). Cada mapa_ref é um dict {tam: n}."""
    R = len(refs_data)
    consumos = [float(r.get("consumo", 1.0645)) for r in refs_data]
    grades_tot, pesos = [], []
    for r in refs_data:
        gt = {t: sum(r["grade"].get(c, {}).get(t, 0) for c in r["grade"]) for t in tamanhos}
        grades_tot.append(gt)
        pesos.append(max(1, sum(gt.values())))
    soma_pesos = sum(pesos)

    splits_cache = {}

    def splits(ri, k):
        if (ri, k) not in splits_cache:
            splits_cache[(ri, k)] = _splits_tamanho(k, grades_tot[ri], tamanhos)
        return splits_cache[(ri, k)]

    por_vec = {}
    for vec in _vetores_pecas(consumos, mesa):
        vars_por_ref = [splits(ri, vec[ri]) for ri in range(R)]
        if any(not v for v in vars_por_ref):
            continue
        cands = []
        for prod in iproduct(*vars_por_ref):
            sc = sum(
                score_mapa(prod[ri], grades_tot[ri], tamanhos) * pesos[ri]
                for ri in range(R)
            ) / soma_pesos
            sc += 0.15 * sum(vec)  # bônus por aproveitar a mesa
            cands.append((sc, prod))
        cands.sort(key=lambda x: -x[0])
        por_vec[vec] = cands[:por_vetor]

    # round-robin entre vetores (diversidade), respeitando o rank interno
    pool, vistos = [], set()
    ordem_vecs = sorted(por_vec.keys(), key=lambda v: -(por_vec[v][0][0] if por_vec[v] else 0))
    idx = 0
    while len(pool) < pool_max:
        adicionou = False
        for vec in ordem_vecs:
            cands = por_vec[vec]
            if idx < len(cands):
                sc, prod = cands[idx]
                key = tuple(tuple(sorted(m.items())) for m in prod)
                if key not in vistos:
                    vistos.add(key)
                    pool.append(prod)
                    adicionou = True
                    if len(pool) >= pool_max:
                        break
        if not adicionou:
            break
        idx += 1
    return pool
