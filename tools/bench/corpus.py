"""
Bancada de comparacao -- conjunto de casos (corpus).

Dois conjuntos:
  - PUBLICO (neste arquivo): grades que ja estao no repositorio.
  - PRIVADO (dados/ordens/bench_corpus.json): OPs reais da fabrica. A pasta
    dados/ordens/ esta no .gitignore, entao as OPs nunca vao para o GitHub.

Para montar o conjunto privado a partir do que ja foi calculado nesta maquina:
    python tools/bench/corpus.py --importar-cache
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS_PRIVADO = os.path.join(BASE, "dados", "ordens", "bench_corpus.json")
GABARITO = os.path.join(BASE, "dados", "ordens", "bench_gabarito.json")

_CHAVES_CFG = ("consumo_peca_m", "mesa_comprimento_m", "limite_folhas_padrao",
               "desvio_absoluto_padrao", "desvio_percentual_padrao",
               "criterio_combinacao")

_CFG_PADRAO = {"mesa_comprimento_m": 10.0, "limite_folhas_padrao": 70,
               "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
               "criterio_combinacao": "MIN"}

PUBLICO = [
    {"nome": "blazer-isadora", "tamanhos": ["PP", "P", "M", "G"], "regras": {},
     "config": dict(_CFG_PADRAO, consumo_peca_m=1.0645),
     "grade": {
         "BLUES":   {"PP": 41, "P": 45, "M": 25, "G": 10},
         "BOSSA":   {"PP": 19, "P": 20, "M": 13, "G": 2},
         "JAZZ":    {"PP": 44, "P": 55, "M": 30, "G": 11},
         "PRETO":   {"PP": 47, "P": 54, "M": 31, "G": 12},
         "SAMBA":   {"PP": 39, "P": 37, "M": 18, "G": 5},
         "VALSA":   {"PP": 45, "P": 50, "M": 23, "G": 5},
         "VANILLA": {"PP": 49, "P": 51, "M": 27, "G": 9}}},
    {"nome": "duas-cores-pequena", "tamanhos": ["PP", "P", "M", "G"], "regras": {},
     "config": dict(_CFG_PADRAO, consumo_peca_m=1.0645),
     "grade": {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2},
               "ROSA": {"PP": 8, "P": 9, "M": 5, "G": 1}}},
    {"nome": "uma-cor-g-nao-cresce", "tamanhos": ["PP", "P", "M", "G"],
     "regras": {"G": {"hi": 0}},
     "config": dict(_CFG_PADRAO, consumo_peca_m=1.87),
     "grade": {"UNICA": {"PP": 82, "P": 104, "M": 62, "G": 17}}},
]


def assinatura_caso(caso):
    """Identidade estavel de um caso (para casar com o gabarito)."""
    import hashlib
    canon = json.dumps({k: caso[k] for k in ("grade", "tamanhos", "regras", "config")},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:12]


def carregar(so_publico=False):
    """Lista de casos: publicos + privados (se o arquivo existir)."""
    casos = [dict(c) for c in PUBLICO]
    if not so_publico and os.path.isfile(CORPUS_PRIVADO):
        with open(CORPUS_PRIVADO, encoding="utf-8") as f:
            casos.extend(json.load(f))
    return casos


def carregar_gabarito():
    if not os.path.isfile(GABARITO):
        return {}
    with open(GABARITO, encoding="utf-8") as f:
        return json.load(f)


def importar_do_cache(caminho_cache=None, min_pecas=60):
    """Extrai as grades single-ref guardadas em dados/cache_planos.json e grava
    o conjunto privado. Nomes neutros (a referencia real nao e gravada)."""
    caminho_cache = caminho_cache or os.path.join(BASE, "dados", "cache_planos.json")
    with open(caminho_cache, encoding="utf-8") as f:
        cache = json.load(f)
    casos, vistos = [], set()
    for sig, entrada in cache.items():
        r = entrada.get("resultado") or {}
        if r.get("tipo") == "multiref" or "grade" not in r:
            continue
        grade = r["grade"]
        if sum(sum(v.values()) for v in grade.values()) < min_pecas:
            continue
        cfg = {k: r.get("config", {}).get(k) for k in _CHAVES_CFG}
        if any(v is None for v in cfg.values()):
            continue
        regras = r.get("regras_especiais") or {}
        chave = json.dumps([grade, cfg, regras], sort_keys=True)
        if chave in vistos:
            continue
        vistos.add(chave)
        casos.append({"nome": f"op-{sig[:6]}-{len(grade)}c-cons{cfg['consumo_peca_m']}",
                      "tamanhos": r["tamanhos"], "regras": regras,
                      "config": cfg, "grade": grade})
    os.makedirs(os.path.dirname(CORPUS_PRIVADO), exist_ok=True)
    tmp = CORPUS_PRIVADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(casos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CORPUS_PRIVADO)
    return casos


if __name__ == "__main__":
    if "--importar-cache" in sys.argv:
        cs = importar_do_cache()
        print(f"{len(cs)} caso(s) gravado(s) em {CORPUS_PRIVADO}")
    else:
        for c in carregar():
            pecas = sum(sum(v.values()) for v in c["grade"].values())
            print(f"{c['nome']:40s} {len(c['grade'])} cor(es) {pecas:5d} pecas")
