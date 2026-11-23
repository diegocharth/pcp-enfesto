"""
Bancada do alocador de rolos -- rolo a rolo x busca exata/local x gabarito.

Corpus: alocacoes reais exportadas pela tela (dados/resultados/alocacao_rolos_*.xlsx)
remontadas em dados/ordens/bench_alocacao.json (pasta fora do git: sao OPs reais).
Por cor: camadas por mapa, comprimento da camada e comprimento nominal dos rolos.

Uso:
    python tools/bench/alocacao.py --extrair          # (re)monta o corpus
    python tools/bench/alocacao.py                    # rolo a rolo x versao atual
    python tools/bench/alocacao.py --cpsat 120        # + gabarito CP-SAT (so dev)
    python tools/bench/alocacao.py --folga 1          # forca a folga de incerteza (%)

O gabarito CP-SAT maximiza os metros cobertos (= menor compra) com o mesmo
modelo do alocador (mm inteiros, camada inteira, margem 1x por mapa paga num
rolo que serve o mapa) e mostra o piso provado quando nao fecha no tempo.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(AQUI))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from engine.alocador_rolos import _alocar_cor, _comp_seguro  # noqa: E402

CORPUS = os.path.join(BASE, "dados", "ordens", "bench_alocacao.json")
RE_MAPA = re.compile(r"Mapa (\d+) -- camada ([\d.]+)m -- (\d+)/(\d+) camadas")
RE_ROLO_ANT = re.compile(r"(.+): rolo (\d+) informado ([\d.]+)m; alocado contra [\d.]+m "
                         r"\(folga de incerteza ([\d.]+)%\)")
RE_DEF_ANT = re.compile(r"(.+): deficit de (\d+) camada\(s\) do mapa (\d+) -- comprar aprox\. ([\d.]+)m")


# --- extracao das planilhas --------------------------------------------------

def _linhas(ws):
    for row in ws.iter_rows(values_only=True):
        vals = [v for v in row if v is not None]
        if vals:
            yield vals, row


def _le_antigo(nome, wb):
    """Formato de junho/2026: rolos e deficits nos alertas do resumo; camadas
    cobertas nas linhas '  Mapa M' de cada aba de cor."""
    rolos, deficit, folga, margem = {}, {}, 0.01, 0.06
    for vals, _ in _linhas(wb["Resumo Alocacao"]):
        t = vals[0] if isinstance(vals[0], str) else ""
        m = RE_ROLO_ANT.match(t)
        if m:
            rolos.setdefault(m.group(1), []).append(float(m.group(3)))
            folga = float(m.group(4)) / 100.0
        m = RE_DEF_ANT.match(t)
        if m:
            n, mid = int(m.group(2)), int(m.group(3))
            deficit.setdefault(m.group(1), {})[mid] = (n, round(float(m.group(4)) / n, 4))
    cores = {}
    for ws in wb.worksheets:
        cor = ws.title[6:]
        if not ws.title.startswith("Rolos ") or not rolos.get(cor):
            continue
        dem, cc = {}, {}
        for vals, _ in _linhas(ws):
            t = vals[0]
            if isinstance(t, str) and t.strip().startswith("Mapa ") and len(vals) > 2:
                mid = int(t.split()[1])
                dem[mid] = dem.get(mid, 0) + int(str(vals[1]).split()[0])
                cc[mid] = float(vals[2])
                fac = [v for v in vals if isinstance(v, str) and "faca" in v]
                if fac:
                    margem = float(re.search(r"([\d.]+)m faca", fac[0]).group(1))
        for mid, (n, c) in deficit.get(cor, {}).items():
            dem[mid] = dem.get(mid, 0) + n
            cc.setdefault(mid, c)
        cores[cor] = {"demanda": dem, "cc": cc, "rolos": rolos[cor]}
    cfg = {"margem_seguranca_enfesto_m": margem, "folga_incerteza_pct": folga,
           "folga_incerteza_m": 0.0, "ponta_minima_util_m": 0.5}
    return {"arquivo": nome, "versao": "antiga", "config": cfg, "cores": cores}


def _le(f):
    import openpyxl
    nome = os.path.basename(f)
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    params = {}
    for vals, _ in _linhas(wb["Resumo Alocacao"]):
        if isinstance(vals[0], str) and len(vals) > 1:
            params[vals[0]] = vals[1]
    if "Versao" not in params:
        return _le_antigo(nome, wb)
    folga = float(params.get("Folga de incerteza (%)", 1)) / 100.0
    folga_m = float(params.get("Folga de incerteza fixa (m)", 0) or 0)
    cfg = {"margem_seguranca_enfesto_m": float(params.get("Margem de faca por sub-enfesto (m)", 0.1)),
           "folga_incerteza_pct": folga, "folga_incerteza_m": folga_m,
           "ponta_minima_util_m": float(params.get("Ponta minima util (m)", 0.5))}
    cores = {}
    for ws in wb.worksheets:
        if not ws.title.startswith("Rolos "):
            continue
        dem, cc, rolos, cab, nos_rolos = {}, {}, [], None, False
        for vals, row in _linhas(ws):
            v0 = vals[0]
            if isinstance(v0, str):
                m = RE_MAPA.match(v0)
                if m:
                    cc[int(m.group(1))] = float(m.group(2))
                    dem[int(m.group(1))] = int(m.group(4))
                elif v0.startswith("Sobras por rolo") or v0.startswith("Rolos utilizados"):
                    nos_rolos = True
                elif v0 == "Rolo":
                    cab = vals
                continue
            if nos_rolos and cab and isinstance(v0, (int, float)):
                d = dict(zip(cab, row[:len(cab)]))
                if d.get("Nominal (m)"):
                    nom = float(d["Nominal (m)"])
                else:   # v2.11.x: ponta = restante do comp_seguro
                    seg = float(d["Usado (m)"]) + float(d["Ponta (m)"])
                    nom = seg + folga_m if folga_m > 0 else seg / (1.0 - folga)
                rolos.append(round(nom, 2))
        if dem:
            cores[ws.title[6:]] = {"demanda": dem, "cc": cc, "rolos": rolos}
    return {"arquivo": nome, "versao": str(params["Versao"]), "config": cfg, "cores": cores}


def extrair():
    vistos, casos = set(), []
    for f in sorted(glob.glob(os.path.join(BASE, "dados", "resultados", "alocacao_rolos_*.xlsx"))):
        c = _le(f)
        assin = hashlib.sha1(json.dumps([c["config"], c["cores"]], sort_keys=True).encode()).hexdigest()
        if c["cores"] and assin not in vistos:
            vistos.add(assin)
            casos.append(c)
    with open(CORPUS, "w", encoding="utf-8") as fh:
        json.dump(casos, fh, indent=1)
    print(f"{len(casos)} alocacoes distintas -> {CORPUS}")


# --- gabarito CP-SAT (so dev) ------------------------------------------------

def gabarito(dem, cc, rolos, cfg, limite_s, dica=None):
    from ortools.sat.python import cp_model
    marg = int(math.ceil(cfg["margem_seguranca_enfesto_m"] * 1000 - 1e-6))
    caps = [int(math.floor(round(_comp_seguro(n, cfg), 6) * 1000 + 1e-6)) for n in rolos]
    mids = [m for m in dem if dem[m] > 0]
    L = {m: int(math.ceil(cc[m] * 1000 - 1e-6)) for m in mids}
    W = {m: int(round(cc[m] * 10000)) for m in mids}
    md = cp_model.CpModel()
    k, p = {}, {}
    y = {m: md.NewBoolVar("") for m in mids}
    for r, cap in enumerate(caps):
        for m in mids:
            k[r, m] = md.NewIntVar(0, min(dem[m], cap // L[m]), "")
            p[r, m] = md.NewBoolVar("")
            md.Add(k[r, m] >= 1).OnlyEnforceIf(p[r, m])
        md.Add(sum(L[m] * k[r, m] + marg * p[r, m] for m in mids) <= cap)
    for m in mids:
        md.Add(sum(k[r, m] for r in range(len(caps))) <= dem[m] * y[m])
        md.Add(sum(p[r, m] for r in range(len(caps))) == y[m])
    for (r, m), n in (dica or {}).items():
        md.AddHint(k[r, m], n)
    md.Maximize(sum(W[m] * k[r, m] for r in range(len(caps)) for m in mids))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = limite_s
    sv.parameters.num_workers = 16
    st = sv.Solve(md)
    total = sum(dem[m] * W[m] for m in mids)
    return (round((total - sv.ObjectiveValue()) / 10000.0, 2),
            round(max(0.0, (total - sv.BestObjectiveBound()) / 10000.0), 2),
            st == cp_model.OPTIMAL)


# --- comparacao --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extrair", action="store_true")
    ap.add_argument("--cpsat", type=float, default=0.0, help="segundos por cor no CP-SAT (0 = sem)")
    ap.add_argument("--folga", type=float, default=None, help="folga de incerteza em %% (padrao: a do arquivo)")
    a = ap.parse_args()
    if a.extrair:
        extrair()
        return
    casos = json.load(open(CORPUS, encoding="utf-8"))
    tot = [0.0, 0.0, 0.0]
    for c in casos:
        cfg = dict(c["config"])
        if a.folga is not None:
            cfg["folga_incerteza_pct"] = a.folga / 100.0
        print(f"== {c['arquivo']} (folga {cfg['folga_incerteza_pct'] * 100:.0f}%)")
        for cor, v in c["cores"].items():
            dem = {int(m): int(n) for m, n in v["demanda"].items()}
            cc = {int(m): float(x) for m, x in v["cc"].items()}
            antes = _alocar_cor(dem, cc, v["rolos"], dict(cfg, alocacao_exata=False))
            t0 = time.perf_counter()
            depois = _alocar_cor(dem, cc, v["rolos"], cfg)
            t = time.perf_counter() - t0
            linha = (f"  {cor:10s} {len(dem):2d} mapas {len(v['rolos']):2d} rolos | compra "
                     f"{antes['tecido_a_comprar_m']:8.2f} -> {depois['tecido_a_comprar_m']:8.2f} "
                     f"| rolos {antes['n_rolos_utilizados']:2d} -> {depois['n_rolos_utilizados']:2d} "
                     f"| {depois['busca_exata']:11s} {t:5.2f}s")
            tot[0] += antes["tecido_a_comprar_m"]
            tot[1] += depois["tecido_a_comprar_m"]
            if a.cpsat > 0:
                dica = {}
                for e in depois["enfestos"]:
                    for f in e["fontes"]:
                        ch = (f["rolo_indice"] - 1, e["mapa_id"])
                        dica[ch] = dica.get(ch, 0) + f["n_camadas"]
                achado, piso, ot = gabarito(dem, cc, v["rolos"], cfg, a.cpsat, dica)
                tot[2] += achado
                linha += f" | CP-SAT {achado:8.2f} (piso {piso:8.2f}{' otimo' if ot else ''})"
            print(linha, flush=True)
    print(f"\nTOTAL compra: rolo a rolo {tot[0]:.2f} m -> atual {tot[1]:.2f} m"
          + (f" | CP-SAT {tot[2]:.2f} m" if a.cpsat > 0 else ""))


if __name__ == "__main__":
    main()
