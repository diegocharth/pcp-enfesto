"""
PCP Enfestos -- Multi-ref: folhas exatas de um enfesto combinado
================================================================

Dado um combo (por enfesto, um mapa de cada referencia), escolhe as folhas de
cada cor -- a folha e COMPARTILHADA pelas referencias do enfesto -- com o menor
desvio total, repartindo o limite de folhas de cada enfesto entre as cores de
forma EXATA. Reaproveita o nucleo do motor exato single-ref
(engine/exato_folhas.py: _pontos_cor + _conjunto), com dimensoes compostas
(referencia, tamanho) no lugar dos tamanhos.

O metodo antigo (engine/solver_multiref.py) resolvia cor a cor, gastando o
limite de folhas na ordem das cores: podia declarar inviavel um combo viavel
ou devolver desvio maior. Este modulo e puro (sem estado global).
"""

from engine.exato_folhas import _pontos_cor, _conjunto

TRUNCOU = "truncou"


class _CtxCombo:
    """Adaptador minimo para _pontos_cor/_conjunto (mesmos nomes do _Ctx)."""

    def __init__(self, LO, HI, G):
        self.LO, self.HI, self.G = LO, HI, G
        self.UB = [None] * len(LO)
        self.T = 0
        self.RT = range(0)
        self.truncou = False


def preparar(todas_cores, dims_por_cor):
    """Limites por cor nas dimensoes compostas -- independem do combo."""
    LO, HI, G = [], [], []
    for cor in todas_cores:
        _, comp_grade, comp_limite = dims_por_cor[cor]
        G.append([int(g) for g in comp_grade])
        LO.append([max(0, int(g) + int(l[0])) for g, l in zip(comp_grade, comp_limite)])
        HI.append([int(g) + int(l[1]) for g, l in zip(comp_grade, comp_limite)])
    return LO, HI, G


def folhas_exatas(combo, n_mapas, todas_cores, dims_por_cor, prep, max_folhas):
    """{cor: [folhas por enfesto]} de menor desvio; None se o combo e inviavel;
    TRUNCOU se uma guarda de tamanho disparou antes de concluir (o chamador
    usa entao o metodo antigo)."""
    LO, HI, G = prep
    # enfestos identicos viram uma coluna so, com a capacidade somada
    indice, rep, mult, coluna = {}, [], [], []
    for k in range(n_mapas):
        ch = tuple(tuple(sorted(m.items())) for m in combo[k])
        if ch not in indice:
            indice[ch] = len(rep)
            rep.append(k)
            mult.append(0)
        a = indice[ch]
        mult[a] += 1
        coluna.append(a)
    nd = len(rep)
    caps = [max_folhas * m for m in mult]
    ctx = _CtxCombo(LO, HI, G)
    pts = []
    for ci, cor in enumerate(todas_cores):
        comp_tams = dims_por_cor[cor][0]
        if not comp_tams:
            pts.append([(0, 0.0, 0, (0,) * nd)])
            continue
        rows = [[combo[k][ri].get(t, 0) for (ri, t) in comp_tams] for k in rep]
        hi = HI[ci]
        ub = []
        for r in rows:
            u = max_folhas * n_mapas
            for t, v in enumerate(r):
                if v:
                    q = hi[t] // v if hi[t] >= 0 else -1
                    if q < u:
                        u = q
            ub.append(max(u, 0))
        ctx.UB[ci] = ub
        ctx.T = len(comp_tams)
        ctx.RT = range(ctx.T)
        p = _pontos_cor(ctx, ci, list(range(nd)), rows, caps)
        if p is None:
            return TRUNCOU if ctx.truncou else None
        pts.append(p)
    r = _conjunto(ctx, pts, caps)
    if r is None:
        return TRUNCOU if ctx.truncou else None
    if ctx.truncou:
        return TRUNCOU
    # reparte cada coluna entre os enfestos fisicos identicos, sem passar do limite
    usado = [0] * n_mapas
    folhas = {cor: [0] * n_mapas for cor in todas_cores}
    for ci, cor in enumerate(todas_cores):
        f = r[2][ci]
        for a in range(nd):
            resto = f[a]
            if not resto:
                continue
            copias = [k for k in range(n_mapas) if coluna[k] == a]
            copias.sort(key=lambda k: (max_folhas - usado[k] < resto, usado[k], k))
            for k in copias:
                x = min(resto, max_folhas - usado[k])
                if x > 0:
                    folhas[cor][k] += x
                    usado[k] += x
                    resto -= x
                if not resto:
                    break
    return folhas
