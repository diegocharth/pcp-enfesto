"""
PCP Enfestos -- busca EXATA da alocacao de rolos de UMA cor
===========================================================

Complementa engine/alocador_rolos.py (que resolve rolo a rolo, uma mochila por
rolo). Aqui a busca considera TODOS os rolos juntos (busca em profundidade com
limites e memoria de estados), para provar a menor compra possivel e, sem
deficit, o menor numero de rolos abertos.

Mesmo modelo fisico do alocador: milimetros inteiros (capacidade do rolo para
baixo, camada e margem para cima), camada inteira, sem emenda, margem de faca
paga 1x por mapa, num dos rolos que servem o mapa.

Feito para instancias pequenas (poucos mapas por cor). Passou do limite de
tempo/passos, devolve o melhor que achou com provado=False; o chamador compara
com o resultado rolo a rolo e fica com o melhor dos dois (nunca piora).
"""

import math
import time
from itertools import combinations

LIMITE_NOS = 400_000         # passos de busca por chamada (teto de seguranca)
PRAZO_S = 1.0                # tempo maximo por chamada


class _Estouro(Exception):
    pass


def _uteis(L, D, cap):
    """Maior soma de camadas (mm) que cabe em `cap` com no maximo D[i] camadas
    de cada tipo (sem margem): subconjunto-soma nos bits de um inteiro."""
    # Nada passa da soma das camadas que cabem: limita a mascara (rolo com
    # comprimento absurdo, erro de digitacao, nao aloca gigabytes).
    cap = min(cap, sum(min(di, cap // li) * li for li, di in zip(L, D)))
    alc = 1
    mascara = (1 << (cap + 1)) - 1
    for li, di in zip(L, D):
        for _ in range(min(di, cap // li)):
            novo = (alc | (alc << li)) & mascara
            if novo == alc:
                break
            alc = novo
    return alc.bit_length() - 1


class _Busca:
    def __init__(self, L, W, D, caps, marg, prazo, limite_nos):
        self.L, self.W, self.D = L, W, D
        self.M = len(L)
        self.caps = caps
        self.marg = marg
        self.prazo = prazo
        self.limite = limite_nos
        self.nos = 0
        self.cache_pad = {}
        self.melhor = [None, None]
        self._teto_rolo = None

    @property
    def teto_rolo(self):
        """Teto de cobertura de cada rolo sozinho (sem margem), com a demanda toda.
        W fica em decimos de mm do comprimento real e L e o mm arredondado para
        cima: W <= 10*L."""
        if self._teto_rolo is None:
            self._teto_rolo = [10 * _uteis(self.L, self.D, c) for c in self.caps]
        return self._teto_rolo

    def _conta(self):
        self.nos += 1
        if self.nos > self.limite or (self.nos & 1023 == 0 and time.perf_counter() > self.prazo):
            raise _Estouro()

    def padroes(self, cap, rem, st, min_cob=None):
        """Padroes MAXIMAIS de um rolo, do mais cheio para o mais vazio:
        (cobertura W, ks, novo st, usado mm, mapas que pagam a margem aqui).
        st[i]: 0 = mapa ainda nao servido, 1 = servido devendo a margem,
        2 = margem paga. A margem e paga aqui quando cabe (dominante); so fica
        devendo a que nao couber, e um rolo seguinte que sirva o mapa paga.
        min_cob: so interessam padroes com cobertura > min_cob (poda a
        enumeracao; sem memoria). None = todos, com memoria."""
        L, W, M, marg = self.L, self.W, self.M, self.marg
        # rem limitado a cap//L+1: preserva quanto cabe e se sobra camada depois.
        chave = (cap, tuple(min(r, cap // l + 1) for r, l in zip(rem, L)), st)
        if min_cob is None and chave in self.cache_pad:
            return self.cache_pad[chave]
        out = []
        ks = [0] * M
        n_pot = sum(1 for s in st if s != 2)      # margens que ainda podem ser pagas

        def fecha():
            self._conta()
            usado = sum(k * l for k, l in zip(ks, L))
            folga = cap - usado
            serv = [i for i in range(M) if ks[i] and st[i] != 2]
            n_paga = min(len(serv), folga // marg) if marg > 0 else len(serv)
            grupos = [tuple(serv)] if n_paga == len(serv) else list(combinations(serv, n_paga))
            for pagos in grupos:
                nst = list(st)
                for i in serv:
                    nst[i] = 2 if i in pagos else 1
                sobra = folga - marg * len(pagos)
                ok = True
                for i in range(M):
                    resto = rem[i] - ks[i]
                    if nst[i] == 1 and resto == 0:
                        ok = False          # devendo margem sem camada para paga-la depois
                        break
                    if resto > 0 and L[i] + (marg if nst[i] != 2 else 0) <= sobra:
                        ok = False          # nao maximal: cabia mais uma camada
                        break
                if ok:
                    cob = sum(k * w for k, w in zip(ks, W))
                    out.append((cob, tuple(ks), tuple(nst), cap - sobra, frozenset(pagos)))

        def rec(t, c, cob):
            self._conta()
            if t == M:
                fecha()
                return
            if min_cob is not None:
                extra = sum(min(rem[i], c // L[i]) * W[i] for i in range(t, M))
                if cob + min(extra, 10 * c) <= min_cob:
                    return          # nem enchendo o resto passa do minimo pedido
            # Poda: tipos ja decididos que nao se esgotaram seguem disponiveis;
            # se o resto nao consegue baixar a sobra para menos que a menor
            # camada deles (com folga para todas as margens), nada daqui e maximal.
            disp = [L[i] for i in range(t) if rem[i] - ks[i] > 0]
            if disp:
                cabe = sum(min(rem[i], c // L[i]) * L[i] for i in range(t, M))
                if c - min(cabe, c) - marg * n_pot >= min(disp) + marg:
                    return
            for k in range(min(rem[t], c // L[t]), -1, -1):
                ks[t] = k
                rec(t + 1, c - k * L[t], cob + k * W[t])
            ks[t] = 0

        rec(0, cap, 0)
        if not out and min_cob is None:
            out.append((0, tuple([0] * M), st, 0, frozenset()))
        out.sort(key=lambda p: -p[0])
        if min_cob is None:
            self.cache_pad[chave] = out
        return out

    def maximizar(self, ordem, piso, rem0=None, st0=None, limiar_padroes=False):
        """Maior cobertura (W) com os rolos de `ordem`, aceitando so solucao > piso.
        rem0/st0: camadas disponiveis e estado das margens no inicio (padrao: a
        demanda toda, nenhum mapa servido). limiar_padroes: enumera so os padroes
        que ainda podem superar o piso (para muitos mapas; sem memoria).
        Resultado em self.melhor = [cobertura, plano] (plano None: nada supera o piso)."""
        R = len(ordem)
        if rem0 is None:
            rem0, teto_rolo = tuple(self.D), self.teto_rolo
        else:
            rem0 = tuple(rem0)
            teto_rolo = {j: 10 * _uteis(self.L, rem0, self.caps[j]) for j in ordem}
        st0 = tuple(st0) if st0 is not None else tuple([0] * self.M)
        teto_fim = [0] * (R + 1)
        for p in range(R - 1, -1, -1):
            teto_fim[p] = teto_fim[p + 1] + teto_rolo[ordem[p]]
        W = self.W
        melhor = self.melhor = [piso, None]
        teto_memo = {}
        pilha = []
        alvo_max = min(teto_fim[0], sum(d * w for d, w in zip(rem0, W)))

        def dfs(p, rem, st, cob):
            self._conta()
            limiar = melhor[0] - cob
            resto = sum(r * w for r, w in zip(rem, W))
            if min(resto, teto_fim[p]) <= limiar:
                return
            chave = (p, rem, st)
            if teto_memo.get(chave, 1 << 62) <= limiar:
                return
            if p == R:
                if 1 not in st:
                    melhor[0], melhor[1] = cob, list(pilha)
                return
            minimo = (melhor[0] - cob - teto_fim[p + 1]) if limiar_padroes else None
            for pad in self.padroes(self.caps[ordem[p]], rem, st, minimo):
                if min(pad[0] + teto_fim[p + 1], resto) <= melhor[0] - cob:
                    break
                pilha.append((ordem[p], pad))
                dfs(p + 1, tuple(r - k for r, k in zip(rem, pad[1])), pad[2], cob + pad[0])
                pilha.pop()
                if melhor[0] >= alvo_max:
                    return
            teto_memo[chave] = min(teto_memo.get(chave, 1 << 62), melhor[0] - cob)

        dfs(0, rem0, st0, 0)


def _preparar(demanda, comp_camada_por_id, rolos_cor, config):
    """Tipos (mapas com demanda), em mm/decimos de mm, e capacidades dos rolos."""
    from engine.alocador_rolos import _comp_seguro   # import tardio: evita ciclo
    mids = [m for m in sorted(demanda, key=lambda m: (-comp_camada_por_id.get(m, 0.0), m))
            if int(demanda[m]) > 0 and float(comp_camada_por_id.get(m, 0.0)) > 0]
    L = [int(math.ceil(float(comp_camada_por_id[m]) * 1000 - 1e-6)) for m in mids]
    W = [int(round(float(comp_camada_por_id[m]) * 10000)) for m in mids]
    D = [int(demanda[m]) for m in mids]
    marg = int(math.ceil(float(config.get("margem_seguranca_enfesto_m", 0.10)) * 1000 - 1e-6))
    caps = [int(math.floor(round(_comp_seguro(n, config), 6) * 1000 + 1e-6)) for n in rolos_cor]
    return mids, L, W, D, marg, caps


def plano_de_resultado(res):
    """Plano [(rolo 0-based, {mapa: k}, {mapas que pagam})] de um resultado de
    _alocar_cor (fontes por enfesto; primaria = paga a margem naquele rolo)."""
    por_rolo = {}
    for e in res.get("enfestos", []):
        for f in e.get("fontes", []):
            esc, pagos = por_rolo.setdefault(f["rolo_indice"] - 1, ({}, set()))
            esc[e["mapa_id"]] = esc.get(e["mapa_id"], 0) + int(f["n_camadas"])
            if f.get("primaria"):
                pagos.add(e["mapa_id"])
    return [(j, esc, pagos) for j, (esc, pagos) in sorted(por_rolo.items())]


def vizinhanca(demanda, comp_camada_por_id, rolos_cor, config, plano, prazo_s=PRAZO_S,
               limite_par=20_000, limite_total=None):
    """Busca local para cores com muitos mapas (onde a busca completa nao fecha).

    Parte de um plano valido e, para cada PAR de rolos, re-otimiza de forma exata
    o que os dois cortam (as camadas deles mais todo o deficit), sem mexer nos
    outros rolos. So aceita aumento estrito de metros cobertos (= menos compra).
    Repete os passes ate um passe inteiro nao melhorar, gastar `limite_total`
    passos de busca (deterministico: mesma entrada, mesmo resultado) ou acabar
    o prazo (seguranca). Devolve o plano melhorado (mesmo formato) ou None."""
    mids, L, W, D, marg, caps = _preparar(demanda, comp_camada_por_id, rolos_cor, config)
    M, R = len(mids), len(caps)
    if not M or R < 2:
        return None
    idx = {m: i for i, m in enumerate(mids)}
    X = [[0] * M for _ in range(R)]
    paga = [None] * M
    for j, esc, pagos in plano:
        for m, k in esc.items():
            if m in idx:
                X[j][idx[m]] += int(k)
        for m in pagos:
            if m in idx:
                paga[idx[m]] = j

    def usado(j, pg):
        return (sum(k * l for k, l in zip(X[j], L))
                + marg * sum(1 for i in range(M) if pg[i] == j))

    def valido(pg):
        if any(usado(j, pg) > caps[j] for j in range(R)):
            return False
        for i in range(M):
            servido = any(X[j][i] for j in range(R))
            if servido != (pg[i] is not None) or (servido and not X[pg[i]][i]):
                return False        # margem paga 1x, por um rolo que serve o mapa
        return True

    deficit = [D[i] - sum(X[j][i] for j in range(R)) for i in range(M)]
    if any(d < 0 for d in deficit) or not valido(paga):
        return None                       # plano de entrada fora do modelo: nao mexe
    fim = time.perf_counter() + prazo_s
    melhorou = False
    gasto = 0

    def esgotou():
        return (time.perf_counter() >= fim
                or (limite_total is not None and gasto >= limite_total))

    def tenta(S):
        """Re-otimiza os rolos de S juntos; aplica se a cobertura subir."""
        nonlocal deficit, gasto
        rem0 = [sum(X[j][i] for j in S) + deficit[i] for i in range(M)]
        fora = [any(X[r][i] for r in range(R) if r not in S) for i in range(M)]
        st0 = [2 if fora[i] and paga[i] not in S else 0 for i in range(M)]
        piso = sum(sum(X[j][i] for j in S) * W[i] for i in range(M))
        lim = limite_par if limite_total is None else min(limite_par, limite_total - gasto)
        busca = _Busca(L, W, D, caps, marg, fim, lim)
        try:
            busca.maximizar(list(S), piso, rem0, st0, limiar_padroes=True)
        except _Estouro:
            pass                          # usa o que achou ate o limite do grupo
        gasto += busca.nos
        achado = busca.melhor[1]
        if achado is None:
            return False
        X_ant = {j: X[j] for j in S}
        for j in S:
            X[j] = [0] * M
        nova = [None if paga[i] in S else paga[i] for i in range(M)]
        for j, pad in achado:
            X[j] = list(pad[1])
            for i in pad[4]:
                nova[i] = j
        # Mapa que pagava a margem dentro do grupo e segue servido so fora
        # dele: um rolo de fora que o serve e tem folga paga a margem.
        for i in range(M):
            if nova[i] is None and any(X[r][i] for r in range(R)):
                livres = [r for r in range(R) if r not in S and X[r][i]
                          and caps[r] - usado(r, nova) >= marg]
                if livres:
                    nova[i] = max(livres, key=lambda r: (caps[r] - usado(r, nova), -r))
        if not valido(nova):
            for j in S:
                X[j] = X_ant[j]
            return False
        paga[:] = nova
        deficit = [D[i] - sum(X[j][i] for j in range(R)) for i in range(M)]
        return True

    # Pares primeiro (baratos); sem melhora num passe inteiro, trios; se um
    # trio melhorar, volta aos pares. Rolos com mais folga entram antes.
    tamanho = 2
    while not esgotou() and any(deficit) and tamanho <= min(3, R):
        folgas = sorted(range(R), key=lambda j: (usado(j, paga) - caps[j], j))
        passe = False
        for S in combinations(folgas, tamanho):
            if esgotou() or not any(deficit):
                break
            if tenta(S):
                passe = melhorou = True
        tamanho = 2 if passe else tamanho + 1
    if not melhorou:
        return None
    out = []
    for j in sorted(range(R), key=lambda j: (-caps[j], j)):
        esc = {mids[i]: X[j][i] for i in range(M) if X[j][i]}
        if esc:
            out.append((j, esc, {mids[i] for i in range(M) if paga[i] == j}))
    return out


def resolver(demanda, comp_camada_por_id, rolos_cor, config, cobertas_piso=None,
             n_rolos_piso=None, prazo_s=PRAZO_S, limite_nos=LIMITE_NOS):
    """Busca exata de uma cor.

    cobertas_piso {mapa: camadas} e n_rolos_piso: resultado ja conhecido (rolo a
    rolo). So devolve plano que o supere: mais metros cobertos; ou, sem deficit,
    a mesma cobertura com menos rolos.

    Devolve {"plano": [(rolo_idx0, {mapa: k}, {mapas que pagam margem})] na ordem
    de corte, ou None quando nao achou nada melhor, "provado": bool}. provado=True
    com plano None = o resultado conhecido ja e otimo."""
    mids, L, W, D, marg, caps = _preparar(demanda, comp_camada_por_id, rolos_cor, config)
    if not mids or not rolos_cor:
        return {"plano": None, "provado": True}
    b = _Busca(L, W, D, caps, marg, time.perf_counter() + prazo_s, limite_nos)
    ordem = sorted(range(len(caps)), key=lambda j: (-caps[j], j))
    total = sum(d * w for d, w in zip(D, W))
    piso = -1 if cobertas_piso is None else sum(
        int(cobertas_piso.get(m, 0)) * w for m, w in zip(mids, W))

    def traduz(plano):
        out = []
        for j, pad in plano:
            esc = {mids[i]: k for i, k in enumerate(pad[1]) if k}
            if esc:
                out.append((j, esc, {mids[i] for i in pad[4]}))
        return out

    try:
        b.maximizar(ordem, piso)
    except _Estouro:
        plano = b.melhor[1]
        return {"plano": traduz(plano) if plano else None, "provado": False}
    achado = b.melhor[1]
    if achado is not None:
        if b.melhor[0] < total:
            return {"plano": traduz(achado), "provado": True}
        n_rolos_piso = sum(1 for _, pad in achado if any(pad[1]))
    # Cobertura otima. Sem deficit, procura a mesma cobertura com MENOS rolos
    # (os k maiores bastam: trocar cada rolo por um maior ou igual nunca
    # invalida o plano).
    if (achado is None and piso < total) or not n_rolos_piso or n_rolos_piso <= 1:
        return {"plano": traduz(achado) if achado else None, "provado": True}
    necessario = sum(d * l for d, l in zip(D, L)) + marg * len(D)
    acum, kmin = 0, None
    for n, j in enumerate(ordem, 1):
        acum += caps[j]
        if acum >= necessario:
            kmin = n
            break
    sem_menos = {"plano": traduz(achado) if achado else None, "provado": True}
    if kmin is None:
        return sem_menos
    try:
        for k in range(kmin, n_rolos_piso):
            b.maximizar(ordem[:k], total - 1)
            if b.melhor[1] is not None:
                return {"plano": traduz(b.melhor[1]), "provado": True}
    except _Estouro:
        return dict(sem_menos, provado=False)
    return sem_menos


# Busca completa so com poucos mapas na cor: medido, ate 8 mapas ela fecha em
# menos de 1 s em ~80-100% dos casos; no plano multi-ref real de 02/07 (17 mapas
# por cor) nao fecha. Ali entra a busca local por pares/trios de rolos.
# As duas param por PASSOS de busca (mesma entrada -> mesmo resultado; ~350-500
# mil passos/s na maquina de desenvolvimento); o relogio e so seguranca.
# Busca local no 02/07 (10 cor x folga), compra a menos x passos: 150 mil
# -13,9 m (0,4 s/cor); 300 mil -17,9 m; 500 mil -22,0 m (1,3 s/cor); 800 mil
# -26,1 m (2,1 s/cor); 1,2 milhao -28,0 m. CP-SAT (120 s/cor): -42,8 m.
EXATA_MAX_MAPAS = 8
EXATA_MAX_ROLOS = 200        # busca completa: 1 nivel de recursao por rolo
EXATA_PASSOS = 400_000       # busca completa, por cor
LOCAL_PASSOS = 500_000       # busca local, por cor
EXATA_PRAZO_COR_S = 4.0      # seguranca por etapa (completa; local) em cada cor
EXATA_PRAZO_TOTAL_S = 15.0   # seguranca da alocacao inteira (cores e lotes)


def _prazo_restante(config, teto):
    fim = config.get("_prazo_exata")
    return teto if fim is None else min(teto, fim - time.perf_counter())


def melhorar(demanda, comp_camada_por_id, rolos_cor, config, res):
    """Melhora a alocacao rolo a rolo `res` de uma cor:
    busca completa com poucos mapas (prova o otimo); com muitos mapas, ou se a
    completa nao fechar no prazo, busca local a partir do melhor plano conhecido
    (melhora a compra, sem prova). Respeita o prazo global da alocacao
    (config["_prazo_exata"], relogio perf_counter). Devolve {"plano", "provado"}
    ou None quando desligada ou sem tempo."""
    if not config.get("alocacao_exata", True) or not rolos_cor:
        return None
    out = None
    if (sum(1 for m in demanda if int(demanda[m]) > 0) <= EXATA_MAX_MAPAS
            and len(rolos_cor) <= EXATA_MAX_ROLOS):
        prazo = _prazo_restante(config, EXATA_PRAZO_COR_S)
        if prazo <= 0.01:
            return None
        try:
            out = resolver(
                demanda, comp_camada_por_id, rolos_cor, config,
                cobertas_piso=res["camadas_alocadas"],
                n_rolos_piso=res["n_rolos_utilizados"], prazo_s=prazo,
                limite_nos=EXATA_PASSOS)
        except RecursionError:          # rede de seguranca: fica o rolo a rolo
            out = None
        if out is not None and out["provado"]:
            return out
    if not res["camadas_em_deficit"]:
        return out                       # a busca local so reduz compra
    prazo = _prazo_restante(config, EXATA_PRAZO_COR_S)
    if prazo <= 0.01:
        return out
    base = (out["plano"] if out and out["plano"]
            else plano_de_resultado(res))
    try:
        plano = vizinhanca(demanda, comp_camada_por_id, rolos_cor,
                                          config, base, prazo_s=prazo,
                                          limite_total=LOCAL_PASSOS)
    except RecursionError:
        plano = None
    if plano:
        return {"plano": plano, "provado": False}
    return out if out is not None else {"plano": None, "provado": False}
