"""
Bancada de comparacao A x B dos motores single-ref.

Roda o motor classico (engine.solver) e o motor exato (engine.solver_exato) em
todos os casos do corpus, valida cada solucao com o validador independente e
compara com o gabarito exato quando ele existe.

Uso:
    python tools/bench/rodar.py                  # todos os casos, 2 motores
    python tools/bench/rodar.py --so-exato       # so o motor novo (rapido)
    python tools/bench/rodar.py --timeout 60 --processos 6 --com-historico

Sai com codigo 1 se o motor exato violar alguma restricao ou ficar PIOR que o
classico em algum caso (enfestos, depois desvio, depois pecas/mapa).
"""
import argparse
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


def _fingerprint(grade, tamanhos):
    """Copia da regra de main._fingerprint_grade (historico por proporcao)."""
    gt = {t: sum(grade[c].get(t, 0) for c in grade) for t in tamanhos}
    total = sum(gt.values())
    if total == 0:
        return "vazio"
    partes = []
    for t in tamanhos:
        pct = round(gt[t] / total * 20) * 5
        if pct > 0:
            partes.append(f"{t}={pct}")
    return ",".join(partes)


def _rodar_um(args):
    """Executa UM motor em UM caso (roda num processo separado)."""
    caso, motor, timeout, com_historico = args
    from engine.tolerancia import calcular_limites_grade
    cfg = dict(caso["config"])
    cfg.setdefault("num_opcoes_saida", 2)
    grade, tams = caso["grade"], caso["tamanhos"]
    limites = calcular_limites_grade(grade, tams, cfg, caso.get("regras") or {})
    historicos = None
    if com_historico:
        arq = os.path.join(BASE, "dados", "historico_solucoes.json")
        if os.path.isfile(arq):
            with open(arq, encoding="utf-8") as f:
                historicos = (json.load(f).get(_fingerprint(grade, tams)) or {}).get("mapas")
    if motor == "exato":
        from engine.solver_exato import resolver_exato as fn
    else:
        from engine.solver import resolver as fn
    resume = {}
    t0 = time.time()
    sols = fn(grade, tams, limites, cfg, None, timeout_s=timeout,
              historicos=historicos, resume_out=resume)
    tempo = time.time() - t0
    saida = {"caso": caso["nome"], "motor": motor, "tempo": round(tempo, 1),
             "erros": [], "opcoes": []}
    for s in sols:
        saida["erros"].extend(validador.validar(s, grade, tams, limites, cfg))
        r = s["resumo"]
        saida["opcoes"].append({
            "n": r["n_mapas"], "desvio": r["desvio_total"],
            "pm": r["media_pecas_mapa"], "folhas": r["total_folhas"],
            "prova": r.get("prova", "-"), "chave": list(validador.chave_ranking(s))})
    return saida


def _fmt(res):
    if not res:
        return "(nao rodou)"
    if not res["opcoes"]:
        return f"sem solucao ({res['tempo']}s)"
    o = res["opcoes"][0]
    return f"{o['n']} enf. desvio {o['desvio']:3d} {o['pm']:.1f} pc/mapa {res['tempo']:6.1f}s"


def main():
    ap = argparse.ArgumentParser(description="Compara os motores single-ref.")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--processos", type=int, default=max(1, min(8, (os.cpu_count() or 4) - 1)))
    ap.add_argument("--so-exato", action="store_true")
    ap.add_argument("--so-publico", action="store_true")
    ap.add_argument("--com-historico", action="store_true",
                    help="usa dados/historico_solucoes.json como a producao faz")
    ap.add_argument("--json", help="grava o resultado completo neste arquivo")
    a = ap.parse_args()

    casos = corpus.carregar(so_publico=a.so_publico)
    gab = corpus.carregar_gabarito()
    motores = ["exato"] if a.so_exato else ["classico", "exato"]
    tarefas = [(c, m, a.timeout, a.com_historico) for c in casos for m in motores]
    print(f"{len(casos)} caso(s) x {len(motores)} motor(es) | timeout {a.timeout}s | "
          f"{a.processos} processo(s) | historico: {'sim' if a.com_historico else 'nao'}")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.processos) as ex:
        resultados = list(ex.map(_rodar_um, tarefas))
    por = {(r["caso"], r["motor"]): r for r in resultados}

    falhas = 0
    larg = max(len(c["nome"]) for c in casos)
    print(f"\n{'caso':{larg}s} | {'classico':44s} | {'exato':44s} | prova       | gabarito")
    for c in casos:
        rc, re_ = por.get((c["nome"], "classico")), por.get((c["nome"], "exato"))
        linha = f"{c['nome']:{larg}s} | {_fmt(rc):44s} | {_fmt(re_):44s} | "
        linha += f"{(re_['opcoes'][0]['prova'] if re_ and re_['opcoes'] else '-'):11s} | "
        g = gab.get(corpus.assinatura_caso(c))
        notas = []
        if g:
            linha += f"{g['n']} enf. desvio {g['desvio']}" + ("" if g.get("otimo") else " (nao provado)")
            if re_ and re_["opcoes"]:
                o = re_["opcoes"][0]
                if (o["n"], o["desvio"]) == (g["n"], g["desvio"]):
                    notas.append("= gabarito")
                elif (o["n"], o["desvio"]) > (g["n"], g["desvio"]):
                    notas.append("ACIMA do gabarito")
                else:
                    notas.append("MELHOR que o gabarito (conferir)")
        else:
            linha += "-"
        for r in (rc, re_):
            if r and r["erros"]:
                falhas += 1
                notas.append(f"{r['motor'].upper()} INVALIDO: {r['erros'][0]}")
        if rc and rc["opcoes"]:
            if not (re_ and re_["opcoes"]):
                falhas += 1
                notas.append("EXATO sem solucao onde o classico achou")
            elif re_["opcoes"][0]["chave"] > rc["opcoes"][0]["chave"]:
                falhas += 1
                notas.append("EXATO PIOR que o classico")
            elif re_["opcoes"][0]["chave"] < rc["opcoes"][0]["chave"]:
                notas.append("exato melhor")
        print(linha + ("  <- " + "; ".join(notas) if notas else ""))
    print(f"\nTempo total de parede: {time.time() - t0:.0f}s | "
          + ("OK: nenhuma regressao." if not falhas else f"{falhas} PROBLEMA(S)."))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=1)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
