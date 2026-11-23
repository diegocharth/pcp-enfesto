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
