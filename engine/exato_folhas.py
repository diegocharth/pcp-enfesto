"""
PCP Enfestos -- Motor exato: folhas de um combo de mapas e montagem
===================================================================

Parte pura do motor exato (engine/solver_exato.py), separada para manter os
arquivos pequenos. Dado um conjunto de mapas:

- _pontos_cor: TODOS os vetores de folhas que deixam UMA cor dentro da
  tolerancia (propagacao de intervalos + enumeracao da caixa).
- _conjunto: escolhe um ponto por cor de modo que a soma de folhas de cada
  mapa respeite o limite do enfesto, com o menor desvio total (programacao
  dinamica exata sobre as cores).

`ctx` e o contexto do solver (listas LO/HI/G por cor, UB por cor x mapa, RT, T)
e recebe ctx.truncou = True se alguma guarda de tamanho disparar -- nesse caso
o resultado continua valido, mas deixa de valer como prova.
"""

MOTOR_ID = "exato-4"        # entra na assinatura do cache: mudar ao mudar o resultado

MAX_NOS_COR = 20000         # guarda da enumeracao de folhas de uma cor
MAX_PONTOS_COR = 20000      # so corta listas absurdas; pontos dominados saem em _conjunto
MAX_ESTADOS_CONJUNTO = 4000  # guarda da reparticao de folhas entre as cores
NOS_BUSCA_RAPIDA = 3000      # busca em profundidade antes de cair na prog. dinamica



# ---------------------------------------------------------------------------
# Folhas de UMA cor: todos os pontos viaveis
# ---------------------------------------------------------------------------

def _pontos_cor(ctx, c, ks, rows, caps):
    """Lista ordenada de (desvio, desvio_rel, soma_folhas, folhas) com TODOS os
    vetores de folhas que deixam a cor c dentro da tolerancia; None se nenhum.
    ks: indices dos mapas distintos; caps: folhas maximas por mapa distinto."""
    lo, hi, g = ctx.LO[c], ctx.HI[c], ctx.G[c]
    ubc = ctx.UB[c]
    nd = len(ks)
    RT = ctx.RT
    RD = range(nd)
    lob = [0] * nd
    upb = [ubc[ks[a]] if ubc[ks[a]] < caps[a] else caps[a] for a in RD]

    mudou = True
    while mudou:                      # propagacao de intervalos ate o ponto fixo
        mudou = False
        for t in RT:
            smin = 0
            smax = 0
            for a in RD:
                v = rows[a][t]
                if v:
                    smin += v * lob[a]
                    smax += v * upb[a]
            if smax < lo[t] or smin > hi[t]:
                return None
            for a in RD:
                v = rows[a][t]
                if not v:
                    continue
                falta = lo[t] - (smax - v * upb[a])
                if falta > 0:
                    nl = -(-falta // v)
                    if nl > lob[a]:
                        if nl > upb[a]:
                            return None
                        smin += v * (nl - lob[a])
                        lob[a] = nl
                        mudou = True
                nh = (hi[t] - (smin - v * lob[a])) // v
                if nh < upb[a]:
                    if nh < lob[a]:
                        return None
                    smax -= v * (upb[a] - nh)
                    upb[a] = nh
                    mudou = True

    out = []
    fs = [0] * nd
    nos = [0]
    ult = nd - 1

    def rec(a, s):
        r = rows[a]
        if a == ult:                  # ultima coluna: intervalo em forma fechada
            lk, hk = lob[a], upb[a]
            for t in RT:
                v = r[t]
                if v:
                    v1 = -(-(lo[t] - s[t]) // v)
                    v2 = (hi[t] - s[t]) // v
                    if v1 > lk:
                        lk = v1
                    if v2 < hk:
                        hk = v2
                elif s[t] < lo[t] or s[t] > hi[t]:
                    return
            for x in range(lk, hk + 1):
                dev = 0
                drel = 0.0
                for t in RT:
                    d = s[t] + x * r[t] - g[t]
                    if d < 0:
                        d = -d
                    if d:
                        dev += d
                        drel += d / (g[t] or 1)
                fs[a] = x
                out.append((dev, drel, sum(fs), tuple(fs)))
            return
        for x in range(lob[a], upb[a] + 1):
            nos[0] += 1
            if nos[0] > MAX_NOS_COR:
                ctx.truncou = True
                return
            fs[a] = x
            s2 = [s[t] + x * r[t] for t in RT]
            for t in RT:
                if s2[t] > hi[t]:
                    break
            else:
                rec(a + 1, s2)

    rec(0, [0] * ctx.T)
    if not out:
        return None
    out.sort()
    if len(out) > MAX_PONTOS_COR:
        ctx.truncou = True
        del out[MAX_PONTOS_COR:]
    return out


# ---------------------------------------------------------------------------
# Capacidade conjunta: um ponto por cor, sem estourar as folhas de cada mapa
# ---------------------------------------------------------------------------

def _conjunto(ctx, pts, caps):
    """Escolhe um ponto por cor minimizando (desvio, desvio_rel) com a soma de
    folhas de cada mapa <= caps. Retorna (desvio, desvio_rel, [folhas por cor])
    ou None se as cores nao cabem juntas.

    Tres degraus, todos exatos: (1) o melhor ponto de cada cor ja cabe; (2)
    busca em profundidade com teto de nos, que resolve na hora a maioria dos
    casos apertados; (3) se o teto estourar, programacao dinamica sobre as
    cores (estado = folhas ja gastas em cada mapa; estados dominados saem),
    que nao explode."""
    nd = len(caps)
    RD = range(nd)
    uso = [0] * nd
    dev = 0
    drel = 0.0
    for p in pts:                     # caminho rapido: o melhor de cada cor cabe
        b = p[0]
        dev += b[0]
        drel += b[1]
        f = b[3]
        for a in RD:
            uso[a] += f[a]
    for a in RD:
        if uso[a] > caps[a]:
            break
    else:
        return dev, drel, [p[0][3] for p in pts]

    C = len(pts)
    # Pontos dominados dentro da propria cor (outro ponto nao pior no desvio e
    # sem gastar mais folhas em nenhum mapa) nunca sao necessarios.
    filtrados = []
    for p in pts:
        keep = []
        for q in p:                   # p esta ordenado por (dev, drel, soma)
            fq = q[3]
            for k in keep:
                fk = k[3]
                for a in RD:
                    if fk[a] > fq[a]:
                        break
                else:
                    break             # k domina q
            else:
                keep.append(q)
        filtrados.append(keep)
    ordem = sorted(range(C), key=lambda i: len(filtrados[i]))
    # suf_min[i][a]: minimo de folhas do mapa a que as cores i.. ainda vao gastar
    suf_min = [[0] * nd for _ in range(C + 1)]
    for i in range(C - 1, -1, -1):
        pts_i = filtrados[ordem[i]]
        for a in RD:
            suf_min[i][a] = suf_min[i + 1][a] + min(q[3][a] for q in pts_i)
    for a in RD:                      # nem os minimos de cada cor cabem
        if suf_min[0][a] > caps[a]:
            return None

    suf_dev = [0] * (C + 1)           # menor desvio possivel das cores i..
    for i in range(C - 1, -1, -1):
        suf_dev[i] = suf_dev[i + 1] + filtrados[ordem[i]][0][0]
    melhor = [None, None]
    atual = [None] * C
    nos = [0]

    def rec(i, gasto, d0, r0):
        if nos[0] > NOS_BUSCA_RAPIDA:
            return
        if melhor[0] is not None and (d0 + suf_dev[i], r0) >= melhor[0]:
            return
        if i == C:
            melhor[0] = (d0, r0)
            melhor[1] = list(atual)
            return
        prox = suf_min[i + 1]
        for q in filtrados[ordem[i]]:
            nos[0] += 1
            f = q[3]
            for a in RD:
                if gasto[a] + f[a] + prox[a] > caps[a]:
                    break
            else:
                atual[ordem[i]] = f
                rec(i + 1, [gasto[a] + f[a] for a in RD], d0 + q[0], r0 + q[1])

    rec(0, [0] * nd, 0, 0.0)
    if nos[0] <= NOS_BUSCA_RAPIDA:    # a busca terminou: resultado exato
        if melhor[0] is None:
            return None
        return melhor[0][0], melhor[0][1], melhor[1]

    estados = {(0,) * nd: (0, 0.0, ())}   # folhas gastas -> (dev, drel, escolhas)
    for i in range(C):
        prox = suf_min[i + 1]
        teto = [caps[a] - prox[a] for a in RD]
        novos = {}
        for gasto, (d0, r0, esc) in estados.items():
            for q in filtrados[ordem[i]]:
                f = q[3]
                g2 = tuple([gasto[a] + f[a] for a in RD])
                for a in RD:
                    if g2[a] > teto[a]:
                        break
                else:
                    d2 = d0 + q[0]
                    r2 = r0 + q[1]
                    cur = novos.get(g2)
                    if cur is None or (d2, r2) < (cur[0], cur[1]):
                        novos[g2] = (d2, r2, esc + (f,))
        if not novos:
            return None
        if len(novos) > 24:           # descarta estados dominados
            itens = sorted(novos.items(), key=lambda kv: (kv[1][0], kv[1][1]))
            mantidos = []
            for g, v in itens:
                for g1, _ in mantidos:
                    for a in RD:
                        if g1[a] > g[a]:
                            break
                    else:
                        break         # g1 gasta menos e desvia menos: domina g
                else:
                    mantidos.append((g, v))
                    if len(mantidos) > MAX_ESTADOS_CONJUNTO:
                        ctx.truncou = True
                        break
            novos = dict(mantidos)
        estados = novos

    d, r, esc = min(estados.values(), key=lambda v: (v[0], v[1]))
    escolha = [None] * C
    for pos, i in enumerate(ordem):
        escolha[i] = esc[pos]
    return d, r, escolha


# ---------------------------------------------------------------------------
# Montagem da solucao no formato do solver classico
# ---------------------------------------------------------------------------

ROTULOS = {
    "minimo_enfestos": "Menos enfestos",
    "menor_desvio": "Menor desvio (+1 enfesto)",
    "mapas_cheios": "Mapas mais cheios",
    "alternativa": "Alternativa",
}


def _distintos(idx):
    """(indices distintos, multiplicidades) de um multiconjunto ordenado."""
    ks, mu = [], []
    for k in idx:
        if ks and ks[-1] == k:
            mu[-1] += 1
        else:
            ks.append(k)
            mu.append(1)
    return ks, mu


def _montar(ctx, n, idx, escolha, grade, prova, papel):
    ks, mu = _distintos(idx)
    fis = []                           # enfesto fisico -> coluna distinta
    for a, m in enumerate(mu):
        fis.extend([a] * m)
    usado = [0] * n
    folhas = {cor: [0] * n for cor in ctx.cores}
    for ci, cor in enumerate(ctx.cores):
        f = escolha[ci]
        for a in range(len(ks)):
            resto = f[a]
            if not resto:
                continue
            copias = [e for e in range(n) if fis[e] == a]
            # tenta manter a cor inteira num enfesto so (o mais vazio que caiba)
            copias.sort(key=lambda e: (ctx.F - usado[e] < resto, usado[e], e))
            for e in copias:
                x = min(resto, ctx.F - usado[e])
                if x > 0:
                    folhas[cor][e] += x
                    usado[e] += x
                    resto -= x
                if not resto:
                    break
    mapas = [dict(zip(ctx.tams, ctx.maps[ks[a]])) for a in fis]
    tams = ctx.tams
    dev_total = 0
    dev_rel = 0.0
    for cor in ctx.cores:
        for t in tams:
            ct = sum(folhas[cor][e] * mapas[e][t] for e in range(n))
            gv = grade[cor].get(t, 0)
            dev_total += abs(ct - gv)
            dev_rel += abs(ct - gv) / (gv or 1)
    pecas_por_mapa = [sum(m.values()) for m in mapas]
    return {
        "n_mapas": n,
        "mapas": mapas,
        "folhas": folhas,
        "resumo": {
            "n_mapas": n,
            "total_folhas": sum(usado),
            "pecas_por_mapa": pecas_por_mapa,
            "media_pecas_mapa": round(sum(pecas_por_mapa) / n, 1),
            "comprimento_por_mapa": [round(p * ctx.consumo, 4) for p in pecas_por_mapa],
            "comprimento_total": round(sum(pecas_por_mapa) * ctx.consumo, 4),
            "desvio_total": dev_total,
            "desvio_relativo": round(dev_rel, 4),
            "max_folhas_enfesto": ctx.F,
            "consumo_peca": ctx.consumo,
            "prova": prova,
            "motor": MOTOR_ID,
            "papel": papel,
            "rotulo": ROTULOS[papel],
            "comparacao": "",
        },
    }


def _comparar(base, r):
    """Texto curto do que muda nesta opcao em relacao a de menos enfestos."""
    partes = []
    dn = r["n_mapas"] - base["n_mapas"]
    if dn:
        partes.append(f"{dn:+d} enfesto" + ("s" if abs(dn) > 1 else ""))
    dd = r["desvio_total"] - base["desvio_total"]
    partes.append(f"{dd:+d} peças de desvio" if dd else "mesmo desvio")
    dp = round(r["media_pecas_mapa"] - base["media_pecas_mapa"], 1)
    if dp:
        partes.append(f"{dp:+.1f} pç/mapa".replace(".", ","))
    return ", ".join(partes)
