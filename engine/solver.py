"""
PCP Enfestos — Solver v2.3
Premissa primária: menor número de enfestos (operacional).
Premissas secundárias: menor desvio da grade, maior peças/mapa.
Regra hi=0 aplicada via check_viavel — sem mapa estratégico forçado.
"""

import time
from itertools import combinations, islice
from engine.tolerancia import check_viavel, custo_desvio, desvio_absoluto_total
from engine.mapas import gerar_mapas, filtrar_mapas_relevantes, priorizar_mapas, max_pecas_por_mapa

try:
    import numpy as _np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False


def _resolver_folhas_cor(mapas_sel, grade_cor, tamanhos, limites_cor, max_f=120, A_pinv=None,
                         W=6, sweeps=10):
    """
    Acha folhas[k] >= 0 para N mapas satisfazendo os limites (cortado dentro da tolerância),
    minimizando o desvio total. Retorna a lista de folhas ou None se nenhum ponto viável.

    Estratégia: busca local por coordenada (coordinate descent) partindo de 1-2 sementes
    (centro de mínimos quadrados via numpy + estimativa sequencial por resíduo). Escala
    linearmente com N — ao contrário do grid exponencial, resolve N>=5 de fato.

    max_f: int (limite uniforme) ou list[int] (limite por slot restante).
    A_pinv: pseudo-inversa precomputada por combo (evita recomputar por cor).
    """
    N = len(mapas_sel)
    grade_max = max((grade_cor.get(t, 0) for t in tamanhos), default=0)
    if grade_max == 0:
        return [0] * N

    # Normaliza max_f para lista por slot
    if isinstance(max_f, (list, tuple)):
        caps = [max(0, int(m)) for m in max_f]
    else:
        caps = [int(max_f)] * N

    # Pré-extrai linhas dos mapas e limites como tuplas indexadas por tamanho (rápido)
    g    = [grade_cor.get(t, 0) for t in tamanhos]
    rows = [[m.get(t, 0) for t in tamanhos] for m in mapas_sel]
    lims = [limites_cor.get(t, (0, 0)) for t in tamanhos]
    T    = len(tamanhos)

    def eval_fs(fs):
        """Retorna (desvio_total, desvio_relativo, viavel)."""
        d = 0; d_rel = 0.0; ok = True
        for ti in range(T):
            ct = 0
            for k in range(N):
                ct += fs[k] * rows[k][ti]
            diff = ct - g[ti]
            ad = diff if diff >= 0 else -diff
            d += ad
            d_rel += ad / (g[ti] if g[ti] > 0 else 1)
            lo, hi = lims[ti]
            if diff < lo or diff > hi:
                ok = False
        return d, d_rel, ok

    # N=1: enumeração completa — rápido e exato
    if N == 1:
        r0 = rows[0]
        d_max = max(r0) if r0 else 0
        if d_max == 0:
            return None
        best_fs = None; best_dev = float('inf'); best_drel = float('inf')
        for f in range(0, min(caps[0], int(grade_max / max(d_max, 1)) + 6) + 1):
            d, d_rel, ok = eval_fs([f])
            if ok and (d < best_dev or (d == best_dev and d_rel < best_drel)):
                best_dev = d; best_drel = d_rel; best_fs = [f]
                if d == 0:
                    return best_fs
        return best_fs

    # ── Sementes ────────────────────────────────────────────────────────────
    starts = []
    if _HAS_NP:
        try:
            b = _np.array(g, dtype=float)
            if A_pinv is not None:
                x_float = A_pinv @ b
            else:
                A = _np.array(rows, dtype=float).T  # (T x N)
                x_float, _, _, _ = _np.linalg.lstsq(A, b, rcond=None)
            starts.append(_np.clip(_np.round(x_float), 0,
                                   _np.array(caps, dtype=float)).astype(int).tolist())
        except Exception:
            pass
    # Estimativa sequencial por resíduo (semente independente; também serve sem numpy)
    doms = [max(range(T), key=lambda ti, r=r: r[ti]) for r in rows]
    rem  = list(g)
    seq  = []
    for i in range(N):
        di = rows[i][doms[i]]
        fi = max(0, round(rem[doms[i]] / di)) if di > 0 else 0
        fi = min(fi, caps[i])
        seq.append(fi)
        for ti in range(T):
            rem[ti] -= fi * rows[i][ti]
    starts.append(seq)

    # ── Coordinate descent a partir de cada semente ─────────────────────────
    best_fs = None; best_feas_dev = float('inf'); best_feas_drel = float('inf')
    for s in starts:
        fs = list(s)
        cur_dev, cur_drel, cur_ok = eval_fs(fs)
        if cur_ok and (cur_dev < best_feas_dev or (cur_dev == best_feas_dev and cur_drel < best_feas_drel)):
            best_feas_dev = cur_dev; best_feas_drel = cur_drel; best_fs = list(fs)
        for _ in range(sweeps):
            moved = False
            for i in range(N):
                orig = fs[i]
                lo = max(0, orig - W); hi = min(caps[i], orig + W)
                best_v = orig
                base_dev, _bd, _ = eval_fs(fs)
                best_local_dev = base_dev
                for v in range(lo, hi + 1):
                    if v == orig:
                        continue
                    fs[i] = v
                    d, d_rel, ok = eval_fs(fs)
                    if ok and (d < best_feas_dev or (d == best_feas_dev and d_rel < best_feas_drel)):
                        best_feas_dev = d; best_feas_drel = d_rel; best_fs = list(fs)
                    if d < best_local_dev:
                        best_local_dev = d; best_v = v
                fs[i] = best_v
                if best_v != orig:
                    moved = True
            if not moved:
                break
        if best_feas_dev == 0:
            break
    return best_fs


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


def resolver(grade, tamanhos, limites, config, callback_progresso=None, timeout_s=120,
             min_n_mapas=1, skip_combos=0):
    """
    Resolve o plano de enfestos.
    min_n_mapas: pula níveis já completamente explorados (para retomada).
    skip_combos: pula as primeiras N combinações do nível min_n_mapas (retomada exata
                 de onde o timeout anterior parou — só se aplica ao primeiro nível).
    Sem limite de n_mapas — o timeout controla a parada.
    """
    from math import comb as _comb

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

    # Ordena cores do maior para o menor grade total:
    # (1) falha rápido em combos inválidas e (2) aloca capacidade de folhas para as cores maiores primeiro
    cores = sorted(grade.keys(), key=lambda c: sum(grade[c].get(t, 0) for t in tamanhos), reverse=True)

    melhores = []
    t_inicio = time.time()
    primeiro_n_com_solucao = 0
    niveis_esgotados = []  # níveis 100% explorados sem solução
    resume_n    = None     # nível onde o timeout interrompeu (para retomada exata)
    resume_skip = 0        # nº de combinações já testadas nesse nível

    # Tamanho máximo do pool por n_mapas — balanceia cobertura vs tempo
    lim_combo = {1: 125, 2: 125, 3: 80, 4: 50, 5: 30, 6: 20, 7: 15}

    # Limite de folhas mínimo teórico por cor (piso — baseado no grade total / max_pecas)
    folhas_min_por_cor = {
        c: -(-sum(grade[c].get(t, 0) for t in tamanhos) // max(1, max_pecas))
        for c in cores
    }
    total_folhas_min = sum(folhas_min_por_cor.values())

    for n_mapas in range(min_n_mapas, 50):
        if time.time() - t_inicio > timeout_s:
            log(f"Tempo esgotado ({timeout_s}s) — usando melhor resultado encontrado")
            break

        # Pré-check de capacidade: pula nível se matematicamente inviável
        capacidade = n_mapas * max_folhas
        if total_folhas_min > capacidade:
            log(f"\nN={n_mapas}: inviável (mín {total_folhas_min} folhas necessárias, cap {capacidade}). Pulando.")
            niveis_esgotados.append(n_mapas)
            continue

        candidatos = prior[:min(len(prior), lim_combo.get(n_mapas, 10))]
        if len(candidatos) < n_mapas:
            log(f"  Candidatos insuficientes para {n_mapas} mapas. Parando.")
            break

        n_cand = len(candidatos)
        total_combos = _comb(n_cand, n_mapas)

        # Offset de retomada: só no primeiro nível desta execução
        offset = skip_combos if (n_mapas == min_n_mapas and skip_combos > 0) else 0
        if offset >= total_combos and total_combos > 0:
            # Nível já foi totalmente testado numa execução anterior
            log(f"\nN={n_mapas}: já testado completamente ({offset:,}). Avançando.")
            niveis_esgotados.append(n_mapas)
            continue

        log(f"\nTestando {n_mapas} mapa(s)... ({total_combos:,} combinações de {n_cand} candidatos)")

        combos_iter = combinations(candidatos, n_mapas)
        if offset > 0:
            log(f"  ↻ Retomando de {offset:,}/{total_combos:,} ({offset/total_combos*100:.1f}%) já testadas")
            combos_iter = islice(combos_iter, offset, None)

        combos_testadas = offset
        combos_validas  = 0
        t_nivel         = time.time()
        fully_exhausted = True

        for combo in combos_iter:
            if time.time() - t_inicio > timeout_s:
                fully_exhausted = False
                break

            combos_testadas += 1

            # Progresso em tempo real a cada 25K combinações
            if combos_testadas % 25000 == 0:
                elapsed = max(time.time() - t_nivel, 0.1)
                feitas  = combos_testadas - offset  # combos testadas NESTA execução
                rate    = feitas / elapsed
                pct     = combos_testadas / total_combos * 100
                eta     = (total_combos - combos_testadas) / max(rate, 1)
                log(f"  ↳ {combos_testadas:,}/{total_combos:,} ({pct:.1f}%) | {rate:.0f} comb/s | ETA {eta:.0f}s")

            folhas_sol = {}
            valida = True
            # Rastreia folhas usadas por slot (soma de todas as cores processadas até aqui)
            used_per_slot = [0] * n_mapas

            # Precomputa A e A_pinv uma vez por combo — reusado para todas as cores
            _A_pinv = None
            if _HAS_NP and n_mapas >= 2:
                try:
                    _A = _np.array([[m.get(t, 0) for m in combo] for t in tamanhos], dtype=float)
                    _A_pinv = _np.linalg.pinv(_A)
                except Exception:
                    _A_pinv = None

            for cor in cores:
                # Capacidade restante por slot para esta cor
                remaining = [max_folhas - used_per_slot[k] for k in range(n_mapas)]
                if any(r <= 0 for r in remaining):
                    valida = False; break
                fs = _resolver_folhas_cor(
                    list(combo), grade[cor], tamanhos, limites[cor], remaining,
                    A_pinv=_A_pinv
                )
                if fs is None:
                    valida = False; break
                folhas_sol[cor] = fs
                for k in range(n_mapas):
                    used_per_slot[k] += fs[k]

            if not valida: continue
            # Verificação de segurança (should never trigger with capacity-aware allocation)
            if any(used_per_slot[k] > max_folhas for k in range(n_mapas)):
                continue

            combos_validas += 1
            sc = _score_solucao(list(combo), folhas_sol, grade, tamanhos, config)

            cortado_tot = _calcular_cortado(list(combo), folhas_sol, grade, tamanhos)
            dev_total   = desvio_absoluto_total(cortado_tot, grade, tamanhos)
            dev_rel = round(sum(
                abs(cortado_tot[c].get(t, 0) - grade[c].get(t, 0)) / (grade[c].get(t, 0) or 1)
                for c in grade for t in tamanhos
            ), 4)
            pecas_por_mapa = [sum(m.values()) for m in combo]
            total_folhas   = sum(sum(folhas_sol[c]) for c in cores)

            melhores.append({
                "n_mapas": n_mapas,
                "mapas"  : [dict(m) for m in combo],
                "folhas" : folhas_sol,
                "score"  : sc,
                "resumo" : {
                    "n_mapas"             : n_mapas,
                    "total_folhas"        : total_folhas,
                    "pecas_por_mapa"      : pecas_por_mapa,
                    "media_pecas_mapa"    : round(sum(pecas_por_mapa) / n_mapas, 1),
                    "comprimento_por_mapa": [round(p * consumo, 4) for p in pecas_por_mapa],
                    "comprimento_total"   : round(sum(pecas_por_mapa) * consumo, 4),
                    "desvio_total"        : dev_total,
                    "desvio_relativo"     : dev_rel,
                    "max_folhas_enfesto"  : max_folhas,
                    "consumo_peca"        : consumo,
                }
            })

        status = "completo ✓" if fully_exhausted else f"timeout ({int(time.time()-t_nivel)}s)"
        log(f"  Combinações testadas: {combos_testadas:,} | Válidas: {combos_validas} | {status}")

        if fully_exhausted and combos_validas == 0:
            niveis_esgotados.append(n_mapas)

        if melhores:
            melhores.sort(key=lambda s: (
                s["n_mapas"],
                s["resumo"]["desvio_total"],
                -s["resumo"]["media_pecas_mapa"],
                s["resumo"]["desvio_relativo"],
            ))
            distintas = _filtrar_distintas(melhores, num_opcoes + 3)
            melhor_dev = distintas[0]["resumo"]["desvio_total"]
            log(f"  → Melhor: {n_mapas} mapas, desvio={melhor_dev}pcs, {distintas[0]['resumo']['media_pecas_mapa']}pcs/mapa")

            if primeiro_n_com_solucao == 0:
                primeiro_n_com_solucao = n_mapas

            opcoes_no_melhor_n = [s for s in distintas if s["n_mapas"] == primeiro_n_com_solucao]
            if melhor_dev == 0 and len(opcoes_no_melhor_n) >= num_opcoes:
                log(f"\nOK Desvio zero com {n_mapas} mapa(s). Parando.")
                return distintas[:num_opcoes]
            if len(opcoes_no_melhor_n) >= num_opcoes and n_mapas >= primeiro_n_com_solucao + 1:
                log(f"\nOK {num_opcoes} opções com {primeiro_n_com_solucao} mapa(s). Desvio={melhor_dev}pcs.")
                return distintas[:num_opcoes]
            if n_mapas >= primeiro_n_com_solucao + 2 and len(distintas) >= num_opcoes:
                log(f"\nOK Explorado N={primeiro_n_com_solucao}..{n_mapas}. Desvio={melhor_dev}pcs.")
                return distintas[:num_opcoes]

        if not fully_exhausted:
            # Timeout no meio deste nível — guarda ponto exato para retomada
            resume_n    = n_mapas
            resume_skip = combos_testadas
            break

    melhores.sort(key=lambda s: (
        s["n_mapas"], s["resumo"]["desvio_total"], -s["resumo"]["media_pecas_mapa"],
        s["resumo"]["desvio_relativo"],
    ))
    result = _filtrar_distintas(melhores, num_opcoes)

    # Determina ponto exato de retomada para o botão "Continuar"
    if resume_n is not None:
        # Parou no meio de um nível por timeout — retoma exatamente daí
        proximo_n   = resume_n
        skip_proximo = resume_skip
    elif niveis_esgotados:
        # Todos os níveis testados foram completamente esgotados — vai para o próximo
        proximo_n   = max(niveis_esgotados) + 1
        skip_proximo = 0
    else:
        # Nenhum nível testado parou por timeout nem esgotou: caminho de "candidatos
        # insuficientes" (nível atual nunca foi testado). NÃO avança além dele.
        proximo_n   = n_mapas if 'n_mapas' in dir() else min_n_mapas
        skip_proximo = 0

    if result:
        log(f"\nDesvio da melhor solução: {result[0]['resumo']['desvio_total']} peças")
    elif resume_n is not None:
        log(f"\nTimeout no nível {resume_n} ({resume_skip:,} combinações testadas).")
        log(f"Use 'Continuar' para retomar de {resume_skip:,} combinações no nível {resume_n}.")
    elif niveis_esgotados:
        log(f"\nNíveis completamente explorados (sem solução): {niveis_esgotados}")
        log(f"Use 'Continuar' para buscar com {proximo_n}+ mapas.")

    # Salva info para main.py retornar ao frontend
    resolver._niveis_esgotados   = niveis_esgotados
    resolver._ultimo_n_explorado = n_mapas if 'n_mapas' in dir() else min_n_mapas
    resolver._proximo_n          = proximo_n
    resolver._skip_combos        = skip_proximo

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



