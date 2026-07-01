"""
PCP Enfestos — Solver Multi-Ref v1.0
Cada referência tem sua própria composição no enfesto combinado.
Restrição: sum(n_pecas_j × consumo_j) <= mesa para cada slot de enfesto.
"""

import time
from itertools import product as iproduct, combinations

from engine.mapas   import gerar_mapas, filtrar_mapas_relevantes, priorizar_mapas, max_pecas_por_mapa
from engine.solver  import _resolver_folhas_cor


def resolver_multiref(refs_data, tamanhos, config, callback=None, timeout_s=120, n_mapas_max=7, resume_out=None):
    """
    refs_data: list of {
        nome:    str,
        grade:   {cor: {tam: int}},
        consumo: float,
        limites: {cor: {tam: (lo, hi)}}
    }
    n_mapas_max: limite superior de enfestos a buscar (branch-and-bound). Combinar
        refs so compensa se usar MENOS enfestos que mante-las separadas; o
        orquestrador passa (baseline_do_grupo - 1) para nunca gastar tempo com
        combinacoes profundas que ja seriam descartadas. n_mapas_max < 1 -> vazio.
    Retorna lista de soluções ordenadas por (n_mapas, desvio_total).
    Cada solução: {n_mapas, refs_sol, comprimentos, desvio_total, resumo}
    """
    mesa       = float(config.get("mesa_comprimento_m", 10.0))
    max_folhas = int(config.get("limite_folhas_padrao", 70))
    num_opcoes = int(config.get("num_opcoes_saida", 2))
    N          = len(refs_data)
    t0         = time.time()
    n_teto     = min(7, int(n_mapas_max))  # teto efetivo de enfestos a explorar

    def log(msg):
        if callback:
            callback(msg)

    if resume_out is not None:
        resume_out["convergiu"] = True  # default; vira False so se cortar por timeout

    if n_teto < 1:
        log("Combinar este grupo nao reduz enfestos (limite < 1). Pulando.")
        return []

    log(f"Multi-ref combinado: {N} refs | Mesa: {mesa}m | Timeout: {timeout_s}s | ate {n_teto} enfesto(s)")

    # ── Gera mapas candidatos por referência ──────────────────────────────────
    K_por_ref = max(10, {2: 35, 3: 22, 4: 12}.get(N, 10))
    mapas_por_ref = []
    for ri, ref in enumerate(refs_data):
        consumo = float(ref.get("consumo", 1.0645))
        if consumo <= 0:
            consumo = 1.0645
        max_p = max_pecas_por_mapa(mesa, consumo)
        if max_p < 1:
            log(f"  AVISO: {ref.get('nome','?')} — consumo {consumo}m excede mesa {mesa}m")
            max_p = 1
        grade_tot = {t: sum(ref["grade"].get(c, {}).get(t, 0) for c in ref["grade"]) for t in tamanhos}
        todos  = gerar_mapas(tamanhos, max_p)
        rel    = filtrar_mapas_relevantes(todos, grade_tot, tamanhos)
        prior  = priorizar_mapas(rel, grade_tot, tamanhos, top_n=K_por_ref)
        if not prior:
            log(f"  AVISO: {ref.get('nome','?')} sem mapas candidatos (grade vazia?)")
            prior = [{}]
        mapas_por_ref.append(prior)
        log(f"  {ref.get('nome','Ref '+str(ri+1))}: {len(prior)} mapas candidatos (cons={consumo}m, max={max_p}pcs)")

    # ── Diagnóstico: mínimo de peças por ref ─────────────────────────────────
    for j, prior in enumerate(mapas_por_ref):
        min_p = min(sum(m.values()) for m in prior) if prior else 0
        max_p_pool = max(sum(m.values()) for m in prior) if prior else 0
        cons_j = float(refs_data[j].get("consumo", 1.0645))
        log(f"  Pool ref {j} ({refs_data[j].get('nome','?')}): "
            f"peças=[{min_p},{max_p_pool}], "
            f"len=[{min_p*cons_j:.2f},{max_p_pool*cons_j:.2f}]m")
    min_comb = sum(
        min(sum(m.values()) for m in prior) * float(refs_data[j].get("consumo", 1.0645))
        for j, prior in enumerate(mapas_por_ref)
    ) if mapas_por_ref else 0
    log(f"  Menor comprimento combinado possível: {min_comb:.2f}m (mesa={mesa}m)")

    # ── Gera composições combinadas válidas ───────────────────────────────────
    log("Gerando composições combinadas válidas...")
    valid_combis = []
    for mapa_tuple in iproduct(*mapas_por_ref):
        total_len = sum(
            sum(mapa_tuple[j].values()) * float(refs_data[j].get("consumo", 1.0645))
            for j in range(N)
        )
        if total_len <= mesa + 0.001:
            valid_combis.append(mapa_tuple)

    log(f"Composições válidas: {len(valid_combis)}")
    if not valid_combis:
        log("Nenhuma composição combinada cabe na mesa! Verifique os consumos e o tamanho da mesa.")
        return []

    # Prioriza: mais peças totais = melhor aproveitamento da mesa
    valid_combis.sort(key=lambda mt: -sum(sum(m.values()) for m in mt))
    MAX_COMBIS = 150
    if len(valid_combis) > MAX_COMBIS:
        valid_combis = valid_combis[:MAX_COMBIS]
        log(f"  (limitadas a {MAX_COMBIS} melhores composições)")

    # ── Busca por n_mapas crescente ───────────────────────────────────────────
    melhores         = []
    budget_por_nivel = max(10, timeout_s // 6)
    primeiro_n       = 0
    cortado_timeout  = False   # True se a busca foi interrompida pelo teto de tempo

    for n_mapas in range(1, n_teto + 1):
        if time.time() - t0 > timeout_s:
            log(f"Timeout ({timeout_s}s) — usando melhor resultado encontrado")
            cortado_timeout = True
            break

        log(f"\nTestando {n_mapas} enfesto(s) combinado(s)...")
        t_nivel         = time.time()
        combos_testadas = 0
        combos_validas  = 0

        # Para n_mapas >= 3, limita pool para não estourar o tempo
        pool_sz = min(len(valid_combis), 50 if n_mapas >= 3 else MAX_COMBIS)
        pool    = valid_combis[:pool_sz]

        for combo in combinations(pool, n_mapas):
            if time.time() - t0 > timeout_s:
                cortado_timeout = True
                break
            if not melhores and time.time() - t_nivel > budget_por_nivel:
                log(f"  Sem solução em {int(time.time()-t_nivel)}s — tentando {n_mapas+1}...")
                break

            combos_testadas += 1
            valida          = True
            desvio_total    = 0
            desvio_rel_total = 0
            used_per_slot   = [0] * n_mapas

            # A camada fisica (folha) e' compartilhada por TODAS as refs que usam
            # uma cor no enfesto combinado: cortar N folhas corta N copias de CADA
            # peca de CADA referencia desenhada no mapa (e' uma unica pilha de
            # tecido, nao uma por referencia). Por isso o numero de folhas por
            # cor tem que ser resolvido UMA SO VEZ considerando a demanda de
            # todas as refs que compartilham essa cor -- nao uma vez por ref.
            todas_cores = []
            vistas_cor  = set()
            for ref in refs_data:
                for cor in ref["grade"]:
                    if cor not in vistas_cor:
                        vistas_cor.add(cor)
                        todas_cores.append(cor)
            # Maior demanda combinada primeiro (mesma logica do solver single-ref):
            # falha rapido em combos invalidas e reserva capacidade de folhas
            # pras cores maiores primeiro.
            todas_cores.sort(key=lambda c: -sum(
                sum(ref["grade"].get(c, {}).values()) for ref in refs_data
            ))

            folhas_por_cor = {}
            for cor in todas_cores:
                remaining = [max_folhas - used_per_slot[k] for k in range(n_mapas)]
                if any(r <= 0 for r in remaining):
                    valida = False
                    break

                # Dimensao composta (ref, tamanho) -- so p/ refs que tem essa cor.
                comp_tams   = []
                comp_grade  = {}
                comp_limite = {}
                comp_rows   = [dict() for _ in range(n_mapas)]
                for ri, ref in enumerate(refs_data):
                    grade_cor_ref = ref["grade"].get(cor)
                    if not grade_cor_ref:
                        continue
                    lim_cor_ref = ref.get("limites", {}).get(cor, {})
                    for t in tamanhos:
                        chave = (ri, t)
                        comp_tams.append(chave)
                        comp_grade[chave]  = grade_cor_ref.get(t, 0)
                        comp_limite[chave] = lim_cor_ref.get(t, (0, 0))
                        for k in range(n_mapas):
                            comp_rows[k][chave] = combo[k][ri].get(t, 0)

                fs = _resolver_folhas_cor(
                    comp_rows, comp_grade, comp_tams, comp_limite, remaining
                )
                if fs is None:
                    valida = False
                    break
                folhas_por_cor[cor] = fs
                for k in range(n_mapas):
                    used_per_slot[k] += fs[k]

                # Acumula desvio (por referencia+tamanho, com a folha compartilhada)
                for ri, ref in enumerate(refs_data):
                    grade_cor_ref = ref["grade"].get(cor)
                    if not grade_cor_ref:
                        continue
                    for t in tamanhos:
                        ct = sum(fs[k] * combo[k][ri].get(t, 0) for k in range(n_mapas))
                        diff = ct - grade_cor_ref.get(t, 0)
                        desvio_total     += abs(diff)
                        desvio_rel_total += abs(diff) / (grade_cor_ref.get(t, 0) or 1)

            if not valida:
                continue
            # Verificação de segurança (should never trigger com alocação capacity-aware)
            if any(used_per_slot[k] > max_folhas for k in range(n_mapas)):
                continue

            combos_validas += 1

            # Calcula comprimentos e totais
            comprimentos = [
                round(sum(
                    sum(combo[k][j].values()) * float(refs_data[j].get("consumo", 1.0645))
                    for j in range(N)
                ), 4)
                for k in range(n_mapas)
            ]
            total_pecas  = sum(sum(combo[k][j].values()) for j in range(N) for k in range(n_mapas))
            total_folhas = sum(used_per_slot)
            media_pecas  = round(total_pecas / n_mapas, 1)

            # Monta resultado por referência (folhas compartilhadas entre refs da mesma cor)
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

            melhores.append({
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
                    "desvio_relativo"         : round(desvio_rel_total, 4),
                    "media_pecas_mapa"        : media_pecas,
                },
            })

        log(f"  Testadas: {combos_testadas:,} | Válidas: {combos_validas}")

        if melhores:
            melhores.sort(key=lambda s: (
                s["n_mapas"],
                s["desvio_total"],
                -s["resumo"]["media_pecas_mapa"],
                s["resumo"]["desvio_relativo"],
            ))
            if primeiro_n == 0:
                primeiro_n = n_mapas
            n_ok = len([s for s in melhores if s["n_mapas"] == primeiro_n])
            log(f"  → Melhor: {primeiro_n} enf., desvio={melhores[0]['desvio_total']}pcs, "
                f"{melhores[0]['resumo']['media_pecas_mapa']}pcs/mapa")
            if n_ok >= num_opcoes and n_mapas >= primeiro_n + 1:
                log(f"\nOK {num_opcoes} opções com {primeiro_n} enfesto(s) combinado(s). Parando.")
                break

    # Sinaliza ao chamador se a busca convergiu (nao foi cortada pelo timeout).
    # Mesmo padrao do solver.py -- usado por main.py para so cachear/aprender
    # tempos de buscas COMPLETAS (evita vies na ETA).
    if resume_out is not None:
        resume_out["convergiu"] = not cortado_timeout

    if not melhores:
        return []

    melhores.sort(key=lambda s: (
        s["n_mapas"],
        s["desvio_total"],
        -s["resumo"]["media_pecas_mapa"],
        s["resumo"]["desvio_relativo"],
    ))
    return melhores[:num_opcoes]
