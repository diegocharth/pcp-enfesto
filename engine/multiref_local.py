"""
PCP Enfestos — Multi-Ref: busca local guiada por violação
=========================================================

Quando a varredura do pool estático não encontra combinação viável, este
módulo faz uma busca local no espaço COMPLETO de composições: parte de
sementes proporcionais e move 1 peça por vez (trocar tamanho, transferir
entre refs, adicionar/remover), sempre medindo a VIOLAÇÃO das tolerâncias
com um solve "soft" por cor (coordinate descent vetorizado que minimiza
violação e desempata por desvio). Violação zero = solução viável de verdade.

Por que existe: combinações viáveis reais usam splits "criativos" (ex.:
KIARA[2PP+1M+1G] junto de LILIAN[1PP+1P]) que nenhum ranking estático de
composições coloca no topo. A busca local encontra essas agulhas seguindo o
gradiente da violação — e os moves são DIRECIONADOS: quando falta peça do
tamanho T da ref R, os candidatos priorizam colocar/realocar peças em (R,T).

Determinístico: RNG com semente fixa -> mesmo input, mesmo resultado
(compatível com o cache de planos por assinatura).
"""

import random

try:
    import numpy as _np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False


def _solve_soft_cor(A, gv, lov, hiv, caps, fs_ini=None, sweeps=3, janela=14):
    """Folhas por cor minimizando (violacao, desvio) — sem exigir viabilidade.

    A: (n_slots x T) peças por dimensão composta; gv/lov/hiv: (T,) grade e
    janelas absolutas; caps: (n_slots,) folhas restantes.
    Retorna (fs, violacao, desvio, ct)."""
    n = A.shape[0]
    caps = _np.maximum(caps, 0)
    if fs_ini is None:
        try:
            x, *_ = _np.linalg.lstsq(A.T.astype(float), gv.astype(float), rcond=None)
            fs = _np.clip(_np.round(x), 0, caps).astype(_np.int64)
        except Exception:
            fs = _np.zeros(n, dtype=_np.int64)
    else:
        fs = _np.clip(fs_ini, 0, caps).astype(_np.int64)

    ct = fs @ A

    def viol_dev(cts):
        viol = _np.clip(lov - cts, 0, None).sum(axis=-1) + _np.clip(cts - hiv, 0, None).sum(axis=-1)
        dev = _np.abs(cts - gv).sum(axis=-1)
        return viol, dev

    for sw in range(sweeps):
        moved = False
        for k in range(n):
            base = ct - fs[k] * A[k]
            if sw == 0 and fs_ini is None:
                lo_v, hi_v = 0, int(caps[k])
            else:
                lo_v = max(0, int(fs[k]) - janela)
                hi_v = min(int(caps[k]), int(fs[k]) + janela)
            if hi_v < lo_v:
                continue
            vs = _np.arange(lo_v, hi_v + 1)
            cts = base[None, :] + vs[:, None] * A[k][None, :]
            V, D = viol_dev(cts)
            idx = int(_np.lexsort((D, V))[0])
            if int(vs[idx]) != int(fs[k]):
                fs[k] = int(vs[idx])
                ct = base + fs[k] * A[k]
                moved = True
        if not moved:
            break
    V, D = viol_dev(ct)
    return fs, float(V), float(D), ct


class _Avaliador:
    """Avalia estados (tensor X: n_slots x R x T) com solve soft por cor.

    Pré-computa máscaras de colunas por cor e faz warm-start das folhas do
    estado pai para acelerar a avaliação dos vizinhos."""

    def __init__(self, refs_data, tamanhos, n_mapas, max_folhas, dims_np, todas_cores):
        self.n = n_mapas
        self.R = len(refs_data)
        self.T = len(tamanhos)
        self.max_folhas = max_folhas
        self.todas_cores = todas_cores
        self.tam_idx = {t: i for i, t in enumerate(tamanhos)}
        self.dims = {}
        for cor in todas_cores:
            comp_tams, gv, lov, hiv = dims_np[cor]
            cols = _np.array(
                [ri * self.T + self.tam_idx[t] for (ri, t) in comp_tams],
                dtype=_np.int64)
            self.dims[cor] = (cols, gv, lov, hiv, comp_tams)

    def avaliar(self, X, fs_pai=None):
        """(violacao, desvio, folhas{cor: fs}, detalhes_pior) para o estado X."""
        A_full = X.reshape(self.n, self.R * self.T)
        used = _np.zeros(self.n, dtype=_np.int64)
        Vt = 0.0
        Dt = 0.0
        folhas = {}
        piores = []  # (viol_dim, cor, ri, t, sinal)
        for cor in self.todas_cores:
            cols, gv, lov, hiv, comp_tams = self.dims[cor]
            if len(cols) == 0:
                folhas[cor] = _np.zeros(self.n, dtype=_np.int64)
                continue
            A = A_full[:, cols]
            caps = self.max_folhas - used
            ini = fs_pai.get(cor) if fs_pai else None
            fs, V, D, ct = _solve_soft_cor(A, gv, lov, hiv, caps, fs_ini=ini)
            folhas[cor] = fs
            used = used + fs
            Vt += V
            Dt += D
            if V > 0:
                falta = _np.clip(lov - ct, 0, None)
                sobra = _np.clip(ct - hiv, 0, None)
                for ti in range(len(cols)):
                    if falta[ti] > 0:
                        piores.append((float(falta[ti]), cor, comp_tams[ti][0],
                                       comp_tams[ti][1], +1))
                    elif sobra[ti] > 0:
                        piores.append((float(sobra[ti]), cor, comp_tams[ti][0],
                                       comp_tams[ti][1], -1))
        piores.sort(key=lambda x: -x[0])
        return Vt, Dt, folhas, piores[:8]


def buscar_local(refs_data, tamanhos, n_mapas, mesa, max_folhas, dims_np,
                 todas_cores, seeds, deadline, ja_encontradas, max_solucoes=2,
                 rng_seed=20260702, estagnacao_s=15.0):
    """Busca local por estados de violação zero.

    seeds: estados iniciais (cada um = lista de n_mapas tuplas de dicts por
    ref). deadline: time.time() limite. estagnacao_s: se a MENOR violação já
    vista não melhora por esse tempo (e nada foi encontrado), desiste do nível
    — grupos sem ganho respondem rápido em vez de queimar o teto inteiro.
    Retorna lista de (estado, folhas)."""
    import time as _t
    if not _HAS_NP:
        return []
    rng = random.Random(rng_seed)
    R = len(refs_data)
    T = len(tamanhos)
    tam_idx = {t: i for i, t in enumerate(tamanhos)}
    consumos = _np.array([float(r.get("consumo", 1.0645)) for r in refs_data])
    av = _Avaliador(refs_data, tamanhos, n_mapas, max_folhas, dims_np, todas_cores)

    def estado_para_X(estado):
        X = _np.zeros((n_mapas, R, T), dtype=_np.int64)
        for k in range(n_mapas):
            for ri in range(R):
                for t, v in estado[k][ri].items():
                    X[k, ri, tam_idx[t]] = v
        return X

    def X_para_estado(X):
        est = []
        for k in range(n_mapas):
            slot = []
            for ri in range(R):
                slot.append({tamanhos[ti]: int(X[k, ri, ti])
                             for ti in range(T) if X[k, ri, ti] > 0})
            est.append(tuple(slot))
        return est

    def chave(X):
        return tuple(sorted(tuple(X[k].flatten().tolist()) for k in range(n_mapas)))

    def comprimentos(X):
        return (X.sum(axis=2) * consumos[None, :]).sum(axis=1)

    def gerar_move(X, piores):
        """Vizinho de X: 60% direcionado pela pior violacao, 40% aleatorio."""
        Xn = X.copy()
        if piores and rng.random() < 0.6:
            # move direcionado: mexe na dimensao mais violada (com ruido)
            _, cor, ri, t, sinal = piores[min(rng.randrange(3), len(piores) - 1)]
            ti = tam_idx[t]
            k = rng.randrange(n_mapas)
            if sinal > 0:
                # falta (ri, t): adiciona peca (se couber) ou rouba de outro tamanho
                if rng.random() < 0.5:
                    Xn[k, ri, ti] += 1
                    if comprimentos(Xn)[k] > mesa + 1e-9:
                        Xn[k, ri, ti] -= 1
                        com = [tj for tj in range(T) if Xn[k, ri, tj] > 0 and tj != ti]
                        if not com:
                            return None
                        Xn[k, ri, rng.choice(com)] -= 1
                        Xn[k, ri, ti] += 1
                else:
                    com = [tj for tj in range(T) if Xn[k, ri, tj] > 0 and tj != ti]
                    if not com:
                        return None
                    Xn[k, ri, rng.choice(com)] -= 1
                    Xn[k, ri, ti] += 1
            else:
                # sobra (ri, t): tira uma peca desse tamanho (vira outro ou some)
                ks = [kk for kk in range(n_mapas) if Xn[kk, ri, ti] > 0]
                if not ks:
                    return None
                k = rng.choice(ks)
                Xn[k, ri, ti] -= 1
                if rng.random() < 0.6:
                    tj = rng.randrange(T)
                    Xn[k, ri, tj] += 1
                    if comprimentos(Xn)[k] > mesa + 1e-9:
                        Xn[k, ri, tj] -= 1
        else:
            # move aleatorio classico
            k = rng.randrange(n_mapas)
            ri = rng.randrange(R)
            tipo = rng.random()
            if tipo < 0.55:
                com = [tj for tj in range(T) if Xn[k, ri, tj] > 0]
                if not com:
                    return None
                t1 = rng.choice(com)
                t2 = rng.randrange(T)
                if t1 == t2:
                    return None
                Xn[k, ri, t1] -= 1
                Xn[k, ri, t2] += 1
            elif tipo < 0.75:
                t2 = rng.randrange(T)
                Xn[k, ri, t2] += 1
                if comprimentos(Xn)[k] > mesa + 1e-9:
                    return None
            elif tipo < 0.9:
                com = [tj for tj in range(T) if Xn[k, ri, tj] > 0]
                if not com:
                    return None
                Xn[k, ri, rng.choice(com)] -= 1
            else:
                if R < 2:
                    return None
                rj = rng.randrange(R)
                if rj == ri:
                    return None
                com = [tj for tj in range(T) if Xn[k, ri, tj] > 0]
                if not com:
                    return None
                Xn[k, ri, rng.choice(com)] -= 1
                Xn[k, rj, rng.randrange(T)] += 1
                if comprimentos(Xn)[k] > mesa + 1e-9:
                    return None
        if int(Xn[k].sum()) < 1:
            return None
        return Xn

    encontradas = []
    MOVES_POR_ITER = 16
    # Semente com slot fisicamente impossivel (acima da mesa) nao entra: os
    # moves validam a mesa, mas um slot invalido HERDADO nunca seria corrigido
    seeds_X = [X for X in (estado_para_X(s) for s in seeds)
               if not (comprimentos(X) > mesa + 1e-9).any()]
    if not seeds_X:
        return []

    # fatias de tempo por semente (round-robin em ciclos)
    inicio = _t.time()
    total = max(0.5, deadline - inicio)
    fatia = max(2.0, total / max(1, len(seeds_X)))

    # deteccao de estagnacao: melhor violacao global e quando ela melhorou
    melhor_V_global = [float("inf")]
    t_melhora = [inicio]

    def _estagnado():
        if encontradas:
            # ja temos solucao: da so mais um pouco de tempo por outra opcao
            return _t.time() - t_melhora[0] > max(6.0, estagnacao_s / 2)
        # perto de viavel (violacao <= 3): insiste o dobro antes de desistir
        janela = estagnacao_s * (2.0 if melhor_V_global[0] <= 3 else 1.0)
        return _t.time() - t_melhora[0] > janela

    ciclo = 0
    while _t.time() < deadline and len(encontradas) < max_solucoes:
        if _estagnado():
            break
        progrediu = False
        for si, seed_X in enumerate(seeds_X):
            if _t.time() >= deadline or len(encontradas) >= max_solucoes or _estagnado():
                break
            fim_fatia = min(deadline, _t.time() + fatia)
            X = seed_X.copy()
            if ciclo > 0:
                # ciclos seguintes: perturba a semente para diversificar
                _, _, _, piores0 = av.avaliar(X)
                for _ in range(2 + ciclo):
                    nv = gerar_move(X, piores0)
                    if nv is not None:
                        X = nv
            V, D, folhas, piores = av.avaliar(X)
            if V < melhor_V_global[0]:
                melhor_V_global[0] = V
                t_melhora[0] = _t.time()
            plato = 0
            while _t.time() < fim_fatia and not _estagnado():
                progrediu = True
                if V == 0:
                    kx = chave(X)
                    if kx not in ja_encontradas:
                        ja_encontradas.add(kx)
                        encontradas.append((X_para_estado(X),
                                            {c: f.copy() for c, f in folhas.items()}))
                        t_melhora[0] = _t.time()
                    if len(encontradas) >= max_solucoes:
                        break
                    for _ in range(4):
                        nv = gerar_move(X, piores)
                        if nv is not None:
                            X = nv
                    V, D, folhas, piores = av.avaliar(X, fs_pai=folhas)
                    continue
                melhor = None
                for _ in range(MOVES_POR_ITER):
                    cand = gerar_move(X, piores)
                    if cand is None:
                        continue
                    V2, D2, f2, p2 = av.avaliar(cand, fs_pai=folhas)
                    if melhor is None or (V2, D2) < (melhor[0], melhor[1]):
                        melhor = (V2, D2, cand, f2, p2)
                if melhor is None:
                    break
                V2, D2, cand, f2, p2 = melhor
                if (V2, D2) < (V, D):
                    X, V, D, folhas, piores = cand, V2, D2, f2, p2
                    plato = 0
                    if V < melhor_V_global[0]:
                        melhor_V_global[0] = V
                        t_melhora[0] = _t.time()
                else:
                    # aceita o melhor vizinho mesmo piorando (escapa do plato),
                    # mas desiste da semente se empacar por muito tempo
                    X, V, D, folhas, piores = cand, V2, D2, f2, p2
                    plato += 1
                    if plato >= 25:
                        break
        ciclo += 1
        if not progrediu:
            break
    return encontradas
