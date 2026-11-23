"""
Bancada de comparacao -- gabarito exato com OR-Tools (CP-SAT).

SO PARA DESENVOLVIMENTO: o OR-Tools nao e dependencia do sistema e nao vai
para a fabrica. Aqui ele serve de segunda opiniao independente: resolve cada
caso do corpus ate o otimo provado (menor numero de enfestos e, nesse numero,
menor desvio) e grava em dados/ordens/bench_gabarito.json (fora do git).

Uso:
    pip install ortools            # uma vez, na maquina de desenvolvimento
    python tools/bench/gabarito_cpsat.py --timeout 120
"""
import argparse
import json
import math
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(AQUI))
for p in (BASE, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

import corpus  # noqa: E402


def _modelo(cp_model, grade, tams, lim, P, F, n):
    m = cp_model.CpModel()
    cores = list(grade)
    T = len(tams)
    M = [[m.NewIntVar(0, P, "") for _ in range(T)] for _ in range(n)]
    for k in range(n):
        m.Add(sum(M[k]) >= 1)
        m.Add(sum(M[k]) <= P)
    Fv = {c: [m.NewIntVar(0, F, "") for _ in range(n)] for c in cores}
    for k in range(n):
        m.Add(sum(Fv[c][k] for c in cores) <= F)
    devs = []
    for c in cores:
        for ti, t in enumerate(tams):
            g = grade[c].get(t, 0)
            lo, hi = lim[c][t]
            if g + hi < 0:
                m.Add(M[0][0] < 0)          # impossivel
                continue
            prods = []
            for k in range(n):
                p = m.NewIntVar(0, F * P, "")
                m.AddMultiplicationEquality(p, [Fv[c][k], M[k][ti]])
                prods.append(p)
            cut = m.NewIntVar(max(0, g + lo), g + hi, "")
            m.Add(cut == sum(prods))
            d = m.NewIntVar(0, max(abs(lo), abs(hi)), "")
            m.AddAbsEquality(d, cut - g)
            devs.append(d)
    chaves = []
    for k in range(n):                      # quebra de simetria entre enfestos
        ch = m.NewIntVar(0, (P + 1) ** T, "")
        m.Add(ch == sum(M[k][ti] * (P + 1) ** ti for ti in range(T)))
        chaves.append(ch)
    for k in range(n - 1):
        m.Add(chaves[k] >= chaves[k + 1])
    m.Minimize(sum(devs))
    return m


def resolver_caso(caso, timeout, workers):
    from ortools.sat.python import cp_model
    from engine.tolerancia import calcular_limites_grade
    cfg = caso["config"]
    grade, tams = caso["grade"], caso["tamanhos"]
    lim = calcular_limites_grade(grade, tams, cfg, caso.get("regras") or {})
    P = int(math.floor(cfg["mesa_comprimento_m"] / cfg["consumo_peca_m"]))
    F = int(cfg["limite_folhas_padrao"])
    folhas = sum(-(-sum(max(0, grade[c].get(t, 0) + lim[c][t][0]) for t in tams) // P)
                 for c in grade)
    n = max(1, -(-folhas // F))
    piso_provado = True
    while n <= 8:
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = timeout
        s.parameters.num_search_workers = workers
        st = s.Solve(_modelo(cp_model, grade, tams, lim, P, F, n))
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {"n": n, "desvio": int(s.ObjectiveValue()),
                    "otimo": bool(st == cp_model.OPTIMAL and piso_provado)}
        if st != cp_model.INFEASIBLE:
            piso_provado = False            # nao provou que n e impossivel
        n += 1
    return None


def main():
    ap = argparse.ArgumentParser(description="Gabarito exato (OR-Tools, so dev).")
    ap.add_argument("--timeout", type=int, default=120, help="segundos por nivel")
    ap.add_argument("--workers", type=int, default=max(1, min(16, (os.cpu_count() or 4) - 2)))
    a = ap.parse_args()
    try:
        import ortools  # noqa: F401
    except ImportError:
        print("OR-Tools nao instalado. Rode: pip install ortools  (so na maquina de dev)")
        return 2
    gab = corpus.carregar_gabarito()
    for caso in corpus.carregar():
        sig = corpus.assinatura_caso(caso)
        if gab.get(sig, {}).get("otimo"):
            print(f"{caso['nome']:40s} ja no gabarito: {gab[sig]}")
            continue
        t0 = time.time()
        r = resolver_caso(caso, a.timeout, a.workers)
        if r:
            r["nome"] = caso["nome"]
            gab[sig] = r
        print(f"{caso['nome']:40s} {r}  ({time.time() - t0:.0f}s)")
        os.makedirs(os.path.dirname(corpus.GABARITO), exist_ok=True)
        tmp = corpus.GABARITO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(gab, f, ensure_ascii=False, indent=1)
        os.replace(tmp, corpus.GABARITO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
