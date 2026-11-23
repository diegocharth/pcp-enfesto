"""
Bancada -- opcoes que o motor exato devolve, pelo CAMINHO DE PRODUCAO.

Roda cada caso do corpus por engine.paralelo.executar_solve("exato"), isto e,
com a varredura fatiada entre os processos do pool, exatamente como o servidor
faz. Mostra todas as opcoes (menos enfestos, 1 enfesto a mais, mapas cheios),
o selo de prova e o tempo, e valida cada plano com o validador independente.

Uso:
    python tools/bench/opcoes.py                 # todos os casos
    python tools/bench/opcoes.py isadora 5c      # so casos cujo nome contem o texto
    python tools/bench/opcoes.py --timeout 60 --opcoes 3
"""
import argparse
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(AQUI))
for p in (BASE, AQUI):
    if p not in sys.path:
        sys.path.insert(0, p)

import corpus      # noqa: E402
import validador   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Opcoes do motor exato pelo pool.")
    ap.add_argument("filtros", nargs="*", help="trechos do nome do caso")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--opcoes", type=int, default=2)
    a = ap.parse_args()

    from engine import paralelo
    from engine.tolerancia import calcular_limites_grade
    casos = [c for c in corpus.carregar()
             if not a.filtros or any(f in c["nome"] for f in a.filtros)]
    gab = corpus.carregar_gabarito()
    print(f"{len(casos)} caso(s) | {paralelo.n_workers()} processo(s) no pool | "
          f"timeout {a.timeout}s")
    falhas = 0
    try:
        for c in casos:
            cfg = dict(c["config"], num_opcoes_saida=a.opcoes)
            lim = calcular_limites_grade(c["grade"], c["tamanhos"], cfg, c.get("regras") or {})
            t0 = time.time()
            sols, _ = paralelo.executar_solve("exato", dict(
                grade=c["grade"], tamanhos=c["tamanhos"], limites=lim, config=cfg,
                timeout_s=a.timeout), lambda m: None)
            g = gab.get(corpus.assinatura_caso(c))
            print(f"\n{c['nome']}  ({time.time() - t0:.1f}s)"
                  + (f"  gabarito: {g['n']} enf. desvio {g['desvio']}" if g else ""))
            for i, s in enumerate(sols, 1):
                r = s["resumo"]
                erros = validador.validar(s, c["grade"], c["tamanhos"], lim, cfg)
                falhas += bool(erros)
                print(f"   {i}. {r['rotulo']:26s} {r['n_mapas']} enf. desvio {r['desvio_total']:3d}  "
                      f"{r['media_pecas_mapa']:4} pc/mapa  {r['prova']:11s} {r['comparacao']}"
                      + (f"  INVALIDO: {erros[0]}" if erros else ""))
    finally:
        paralelo.encerrar()
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
