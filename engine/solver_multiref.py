"""
PCP Enfestos — Solver Multi-Ref v2.0
====================================

Cada referência tem sua própria composição no enfesto combinado.
Restrição física: sum(n_pecas_j × consumo_j) <= mesa para cada slot de enfesto,
e a FOLHA (camada física) é compartilhada por todas as refs que usam a cor no
mesmo slot — cortar N folhas corta N cópias de TODAS as peças de TODAS as refs.

Arquitetura da v2.0 (velocidade + assertividade):

1. PISO DE CAPACIDADE (engine/multiref_pool._piso_capacidade): prova matemática
   barata do mínimo de enfestos; grupos/níveis impossíveis morrem em ms.
2. POOL CONJUNTO (engine/multiref_pool._pool_composicoes): composições geradas
   por vetores de peças + splits guiados pela grade (diversidade garantida).
3. FASE A: varredura de combinações COM repetição do pool (multiset) com solve
   exato por cor (propagação de intervalos + enumeração da caixa; fallback no
   coordinate descent do solver single-ref).
4. FASE B (engine/multiref_local.buscar_local): quando a varredura não acha,
   busca local guiada por violação no espaço completo de composições —
   encontra combinações "criativas" que nenhum pool estático contém.
"""

import time
from itertools import combinations_with_replacement

from engine.solver import _resolver_folhas_cor
from engine.multiref_pool import _piso_capacidade, _pool_composicoes
from engine.multiref_local import buscar_local, _HAS_NP

if _HAS_NP:
    import numpy as _np


# ─────────────────────────────────────────────────────────────────────────────
# Folhas por cor: exato (propagação de intervalos) com fallback
# ─────────────────────────────────────────────────────────────────────────────

def _folhas_exato(rows, g, lims, caps, max_pontos=1500):
    """Resolve folhas[k] >= 0 exatamente para dimensões compostas pequenas.

    rows[k][ti] = peças da dimensão ti no slot k; g[ti] = grade; lims[ti] =
    (lo, hi); caps[k] = folhas restantes no slot. Propaga intervalos até o
    ponto fixo; se a caixa resultante é pequena, enumera e devolve o ponto
    viável de MENOR desvio. Retorna:
      lista  -> solução exata
      None   -> provadamente inviável
      "big"  -> caixa grande demais (chamador usa o coordinate descent)"""
    n = len(rows)
    T = len(g)
    lob = [0] * n
    upb = [int(c) for c in caps]
    if any(u < 0 for u in upb):
        return None

    # Propagação de intervalos (bounds consistency) até o ponto fixo
    for _ in range(30):
        mudou = False
        for ti in range(T):
            lo_t = g[ti] + lims[ti][0]
            hi_t = g[ti] + lims[ti][1]
            soma_min = sum(rows[k][ti] * lob[k] for k in range(n))
            soma_max = sum(rows[k][ti] * upb[k] for k in range(n))
            if soma_max < lo_t or soma_min > hi_t:
                return None
            for k in range(n):
                a = rows[k][ti]
                if a <= 0:
                    continue
                max_outros = soma_max - a * upb[k]
                min_outros = soma_min - a * lob[k]
                folga_lo = lo_t - max_outros
                if folga_lo > 0:
                    nlo = -(-folga_lo // a)
                    if nlo > lob[k]:
                        lob[k] = nlo
                        mudou = True
                nhi = (hi_t - min_outros) // a
                if nhi < upb[k]:
                    upb[k] = nhi
                    mudou = True
                if lob[k] > upb[k]:
                    return None
        if not mudou:
            break

    tam_caixa = 1
    for k in range(n):
        tam_caixa *= (upb[k] - lob[k] + 1)
        if tam_caixa > max_pontos:
            return "big"

    # Enumeração exaustiva da caixa: menor desvio viável (para no desvio zero)
    best, best_dev = None, None
    fs = [0] * n

    def rec(k):
        nonlocal best, best_dev
        if best_dev == 0:
            return
        if k == n:
            dev = 0
            for ti in range(T):
                ct = 0
                for j in range(n):
                    ct += rows[j][ti] * fs[j]
                diff = ct - g[ti]
                if diff < lims[ti][0] or diff > lims[ti][1]:
                    return
                dev += diff if diff >= 0 else -diff
            if best is None or dev < best_dev:
                best, best_dev = list(fs), dev
            return
        for v in range(lob[k], upb[k] + 1):
            fs[k] = v
            rec(k + 1)

    rec(0)
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Solver principal
# ─────────────────────────────────────────────────────────────────────────────

def resolver_multiref(refs_data, tamanhos, config, callback=None, timeout_s=120,
                      n_mapas_max=7, resume_out=None):
    """
    refs_data: list of {
        nome:    str,
        grade:   {cor: {tam: int}},
        consumo: float,
        limites: {cor: {tam: (lo, hi)}}
    }
    n_mapas_max: limite superior de enfestos a buscar (branch-and-bound). Combinar
        refs so compensa se usar MENOS enfestos que mante-las separadas; o
        orquestrador passa (baseline_do_grupo - 1). n_mapas_max < 1 -> vazio.
    Retorna lista de soluções ordenadas por (n_mapas, desvio_total).
    Cada solução: {n_mapas, refs_sol, comprimentos, desvio_total, resumo}
    """
    mesa       = float(config.get("mesa_comprimento_m", 10.0))
    max_folhas = int(config.get("limite_folhas_padrao", 70))
    num_opcoes = int(config.get("num_opcoes_saida", 2))
    N          = len(refs_data)
    t0         = time.time()
    n_teto     = min(7, int(n_mapas_max))

    def log(msg):
        if callback:
            callback(msg)

    if resume_out is not None:
        resume_out["convergiu"] = True  # default; vira False so se cortar por timeout

    if n_teto < 1:
        log("Combinar este grupo nao reduz enfestos (limite < 1). Pulando.")
        return []

    log(f"Multi-ref combinado: {N} refs | Mesa: {mesa}m | Timeout: {timeout_s}s | ate {n_teto} enfesto(s)")

    # ── Normaliza as grades para a UNIAO de cores do grupo ──────────────────
    # A folha e compartilhada: pecas de uma ref presente no slot SAO cortadas
    # tambem nas cores que essa ref nao pediu. Incluir a cor faltante com
    # grade zero (e a janela de tolerancia de grade 0) faz o solver enxergar
    # e LIMITAR essa producao indesejada — sem isso o desvio mentia por
    # omissao e pecas nao pedidas eram cortadas de graca.
    from engine.tolerancia import calcular_limites as _calc_lim
    cores_uniao, _vistas_u = [], set()
    for ref in refs_data:
        for cor in ref["grade"]:
            if cor not in _vistas_u:
                _vistas_u.add(cor)
                cores_uniao.append(cor)
    refs_norm = []
    for r in refs_data:
        r2 = dict(r)
        r2["grade"] = dict(r["grade"])
        r2["limites"] = dict(r.get("limites", {}))
        for cor in cores_uniao:
            if cor not in r2["grade"]:
                r2["grade"][cor] = {t: 0 for t in tamanhos}
                r2["limites"][cor] = {t: _calc_lim(0.0, t, config, None)
                                      for t in tamanhos}
        refs_norm.append(r2)
    refs_data = refs_norm

    # ── Piso de capacidade: prova barata antes de qualquer busca ─────────────
    min_enf, min_folhas_nec, maxp = _piso_capacidade(refs_data, tamanhos, mesa, max_folhas)
    if maxp < 1:
        log("Nenhuma peca cabe na mesa — verifique consumos e mesa.")
        return []
    log(f"Piso de capacidade: demanda minima exige >= {min_folhas_nec} folhas "
        f"(max {maxp} pecas/camada) => >= {min_enf} enfesto(s) combinados")
    if min_enf > n_teto:
        log(f"IMPOSSIVEL combinar este grupo com ganho: precisa de >= {min_enf} "
            f"enfestos e o teto util e {n_teto} (menos que manter separado). "
            f"Descartado por prova de capacidade — sem busca.")
        return []
    if min_enf > 1:
        log(f"Niveis 1..{min_enf - 1} pulados: impossiveis por capacidade de folhas.")

    # ── Pool de composições conjuntas ────────────────────────────────────────
    log("Gerando composicoes conjuntas (vetores de pecas x splits por grade)...")
    pool_geral = _pool_composicoes(refs_data, tamanhos, mesa, pool_max=150)
    if not pool_geral:
        log("Nenhuma composicao conjunta cabe na mesa! Verifique consumos e mesa.")
        return []
    log(f"Composicoes candidatas: {len(pool_geral)}")

    # Cores em ordem de demanda combinada (falha rapido nas maiores)
    todas_cores, vistas_cor = [], set()
    for ref in refs_data:
        for cor in ref["grade"]:
            if cor not in vistas_cor:
                vistas_cor.add(cor)
                todas_cores.append(cor)
    todas_cores.sort(key=lambda c: -sum(
        sum(ref["grade"].get(c, {}).values()) for ref in refs_data
    ))

    # Dimensões compostas por cor (independem do combo)
    dims_por_cor = {}
    dims_np = {}
    for cor in todas_cores:
        comp_tams, comp_grade, comp_limite = [], [], []
        for ri, ref in enumerate(refs_data):
            grade_cor_ref = ref["grade"].get(cor)
            if not grade_cor_ref:
                continue
            lim_cor_ref = ref.get("limites", {}).get(cor, {})
            for t in tamanhos:
                comp_tams.append((ri, t))
                comp_grade.append(grade_cor_ref.get(t, 0))
                comp_limite.append(lim_cor_ref.get(t, (0, 0)))
        dims_por_cor[cor] = (comp_tams, comp_grade, comp_limite)
        if _HAS_NP:
            gv = _np.array(comp_grade, dtype=_np.int64)
            lov = gv + _np.array([l[0] for l in comp_limite], dtype=_np.int64)
            hiv = gv + _np.array([l[1] for l in comp_limite], dtype=_np.int64)
            dims_np[cor] = (comp_tams, gv, lov, hiv)

    consumos_f = [float(r.get("consumo", 1.0645)) for r in refs_data]

    # ── Avaliação de um combo (compartilhada pelas fases A e B) ─────────────
    def avaliar_combo(combo, n_mapas):
        """Solve exato/CD por cor. Retorna (folhas_por_cor, desvios) ou None."""
        # Defesa em profundidade: comprimento FISICO do slot nunca passa da
        # mesa (validado em float real, independente de como o combo nasceu)
        for k in range(n_mapas):
            ln = sum(sum(combo[k][ri].values()) * consumos_f[ri] for ri in range(N))
            if ln > mesa + 1e-6:
                return None
        used_per_slot = [0] * n_mapas
        folhas_por_cor = {}
        for cor in todas_cores:
            remaining = [max_folhas - used_per_slot[k] for k in range(n_mapas)]
            comp_tams, comp_grade, comp_limite = dims_por_cor[cor]
            if not comp_tams:
                folhas_por_cor[cor] = [0] * n_mapas
                continue
            rows = [[combo[k][ri].get(t, 0) for (ri, t) in comp_tams]
                    for k in range(n_mapas)]
            fs = _folhas_exato(rows, comp_grade, comp_limite, remaining)
            if fs == "big":
                rows_d = [{ti: rows[k][ti] for ti in range(len(comp_tams))}
                          for k in range(n_mapas)]
                grade_d = {ti: comp_grade[ti] for ti in range(len(comp_tams))}
                lim_d = {ti: comp_limite[ti] for ti in range(len(comp_tams))}
                fs = _resolver_folhas_cor(
                    rows_d, grade_d, list(range(len(comp_tams))), lim_d, remaining)
            if fs is None:
                return None
            folhas_por_cor[cor] = [int(x) for x in fs]
            for k in range(n_mapas):
                used_per_slot[k] += folhas_por_cor[cor][k]
        if any(used_per_slot[k] > max_folhas for k in range(n_mapas)):
            return None
        return folhas_por_cor

    def montar_solucao(combo, folhas_por_cor, n_mapas):
        desvio_total = 0
        desvio_rel = 0.0
        for cor in todas_cores:
            comp_tams, comp_grade, _ = dims_por_cor[cor]
            fs = folhas_por_cor[cor]
            for ti, (ri, t) in enumerate(comp_tams):
                ct = sum(fs[k] * combo[k][ri].get(t, 0) for k in range(n_mapas))
                diff = ct - comp_grade[ti]
                desvio_total += abs(diff)
                desvio_rel += abs(diff) / (comp_grade[ti] or 1)
        comprimentos = [
            round(sum(sum(combo[k][j].values()) * float(refs_data[j].get("consumo", 1.0645))
                      for j in range(N)), 4)
            for k in range(n_mapas)
        ]
        total_pecas = sum(sum(combo[k][j].values()) for j in range(N) for k in range(n_mapas))
        total_folhas = sum(sum(folhas_por_cor[c][k] for c in todas_cores)
                           for k in range(n_mapas))
        media_pecas = round(total_pecas / n_mapas, 1)
        refs_sol = []
        for ri, ref in enumerate(refs_data):
            refs_sol.append({
                "nome"   : ref.get("nome", f"Ref {ri+1}"),
                "consumo": float(ref.get("consumo", 1.0645)),
                "grade"  : ref["grade"],
                "limites": ref.get("limites", {}),
                "mapas"  : [dict(combo[k][ri]) for k in range(n_mapas)],
                "folhas" : {cor: list(folhas_por_cor[cor]) for cor in ref["grade"]},
            })
        return {
            "n_mapas"     : n_mapas,
            "refs_sol"    : refs_sol,
            "comprimentos": comprimentos,
            "desvio_total": desvio_total,
            "resumo"      : {
                "n_mapas"                 : n_mapas,
                "comprimentos_por_enfesto": comprimentos,
                "comprimento_total"       : round(sum(comprimentos), 4),
                "total_folhas"            : total_folhas,
                "desvio_total"            : desvio_total,
                "desvio_relativo"         : round(desvio_rel, 4),
                "media_pecas_mapa"        : media_pecas,
            },
        }

    # ── Busca em dois passes ─────────────────────────────────────────────────
    # Pass 1 (ASCENDENTE, varredura estatica): niveis baixos tem poucas
    #   combinacoes — se existe solucao "facil" com poucos enfestos, ela sai
    #   barata e ja e a otima em n_mapas.
    # Pass 2 (DESCENDENTE, busca local): viabilidade e (na pratica) monotona
    #   em n — mais slots = mais liberdade. Se nada saiu no pass 1, procurar
    #   primeiro no TETO (onde e mais facil achar) e descer enquanto achar.
    #   Se nem no teto ha solucao, niveis menores nao terao — para na hora.
    melhores        = []
    cortado_timeout = False
    todos_completos = True
    deadline_global = t0 + timeout_s
    lim_pool = {1: 150, 2: 125, 3: 80, 4: 55, 5: 40, 6: 32, 7: 26}

    def ordenar():
        melhores.sort(key=lambda s: (
            s["n_mapas"],
            s["desvio_total"],
            -s["resumo"]["media_pecas_mapa"],
            s["resumo"]["desvio_relativo"],
        ))

    # ── Pass 1: varredura estatica ascendente (35% do orcamento, teto 30s —
    # se a solucao "facil" nao saiu em 30s de varredura, e melhor investir o
    # resto na busca local, que e quem acha as combinacoes dificeis) ─────────
    pass1_deadline = t0 + min(0.35 * timeout_s, 30.0)
    nivel_achado = None
    for n_mapas in range(min_enf, n_teto + 1):
        agora = time.time()
        if agora > pass1_deadline:
            todos_completos = False
            break
        pool = pool_geral[:lim_pool.get(n_mapas, 24)]
        log(f"\nVarredura com {n_mapas} enfesto(s) (pool {len(pool)}, com repeticao)...")
        combos_testadas = 0
        combos_validas = 0
        nivel_completo = True
        for combo in combinations_with_replacement(pool, n_mapas):
            if combos_testadas % 128 == 0 and combos_testadas > 0:
                if time.time() > pass1_deadline:
                    nivel_completo = False
                    break
            combos_testadas += 1
            folhas_por_cor = avaliar_combo(combo, n_mapas)
            if folhas_por_cor is None:
                continue
            combos_validas += 1
            melhores.append(montar_solucao(combo, folhas_por_cor, n_mapas))
        log(f"  Testadas: {combos_testadas:,} | Viaveis: {combos_validas}"
            + ("" if nivel_completo else " (interrompida no orcamento)"))
        if not nivel_completo:
            todos_completos = False
        if melhores:
            nivel_achado = n_mapas
            ordenar()
            log(f"  → Melhor: {n_mapas} enf., desvio={melhores[0]['desvio_total']}pcs")
            break  # nivel mais baixo possivel da varredura — nao ha melhor

    # ── Pass 2: busca local descendente ──────────────────────────────────────
    # Comeca no teto (ou logo abaixo do nivel ja achado) e desce enquanto
    # encontrar solucao. Cada nivel ganha ~55% do tempo restante.
    if _HAS_NP:
        grades_tot_ref = []
        for r in refs_data:
            grades_tot_ref.append({
                t: sum(r["grade"].get(c, {}).get(t, 0) for c in r["grade"])
                for t in tamanhos
            })
        consumos_ref = [float(r.get("consumo", 1.0645)) for r in refs_data]

        def seeds_para(n_mapas):
            from engine.multiref_pool import _splits_tamanho
            pool = pool_geral[:lim_pool.get(n_mapas, 24)]
            seeds = []
            base = pool[:max(8, n_mapas)]
            for j in range(min(6, len(base))):
                seeds.append([base[(j + i) % len(base)] for i in range(n_mapas)])
            # sementes "puras": slots dedicados a uma ref so, proporcional a
            # demanda em comprimento de cada ref (ponto de partida parecido
            # com manter separadas, que a busca local funde gradualmente)
            dem_len = [max(0.001, sum(grades_tot_ref[ri].values()) * consumos_ref[ri])
                       for ri in range(N)]
            tot_len = sum(dem_len)
            aloc = [max(1 if dem_len[ri] > 0.01 else 0,
                        int(round(n_mapas * dem_len[ri] / tot_len)))
                    for ri in range(N)]
            while sum(aloc) > n_mapas:
                aloc[aloc.index(max(aloc))] -= 1
            while sum(aloc) < n_mapas:
                aloc[dem_len.index(max(dem_len))] += 1
            slots = []
            for ri in range(N):
                kmax = int((mesa + 1e-9) / consumos_ref[ri])
                if kmax < 1:
                    continue  # peca nem cabe na mesa: sem slot puro desta ref
                sp = _splits_tamanho(kmax, grades_tot_ref[ri], tamanhos)
                m = sp[0] if sp else {}
                for _ in range(aloc[ri]):
                    slots.append(tuple(m if rj == ri else {} for rj in range(N)))
            if len(slots) == n_mapas:
                seeds.append(slots)
            return seeds

        n_atual = (nivel_achado - 1) if nivel_achado else n_teto
        while n_atual >= min_enf:
            restante = deadline_global - time.time()
            if restante < 8:
                if not melhores:
                    todos_completos = False
                break
            budget = max(10.0, restante * 0.55)
            nivel_deadline = min(deadline_global, time.time() + budget)
            log(f"\nBusca local com {n_atual} enfesto(s) "
                f"(ate {int(nivel_deadline - time.time())}s)...")
            ja = set()
            achadas = buscar_local(
                refs_data, tamanhos, n_atual, mesa, max_folhas, dims_np,
                todas_cores, seeds_para(n_atual), nivel_deadline, ja,
                max_solucoes=num_opcoes,
                estagnacao_s=max(12.0, 0.3 * budget))
            if not achadas:
                log(f"  Nada viavel com {n_atual} enfesto(s) — parando a descida.")
                if not melhores:
                    todos_completos = False
                break
            for estado, folhas_soft in achadas:
                combo = tuple(estado)
                folhas_por_cor = avaliar_combo(combo, n_atual)
                if folhas_por_cor is None:
                    # consistencia garantida: folhas do proprio soft solve (viavel)
                    folhas_por_cor = {c: [int(x) for x in folhas_soft[c]]
                                      for c in folhas_soft}
                melhores.append(montar_solucao(combo, folhas_por_cor, n_atual))
            ordenar()
            log(f"  Encontrada(s) {len(achadas)} solucao(oes) com {n_atual} enfesto(s); "
                f"melhor desvio={melhores[0]['desvio_total']}pcs. Tentando {n_atual - 1}...")
            n_atual -= 1

    if time.time() > deadline_global:
        cortado_timeout = True

    if resume_out is not None:
        resume_out["convergiu"] = not cortado_timeout

    if not melhores:
        if todos_completos and not cortado_timeout:
            log(f"\nSem combinacao viavel com {min_enf}..{n_teto} enfesto(s) "
                f"(varredura completa + busca local). Combinar nao ajuda este grupo.")
        else:
            log(f"\nSem combinacao viavel encontrada dentro do orcamento "
                f"(niveis {min_enf}..{n_teto}; varredura + busca local). "
                f"Combinar provavelmente nao ajuda este grupo.")
        return []

    ordenar()
    return melhores[:num_opcoes]
