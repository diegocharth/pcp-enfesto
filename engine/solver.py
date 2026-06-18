"""
PCP Enfestos — Solver v2.3
Premissa primária: menor número de enfestos (operacional).
Premissas secundárias: menor desvio da grade, maior peças/mapa.
Regra hi=0 aplicada via check_viavel — sem mapa estratégico forçado.
"""

import time
from itertools import combinations
from engine.tolerancia import check_viavel, custo_desvio, desvio_absoluto_total
from engine.mapas import gerar_mapas, filtrar_mapas_relevantes, priorizar_mapas, max_pecas_por_mapa


def _resolver_folhas_cor(mapas_sel, grade_cor, tamanhos, limites_cor, max_f=120):
    """
    Acha folhas[k] >= 0 para N mapas tal que o cortado satisfaz os limites.
    Retorna lista de folhas ou None.
    Entre múltiplas soluções válidas, prefere a de menor desvio total.
    """
    N = len(mapas_sel)
    doms = []
    for m in mapas_sel:
        vals = sorted([(m.get(t, 0), t) for t in tamanhos], reverse=True)
        doms.append(vals[0][1] if vals[0][0] > 0 else tamanhos[0])

    grade_max = max((grade_cor.get(t, 0) for t in tamanhos), default=0)
    if grade_max == 0:
        return [0] * N

    def cortado(fs):
        return {t: sum(fs[k] * mapas_sel[k].get(t, 0) for k in range(N)) for t in tamanhos}

    def desvio(fs):
        ct = cortado(fs)
        return sum(abs(ct[t] - grade_cor.get(t, 0)) for t in tamanhos)

    melhores = None
    melhor_dev = float('inf')

    if N == 1:
        M = mapas_sel[0]; dv = M.get(doms[0], 0)
        if dv == 0: return None
        for f in range(0, min(max_f, int(grade_max / max(dv, 1)) + 6) + 1):
            ct = {t: f * M.get(t, 0) for t in tamanhos}
            if check_viavel(ct, grade_cor, limites_cor):
                d = desvio([f])
                if d < melhor_dev:
                    melhor_dev = d; melhores = [f]
                    if d == 0: break
        return melhores

    if N == 2:
        M0, M1 = mapas_sel; d0 = M0.get(doms[0], 0); d1 = M1.get(doms[1], 0)
        if d0 == 0: return None
        for f0 in range(0, min(max_f, int(grade_max / max(d0, 1)) + 5) + 1):
            res0 = {t: grade_cor.get(t, 0) - f0 * M0.get(t, 0) for t in tamanhos}
            if d1 > 0:
                f1e = max(0, round(res0.get(doms[1], 0) / d1))
                r1 = range(max(0, f1e - 4), min(max_f, f1e + 5))
            else:
                r1 = range(0, 6)
            for f1 in r1:
                ct = cortado([f0, f1])
                if check_viavel(ct, grade_cor, limites_cor):
                    d = desvio([f0, f1])
                    if d < melhor_dev:
                        melhor_dev = d; melhores = [f0, f1]
                        if d == 0: break
            if melhor_dev == 0: break
        return melhores

    if N == 3:
        M0, M1, M2 = mapas_sel
        d0 = M0.get(doms[0], 0); d1 = M1.get(doms[1], 0); d2 = M2.get(doms[2], 0)
        if d0 == 0: return None
        for f0 in range(0, min(max_f, int(grade_max / max(d0, 1)) + 4) + 1):
            r0 = {t: grade_cor.get(t, 0) - f0 * M0.get(t, 0) for t in tamanhos}
            if d1 > 0:
                f1e = max(0, round(r0.get(doms[1], 0) / d1))
                r1 = range(max(0, f1e - 3), min(max_f, f1e + 4))
            else: r1 = range(0, 5)
            for f1 in r1:
                r1v = {t: r0[t] - f1 * M1.get(t, 0) for t in tamanhos}
                if d2 > 0:
                    f2e = max(0, round(r1v.get(doms[2], 0) / d2))
                    r2 = range(max(0, f2e - 3), min(max_f, f2e + 4))
                else: r2 = range(0, 5)
                for f2 in r2:
                    ct = cortado([f0, f1, f2])
                    if check_viavel(ct, grade_cor, limites_cor):
                        d = desvio([f0, f1, f2])
                        if d < melhor_dev:
                            melhor_dev = d; melhores = [f0, f1, f2]
                            if d == 0: break
                if melhor_dev == 0: break
            if melhor_dev == 0: break
        return melhores

    if N == 4:
        M0, M1, M2, M3 = mapas_sel
        ds = [M.get(doms[i], 0) for i, M in enumerate(mapas_sel)]
        if ds[0] == 0: return None
        for f0 in range(0, min(max_f, int(grade_max / max(ds[0], 1)) + 4) + 1):
            r0 = {t: grade_cor.get(t, 0) - f0 * M0.get(t, 0) for t in tamanhos}
            if ds[1] > 0:
                f1e = max(0, round(r0.get(doms[1], 0) / ds[1]))
                r1 = range(max(0, f1e - 2), min(max_f, f1e + 3))
            else: r1 = range(0, 4)
            for f1 in r1:
                r1v = {t: r0[t] - f1 * M1.get(t, 0) for t in tamanhos}
                if ds[2] > 0:
                    f2e = max(0, round(r1v.get(doms[2], 0) / ds[2]))
                    r2 = range(max(0, f2e - 2), min(max_f, f2e + 3))
                else: r2 = range(0, 4)
                for f2 in r2:
                    r2v = {t: r1v[t] - f2 * M2.get(t, 0) for t in tamanhos}
                    if ds[3] > 0:
                        f3e = max(0, round(r2v.get(doms[3], 0) / ds[3]))
                        r3 = range(max(0, f3e - 2), min(max_f, f3e + 3))
                    else: r3 = range(0, 4)
                    for f3 in r3:
                        ct = cortado([f0, f1, f2, f3])
                        if check_viavel(ct, grade_cor, limites_cor):
                            d = desvio([f0, f1, f2, f3])
                            if d < melhor_dev:
                                melhor_dev = d; melhores = [f0, f1, f2, f3]
                                if d == 0: break
                    if melhor_dev == 0: break
                if melhor_dev == 0: break
            if melhor_dev == 0: break
        return melhores

    return None


def _calcular_cortado(mapas_sel, folhas_dict, grade, tamanhos):
    """Calcula o cortado total por cor."""
    result = {}
    for cor in grade:
        result[cor] = {
            t: sum(folhas_dict[cor][k] * mapas_sel[k].get(t, 0)
                   for k in range(len(mapas_sel)))
            for t in tamanhos
        }
    return result


def _score_solucao(mapas_sel, folhas_dict, grade, tamanhos, config):
    """
    Score de uma solução. Hierarquia:
    1. Menor desvio absoluto total (premissa primária — peso 0.65)
    2. Maior média de peças por mapa (peso 0.25)
    3. Menor nº de enfestos (peso 0.10)
    """
    # 1. Desvio total — menor é melhor
    cortado = _calcular_cortado(mapas_sel, folhas_dict, grade, tamanhos)
    dev_abs = desvio_absoluto_total(cortado, grade, tamanhos)
    # Normalização: 0 dev = score 1.0, cada unidade de desvio reduz o score
    # Referência: grade_total como escala
    grade_total_pecas = sum(grade[c].get(t, 0) for c in grade for t in tamanhos)
    score_desvio = 1.0 / (1.0 + dev_abs / max(grade_total_pecas * 0.05, 1))

    # 2. Eficiência de encaixe — maior peças/mapa é melhor
    pecas_por_mapa = [sum(m.values()) for m in mapas_sel]
    max_possivel = max_pecas_por_mapa(
        float(config.get("mesa_comprimento_m", 10.0)),
        float(config.get("consumo_peca_m", 1.0645))
    )
    media_pecas = sum(pecas_por_mapa) / len(mapas_sel)
    score_enc = media_pecas / max(max_possivel, 1)

    # 3. Eficiência operacional — menos enfestos é melhor
    score_op = 1.0 / len(mapas_sel)

    return 0.65 * score_desvio + 0.25 * score_enc + 0.10 * score_op


def resolver(grade, tamanhos, limites, config, callback_progresso=None, timeout_s=120):
    """
    Resolve o plano de enfestos.
    Premissa 1: menor numero de enfestos.
    Premissa 2: menor desvio da grade.
    Premissa 3: maior pecas/mapa.
    hi=0 para um tamanho e respeitado via check_viavel (sem mapa estrategico forcado).
    """
    def log(msg):
        if callback_progresso: callback_progresso(msg)

    consumo    = float(config.get("consumo_peca_m", 1.0645))
    mesa       = float(config.get("mesa_comprimento_m", 10.0))
    max_folhas = int(config.get("limite_folhas_padrao", 70))
    num_opcoes = int(config.get("num_opcoes_saida", 2))
    max_pecas  = max_pecas_por_mapa(mesa, consumo)

    log(f"Mesa: {mesa}m | Consumo: {consumo}m/pca | Max pecas/mapa: {max_pecas}")
    log(f"Limite folhas/enfesto: {max_folhas}")
    log("Premissa: menor n.enfestos, depois menor desvio")

    grade_total = {t: sum(grade[c].get(t, 0) for c in grade) for t in tamanhos}

    log("Gerando mapas candidatos...")
    todos  = gerar_mapas(tamanhos, max_pecas)
    rel    = filtrar_mapas_relevantes(todos, grade_total, tamanhos)
    prior  = priorizar_mapas(rel, grade_total, tamanhos, top_n=400)
    log(f"Mapas candidatos: {len(prior)} (de {len(todos)} totais)")

    melhores = []
    cores    = list(grade.keys())
    t_inicio = time.time()
    primeiro_n_com_solucao = 0

    # Budget por nivel: gasta no maximo 1/4 do timeout por N sem solucao.
    # Se N=3 nao acha nada em 25% do tempo, passa para N=4 automaticamente.
    budget_por_nivel = max(15, timeout_s // 4)

    for n_mapas in range(1, 8):
        if time.time() - t_inicio > timeout_s:
            log(f"Tempo esgotado ({timeout_s}s) — usando melhor resultado encontrado")
            break

        log(f"\nTestando {n_mapas} mapa(s)...")
        lim_combo = {1:400, 2:300, 3:200, 4:100, 5:60, 6:40, 7:30}
        candidatos = prior[:lim_combo.get(n_mapas, 30)]

        combos_testadas = 0
        combos_validas  = 0
        t_nivel = time.time()

        combos_iter = combinations(candidatos, n_mapas)

        for combo in combos_iter:
            if time.time() - t_inicio > timeout_s: break
            # Se nao achou nada neste N apos o budget, avanca para N+1
            if not melhores and time.time() - t_nivel > budget_por_nivel:
                log(f"  Sem solucao em {int(time.time()-t_nivel)}s — tentando {n_mapas+1} mapa(s)...")
                break

            combos_testadas += 1
            folhas_sol = {}
            valida = True

            # Resolver folhas por cor
            for cor in cores:
                fs = _resolver_folhas_cor(
                    list(combo), grade[cor], tamanhos, limites[cor], max_folhas
                )
                if fs is None:
                    valida = False; break
                folhas_sol[cor] = fs

            if not valida: continue

            # Verificar limite de folhas POR ENFESTO (soma de todas as cores)
            for k in range(n_mapas):
                if sum(folhas_sol[c][k] for c in cores) > max_folhas:
                    valida = False; break

            if not valida: continue

            combos_validas += 1
            sc = _score_solucao(list(combo), folhas_sol, grade, tamanhos, config)

            # Calcular desvio total para exibição
            cortado = _calcular_cortado(list(combo), folhas_sol, grade, tamanhos)
            dev_total = desvio_absoluto_total(cortado, grade, tamanhos)
            pecas_por_mapa = [sum(m.values()) for m in combo]
            total_folhas   = sum(sum(folhas_sol[c]) for c in cores)

            melhores.append({
                "n_mapas": n_mapas,
                "mapas"  : [dict(m) for m in combo],
                "folhas" : folhas_sol,
                "score"  : sc,
                "resumo" : {
                    "n_mapas"           : n_mapas,
                    "total_folhas"      : total_folhas,
                    "pecas_por_mapa"    : pecas_por_mapa,
                    "media_pecas_mapa"  : round(sum(pecas_por_mapa) / n_mapas, 1),
                    "comprimento_por_mapa": [round(p * consumo, 4) for p in pecas_por_mapa],
                    "comprimento_total"   : round(sum(pecas_por_mapa) * consumo, 4),
                    "desvio_total"        : dev_total,
                    "max_folhas_enfesto"  : max_folhas,
                    "consumo_peca"        : consumo,
                }
            })

        log(f"  Combinações testadas: {combos_testadas:,} | Válidas: {combos_validas}")

        if melhores:
            melhores.sort(key=lambda s: (
                s["n_mapas"],                        # MENOS enfestos (primário)
                s["resumo"]["desvio_total"],          # menor desvio
                -s["resumo"]["media_pecas_mapa"],     # mais pecs/mapa
            ))
            distintas = _filtrar_distintas(melhores, num_opcoes + 3)
            melhor_dev = distintas[0]["resumo"]["desvio_total"]
            log(f"  -> Melhor: {n_mapas} mapas, desvio={melhor_dev}pcs, {distintas[0]['resumo']['media_pecas_mapa']}pcs/mapa")

            if primeiro_n_com_solucao == 0:
                primeiro_n_com_solucao = n_mapas

            # Parar se:
            # 1. Desvio zero com o melhor N encontrado — perfeito
            # 2. OU já temos opcoes suficientes no N mais baixo encontrado
            opcoes_no_melhor_n = [s for s in distintas if s["n_mapas"] == primeiro_n_com_solucao]
            if melhor_dev == 0 and len(opcoes_no_melhor_n) >= num_opcoes:
                log(f"\nOK Desvio zero com {n_mapas} mapa(s). Parando.")
                return distintas[:num_opcoes]

            if len(opcoes_no_melhor_n) >= num_opcoes and n_mapas >= primeiro_n_com_solucao + 1:
                log(f"\nOK {num_opcoes} opcoes com {primeiro_n_com_solucao} mapa(s). Desvio={melhor_dev}pcs.")
                return distintas[:num_opcoes]

            if n_mapas >= primeiro_n_com_solucao + 2 and len(distintas) >= num_opcoes:
                log(f"\nOK Explorado N={primeiro_n_com_solucao} a N={n_mapas}. Desvio={melhor_dev}pcs.")
                return distintas[:num_opcoes]

    melhores.sort(key=lambda s: (
        s["n_mapas"],
        s["resumo"]["desvio_total"],
        -s["resumo"]["media_pecas_mapa"],
    ))
    result = _filtrar_distintas(melhores, num_opcoes)
    if result:
        log(f"\nDesvio da melhor solucao: {result[0]['resumo']['desvio_total']} pecas")
        log(f"Media pecas/mapa: {result[0]['resumo']['media_pecas_mapa']}")
    return result[:num_opcoes]


def _filtrar_distintas(solucoes, top_n):
    vistas = set()
    result = []
    for s in solucoes:
        chave = tuple(sorted(tuple(sorted(m.items())) for m in s["mapas"]))
        if chave not in vistas:
            vistas.add(chave); result.append(s)
        if len(result) >= top_n: break
    return result



