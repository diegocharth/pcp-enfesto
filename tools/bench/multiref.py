"""
Bancada multi-ref: todos os PARES das referencias do corpus.

Como a tela faz: calcula cada referencia sozinha (motor exato), e cada par com
teto = soma dos individuais - 1 (combinar so vale se usar menos enfestos) e o
tempo de um par na primeira vez (120 s). Valida cada plano combinado com o
validador independente e compara com o gabarito, se existir
(dados/ordens/bench_gabarito_multiref.json, gerado por gabarito_cpsat.py --multiref).

Uso:
    python tools/bench/multiref.py                 # as referencias 5c do corpus
    python tools/bench/multiref.py --timeout 60 --processos 15
"""
import argparse
import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(AQUI))
for p in (BASE, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

import corpus      # noqa: E402
import validador   # noqa: E402

GABARITO_MR = os.path.join(BASE, "dados", "ordens", "bench_gabarito_multiref.json")


def referencias(nomes=None):
    """Referencias do multi-ref: os casos de 5 cores do corpus privado (mesmas
    regras especiais; o multi-ref usa UMA regra para todas)."""
    casos = [c for c in corpus.carregar() if "-5c-" in c["nome"]]
    if nomes:
        casos = [c for c in casos if any(n in c["nome"] for n in nomes)]
    # mesma grade com regra diferente (variacao de teste) entra uma vez so
    vistos, out = set(), []
    for c in casos:
        chave = json.dumps(c["grade"], sort_keys=True)
        if chave not in vistos:
            vistos.add(chave)
            out.append(c)
    return out


def chave_par(nomes):
    return "+".join(sorted(nomes))


def _individual(c):
    from engine.solver_exato import resolver_exato
    from engine.tolerancia import calcular_limites_grade
    cfg = dict(c["config"], num_opcoes_saida=1)
    lim = calcular_limites_grade(c["grade"], c["tamanhos"], cfg, c.get("regras") or {})
    sols = resolver_exato(c["grade"], c["tamanhos"], lim, cfg, None, timeout_s=120)
    return c["nome"], (sols[0]["n_mapas"] if sols else None)


def _par(args):
    a, b, cap, timeout = args
    from engine.solver_multiref import resolver_multiref
    from engine.tolerancia import calcular_limites_grade
    tams = a["tamanhos"]
    regras = a.get("regras") or {}
    cfg = dict(a["config"], num_opcoes_saida=2)
    refs = []
    for c in (a, b):
        cfg_r = dict(c["config"])
        refs.append({"nome": c["nome"], "grade": c["grade"], "consumo": c["config"]["consumo_peca_m"],
                     "limites": calcular_limites_grade(c["grade"], tams, cfg_r, regras)})
    ro = {}
    t0 = time.time()
    sols = resolver_multiref(refs, tams, cfg, None, timeout_s=timeout, n_mapas_max=cap, resume_out=ro)
    tempo = time.time() - t0
    erros = [e for s in sols for e in validador.validar_multiref(s, tams, cfg)]
    return {"par": chave_par([a["nome"], b["nome"]]), "cap": cap, "tempo": round(tempo, 1),
            "status": ro.get("status"), "convergiu": ro.get("convergiu"),
            "n": sols[0]["n_mapas"] if sols else None,
            "desvio": sols[0]["desvio_total"] if sols else None, "erros": erros}


def main():
    ap = argparse.ArgumentParser(description="Bancada multi-ref (pares).")
    ap.add_argument("nomes", nargs="*")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--processos", type=int, default=15)
    ap.add_argument("--json")
    a = ap.parse_args()
    refs = referencias(a.nomes)
    print(f"{len(refs)} referencia(s): {', '.join(r['nome'] for r in refs)}")
    with ProcessPoolExecutor(max_workers=min(a.processos, len(refs))) as ex:
        indiv = dict(ex.map(_individual, refs))
    print("individuais (motor exato):", indiv)
    tarefas = []
    for x, y in itertools.combinations(refs, 2):
        cap = indiv[x["nome"]] + indiv[y["nome"]] - 1
        tarefas.append((x, y, cap, a.timeout))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.processos) as ex:
        res = list(ex.map(_par, tarefas))
    gab = {}
    if os.path.isfile(GABARITO_MR):
        with open(GABARITO_MR, encoding="utf-8") as f:
            gab = json.load(f)
    invalidos = 0
    print(f"\n{'par':48s} cap | resultado                         | gabarito")
    for r in res:
        g = gab.get(r["par"])
        txt = (f"{r['n']} enf. desvio {r['desvio']:3d}" if r["n"] else f"sem combinacao ({r['status']})")
        txt += f" {r['tempo']:5.1f}s" + ("" if r["convergiu"] else " CORTADO")
        gt = "-"
        if g:
            gt = (f"{g['n']} enf. desvio {g['desvio']}" if g.get("n") else "nao combina") \
                 + ("" if g.get("otimo") else " (nao provado)")
        nota = ""
        if r["erros"]:
            invalidos += 1
            nota = f"  <- INVALIDO: {r['erros'][0]}"
        elif g and g.get("n") and r["n"]:
            if (r["n"], r["desvio"]) == (g["n"], g["desvio"]):
                nota = "  <- = gabarito"
            elif r["n"] > g["n"]:
                nota = "  <- MAIS ENFESTOS que o gabarito"
            elif r["desvio"] > g["desvio"] and r["n"] == g["n"]:
                nota = f"  <- desvio +{r['desvio'] - g['desvio']} sobre o gabarito"
        elif g and g.get("n") and not r["n"]:
            nota = "  <- FALSO NEGATIVO (gabarito combina)"
        print(f"{r['par']:48s} {r['cap']:3d} | {txt:33s} | {gt}{nota}")
    print(f"\nTempo de parede dos pares: {time.time() - t0:.0f}s | invalidos: {invalidos}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"individuais": indiv, "pares": res}, f, ensure_ascii=False, indent=1)
    return 1 if invalidos else 0


if __name__ == "__main__":
    sys.exit(main())
