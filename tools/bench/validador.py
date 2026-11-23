"""
Bancada de comparacao -- validador independente das restricoes duras.

Confere uma solucao single-ref SEM usar nenhum codigo do solver: recalcula o
cortado a partir de mapas x folhas e verifica mesa, limite de folhas por
enfesto e a tolerancia de cada celula cor x tamanho. Qualquer solucao que um
motor devolva tem que passar aqui, senao o motor esta errado.
"""


def validar(sol, grade, tamanhos, limites, config):
    """Lista de erros (vazia = solucao valida)."""
    erros = []
    mesa = float(config.get("mesa_comprimento_m", 10.0))
    consumo = float(config.get("consumo_peca_m", 1.0645))
    max_folhas = int(config.get("limite_folhas_padrao", 70))
    mapas = sol.get("mapas") or []
    folhas = sol.get("folhas") or {}
    n = len(mapas)
    if n < 1:
        return ["solucao sem mapas"]
    if sol.get("n_mapas") != n:
        erros.append(f"n_mapas={sol.get('n_mapas')} difere do numero de mapas ({n})")

    for e, m in enumerate(mapas):
        pecas = sum(int(v) for v in m.values())
        if pecas < 1:
            erros.append(f"enfesto {e + 1}: mapa vazio")
        if any(int(v) < 0 for v in m.values()):
            erros.append(f"enfesto {e + 1}: quantidade negativa no mapa")
        if pecas * consumo > mesa + 1e-9:
            erros.append(f"enfesto {e + 1}: {pecas} pecas x {consumo}m passa da mesa de {mesa}m")
        if any(t not in tamanhos for t in m):
            erros.append(f"enfesto {e + 1}: tamanho desconhecido no mapa")

    for cor in grade:
        fs = folhas.get(cor)
        if fs is None or len(fs) != n:
            erros.append(f"{cor}: folhas ausentes ou com tamanho diferente de {n}")
    if erros:
        return erros

    for e in range(n):
        total = sum(int(folhas[cor][e]) for cor in grade)
        if total > max_folhas:
            erros.append(f"enfesto {e + 1}: {total} folhas passa do limite de {max_folhas}")
        if any(int(folhas[cor][e]) < 0 for cor in grade):
            erros.append(f"enfesto {e + 1}: folhas negativas")

    desvio = 0
    for cor in grade:
        for t in tamanhos:
            cortado = sum(int(folhas[cor][e]) * int(mapas[e].get(t, 0)) for e in range(n))
            pedido = int(grade[cor].get(t, 0))
            lo, hi = limites[cor][t]
            dif = cortado - pedido
            desvio += abs(dif)
            if dif < lo or dif > hi:
                erros.append(f"{cor}/{t}: cortado {cortado} para pedido {pedido} "
                             f"(desvio {dif:+d} fora de [{lo:+d}, {hi:+d}])")
    informado = (sol.get("resumo") or {}).get("desvio_total")
    if informado is not None and informado != desvio:
        erros.append(f"desvio_total informado {informado} difere do recalculado {desvio}")
    return erros


def chave_ranking(sol):
    """Mesma ordem do sistema: menos enfestos, menor desvio, mais pecas/mapa."""
    r = sol["resumo"]
    pecas = sum(sum(int(v) for v in m.values()) for m in sol["mapas"])
    return (r["n_mapas"], r["desvio_total"], -pecas)


def validar_multiref(sol, tamanhos, config):
    """Erros de uma solucao do solver multi-ref (vazia = valida). Confere, sem
    usar codigo do solver: comprimento de cada enfesto na mesa (soma das pecas x
    consumo de cada referencia), limite de folhas por enfesto, FOLHA COMPARTILHADA
    (mesma cor, mesmo enfesto = mesmo numero de folhas em todas as referencias)
    e a tolerancia de cada referencia x cor x tamanho."""
    erros = []
    mesa = float(config.get("mesa_comprimento_m", 10.0))
    max_folhas = int(config.get("limite_folhas_padrao", 70))
    refs = sol.get("refs_sol") or []
    n = sol.get("n_mapas") or 0
    if not refs or n < 1:
        return ["solucao sem referencias ou sem enfestos"]
    folhas_cor = {}
    for r in refs:
        if len(r["mapas"]) != n:
            erros.append(f"{r['nome']}: {len(r['mapas'])} mapas para {n} enfestos")
            return erros
        for cor, fs in r["folhas"].items():
            if len(fs) != n:
                erros.append(f"{r['nome']}/{cor}: folhas com tamanho {len(fs)}")
                return erros
            if cor in folhas_cor and list(folhas_cor[cor]) != list(fs):
                erros.append(f"{cor}: folhas diferentes entre referencias no mesmo enfesto "
                             f"({folhas_cor[cor]} x {fs})")
            folhas_cor.setdefault(cor, list(fs))
    for k in range(n):
        comp = sum(sum(int(v) for v in r["mapas"][k].values()) * float(r["consumo"]) for r in refs)
        if comp > mesa + 1e-6:
            erros.append(f"enfesto {k + 1}: {comp:.3f}m passa da mesa de {mesa}m")
        tot = sum(int(fs[k]) for fs in folhas_cor.values())
        if tot > max_folhas:
            erros.append(f"enfesto {k + 1}: {tot} folhas passa do limite de {max_folhas}")
        if all(sum(r["mapas"][k].values()) == 0 for r in refs):
            erros.append(f"enfesto {k + 1}: vazio")
    desvio = 0
    for r in refs:
        for cor, gc in r["grade"].items():
            fs = folhas_cor.get(cor, [0] * n)
            for t in tamanhos:
                cortado = sum(int(fs[k]) * int(r["mapas"][k].get(t, 0)) for k in range(n))
                pedido = int(gc.get(t, 0))
                lo, hi = r["limites"][cor][t]
                d = cortado - pedido
                desvio += abs(d)
                if d < lo or d > hi:
                    erros.append(f"{r['nome']}/{cor}/{t}: cortado {cortado} para pedido {pedido} "
                                 f"(desvio {d:+d} fora de [{lo:+d}, {hi:+d}])")
    if sol.get("desvio_total") is not None and sol["desvio_total"] != desvio:
        erros.append(f"desvio_total informado {sol['desvio_total']} difere do recalculado {desvio}")
    return erros
