"""
Bancada de comparacao -- gabarito exato com OR-Tools (CP-SAT).

SO PARA DESENVOLVIMENTO: o OR-Tools nao e dependencia do sistema e nao vai
para a fabrica. Aqui ele serve de segunda opiniao independente: resolve cada
caso do corpus ate o otimo provado (menor numero de enfestos e, nesse numero,
menor desvio) e grava em dados/ordens/bench_gabarito.json (fora do git).

Uso:
    pip install ortools            # uma vez, na maquina de desenvolvimento
    python tools/bench/gabarito_cpsat.py --timeout 120
    python tools/bench/gabarito_cpsat.py --multiref --timeout 90   # pares do multi-ref
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


ESC = 10000      # comprimentos em decimos de milimetro (consumos tem ate 4 casas)


def _modelo_multiref(cp_model, refs, tams, cfg, n):
    """Enfesto combinado: por enfesto, um mapa por referencia (soma dos
    comprimentos <= mesa) e UMA folha por cor, compartilhada pelas referencias."""
    from engine.tolerancia import calcular_limites
    mesa = int(round(cfg["mesa_comprimento_m"] * ESC))
    F = int(cfg["limite_folhas_padrao"])
    T, R = len(tams), len(refs)
    cores = []
    for r in refs:
        for c in r["grade"]:
            if c not in cores:
                cores.append(c)
    m = cp_model.CpModel()
    cons = [int(round(r["consumo"] * ESC)) for r in refs]
    Pr = [mesa // c for c in cons]
    M = [[[m.NewIntVar(0, Pr[ri], "") for _ in range(T)] for ri in range(R)] for _ in range(n)]
    for k in range(n):
        m.Add(sum(cons[ri] * sum(M[k][ri]) for ri in range(R)) <= mesa)
        m.Add(sum(sum(M[k][ri]) for ri in range(R)) >= 1)
    Fv = {c: [m.NewIntVar(0, F, "") for _ in range(n)] for c in cores}
    for k in range(n):
        m.Add(sum(Fv[c][k] for c in cores) <= F)
    devs = []
    for c in cores:
        for ri, r in enumerate(refs):
            for ti, t in enumerate(tams):
                if c in r["grade"]:
                    g = r["grade"][c].get(t, 0)
                    lo, hi = r["limites"][c][t]
                else:          # mesma regra do solver: cor que a ref nao pediu, grade 0
                    g = 0
                    lo, hi = calcular_limites(0.0, t, cfg, None)
                if g + hi < 0:
                    m.Add(M[0][0][0] < 0)
                    continue
                prods = []
                for k in range(n):
                    p = m.NewIntVar(0, F * Pr[ri], "")
                    m.AddMultiplicationEquality(p, [Fv[c][k], M[k][ri][ti]])
                    prods.append(p)
                cut = m.NewIntVar(max(0, g + lo), g + hi, "")
                m.Add(cut == sum(prods))
                d = m.NewIntVar(0, max(abs(lo), abs(hi)), "")
                m.AddAbsEquality(d, cut - g)
                devs.append(d)
    B = max(Pr) + 1
    chaves = []
    for k in range(n):
        ch = m.NewIntVar(0, B ** (R * T), "")
        m.Add(ch == sum(M[k][ri][ti] * B ** (ri * T + ti) for ri in range(R) for ti in range(T)))
        chaves.append(ch)
    for k in range(n - 1):
        m.Add(chaves[k] >= chaves[k + 1])
    m.Minimize(sum(devs))
    return m


def gabarito_multiref(timeout, workers):
    """Pares das referencias da bancada multi-ref, com o mesmo teto da tela."""
    import itertools
    from ortools.sat.python import cp_model
    from engine.tolerancia import calcular_limites_grade
    from engine.multiref_pool import _piso_capacidade
    import multiref
    refs = multiref.referencias()
    indiv = {}
    for c in refs:
        g = corpus.carregar_gabarito().get(corpus.assinatura_caso(c))
        indiv[c["nome"]] = g["n"] if g else multiref._individual(c)[1]
    gab = {}
    if os.path.isfile(multiref.GABARITO_MR):
        with open(multiref.GABARITO_MR, encoding="utf-8") as f:
            gab = json.load(f)
    for x, y in itertools.combinations(refs, 2):
        chave = multiref.chave_par([x["nome"], y["nome"]])
        if chave in gab and gab[chave].get("otimo"):
            print(f"{chave:48s} ja no gabarito: {gab[chave]}")
            continue
        tams, regras, cfg = x["tamanhos"], x.get("regras") or {}, dict(x["config"])
        rs = [{"nome": c["nome"], "grade": c["grade"], "consumo": c["config"]["consumo_peca_m"],
               "limites": calcular_limites_grade(c["grade"], tams, dict(c["config"]), regras)}
              for c in (x, y)]
        cap = indiv[x["nome"]] + indiv[y["nome"]] - 1
        piso = _piso_capacidade(rs, tams, cfg["mesa_comprimento_m"], cfg["limite_folhas_padrao"])[0]
        t0 = time.time()
        r = {"n": None, "desvio": None, "otimo": True, "cap": cap}
        for n in range(piso, cap + 1):
            s = cp_model.CpSolver()
            s.parameters.max_time_in_seconds = timeout
            s.parameters.num_search_workers = workers
            st = s.Solve(_modelo_multiref(cp_model, rs, tams, cfg, n))
            if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                r.update(n=n, desvio=int(s.ObjectiveValue()),
                         otimo=bool(r["otimo"] and st == cp_model.OPTIMAL))
                break
            if st != cp_model.INFEASIBLE:
                r["otimo"] = False
        gab[chave] = r
        print(f"{chave:48s} {r}  ({time.time() - t0:.0f}s)", flush=True)
        os.makedirs(os.path.dirname(multiref.GABARITO_MR), exist_ok=True)
        tmp = multiref.GABARITO_MR + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(gab, f, ensure_ascii=False, indent=1)
        os.replace(tmp, multiref.GABARITO_MR)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Gabarito exato (OR-Tools, so dev).")
    ap.add_argument("--timeout", type=int, default=120, help="segundos por nivel")
    ap.add_argument("--workers", type=int, default=max(1, min(16, (os.cpu_count() or 4) - 2)))
    ap.add_argument("--multiref", action="store_true", help="gabarito dos pares do multi-ref")
    a = ap.parse_args()
    try:
        import ortools  # noqa: F401
    except ImportError:
        print("OR-Tools nao instalado. Rode: pip install ortools  (so na maquina de dev)")
        return 2
    if a.multiref:
        return gabarito_multiref(a.timeout, a.workers)
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
