"""Etapa 4: folhas exatas do enfesto combinado (engine/multiref_exato.py) e
polimento do desvio na busca local do multi-ref."""
import itertools
import os
import random
import sys

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools", "bench"))

from engine.multiref_exato import preparar, folhas_exatas, TRUNCOU
from engine.solver_multiref import resolver_multiref
from engine.tolerancia import calcular_limites_grade
import validador

TAMS = ["P", "M"]
CFG = {"mesa_comprimento_m": 10.0, "limite_folhas_padrao": 6, "num_opcoes_saida": 2,
       "desvio_absoluto_padrao": 3, "desvio_percentual_padrao": 50, "criterio_combinacao": "MAX"}


def _dims(refs, cores):
    dims = {}
    for cor in cores:
        ct, cg, cl = [], [], []
        for ri, r in enumerate(refs):
            for t in TAMS:
                ct.append((ri, t))
                cg.append(r["grade"][cor].get(t, 0))
                cl.append(r["limites"][cor][t])
        dims[cor] = (ct, cg, cl)
    return dims


def _forca_bruta(combo, n, cores, dims, F):
    """Menor desvio total por enumeracao ingenua de todas as folhas."""
    melhor = None
    por_cor = []
    for cor in cores:
        ct, cg, cl = dims[cor]
        pts = []
        for f in itertools.product(range(F + 1), repeat=n):
            dev, ok = 0, True
            for d, (ri, t) in enumerate(ct):
                cut = sum(f[k] * combo[k][ri].get(t, 0) for k in range(n))
                diff = cut - cg[d]
                if diff < cl[d][0] or diff > cl[d][1]:
                    ok = False
                    break
                dev += abs(diff)
            if ok:
                pts.append((dev, f))
        if not pts:
            return None
        por_cor.append(pts)
    for esc in itertools.product(*por_cor):
        if all(sum(e[1][k] for e in esc) <= F for k in range(n)):
            dev = sum(e[0] for e in esc)
            melhor = dev if melhor is None else min(melhor, dev)
    return melhor


def test_folhas_exatas_igual_a_forca_bruta_e_folha_compartilhada():
    rnd = random.Random(4)
    cores = ["AZUL", "ROSA"]
    conferidos = 0
    for _ in range(900):
        refs = []
        for ri in range(2):
            g = {c: {t: rnd.randint(0, 9) for t in TAMS} for c in cores}
            refs.append({"grade": g, "limites": calcular_limites_grade(g, TAMS, CFG, {})})
        n = rnd.choice([1, 2])
        combo = [tuple({t: rnd.randint(0, 2) for t in TAMS} for _ in range(2)) for _ in range(n)]
        if rnd.random() < 0.3 and n == 2:
            combo[1] = combo[0]                      # enfestos identicos
        dims = _dims(refs, cores)
        r = folhas_exatas(combo, n, cores, dims, preparar(cores, dims), CFG["limite_folhas_padrao"])
        ref = _forca_bruta(combo, n, cores, dims, CFG["limite_folhas_padrao"])
        assert r != TRUNCOU
        if ref is None:
            assert r is None
            continue
        conferidos += 1
        assert r is not None, "forca bruta achou folhas e o metodo exato nao"
        dev = 0
        for cor in cores:
            ct, cg, cl = dims[cor]
            for d, (ri, t) in enumerate(ct):
                diff = sum(r[cor][k] * combo[k][ri].get(t, 0) for k in range(n)) - cg[d]
                assert cl[d][0] <= diff <= cl[d][1]
                dev += abs(diff)
        assert dev == ref
        for k in range(n):
            assert sum(r[c][k] for c in cores) <= CFG["limite_folhas_padrao"]
    assert conferidos >= 30


def _ref(nome, grade, consumo):
    cfg = dict(CFG, limite_folhas_padrao=70, desvio_absoluto_padrao=4, desvio_percentual_padrao=20,
               consumo_peca_m=consumo)
    tams = ["PP", "P", "M", "G"]
    return {"nome": nome, "grade": grade, "consumo": consumo,
            "limites": calcular_limites_grade(grade, tams, cfg, {})}


def test_multiref_devolve_plano_valido_com_folha_compartilhada():
    tams = ["PP", "P", "M", "G"]
    cfg = dict(CFG, limite_folhas_padrao=70, desvio_absoluto_padrao=4, desvio_percentual_padrao=20)
    refs = [_ref("A", {"BLUES": {"PP": 10, "P": 12, "M": 6, "G": 2}}, 1.0645),
            _ref("B", {"BLUES": {"PP": 8, "P": 10, "M": 5, "G": 2},
                       "JAZZ": {"PP": 6, "P": 7, "M": 4, "G": 1}}, 1.4)]
    sols = resolver_multiref(refs, tams, cfg, None, timeout_s=40, n_mapas_max=3)
    assert sols
    for s in sols:
        assert validador.validar_multiref(s, tams, cfg) == []
