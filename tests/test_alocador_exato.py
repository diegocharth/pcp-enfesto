"""Etapa 5: busca exata e busca local na alocacao de rolos (engine/alocador_exato.py).

- casos que o alocador rolo a rolo errava (compra a mais; compra "falsa" quando os
  rolos bastavam; margem que so cabe num rolo seguinte);
- busca exata = forca bruta independente em instancias minusculas;
- saida sempre fisicamente valida e nunca pior que o rolo a rolo;
- prazo global respeitado; desligada = comportamento antigo.
"""
import itertools
import random
import time

import pytest

from engine import alocador_exato as AE
from engine import alocador_rolos as AR
from engine.alocador_rolos import _alocar_cor, _comp_seguro, alocar_rolos

CFG = {"margem_seguranca_enfesto_m": 0.06, "folga_incerteza_pct": 0.03,
       "folga_incerteza_m": 0.0, "ponta_minima_util_m": 0.5}


def _sem(cfg):
    return dict(cfg, alocacao_exata=False)


def _valida(res, dem, cc, rolos, cfg):
    """Restricoes fisicas lidas da SAIDA: rolo nunca passa do comp_seguro, camada
    inteira, cobertura <= demanda, margem de faca 1x por mapa coberto."""
    marg = cfg["margem_seguranca_enfesto_m"]
    usado = [0.0] * len(rolos)
    for e in res["enfestos"]:
        m = e["mapa_id"]
        cob = sum(f["n_camadas"] for f in e["fontes"])
        assert cob == e["camadas_cobertas"] <= dem[m]
        assert sum(1 for f in e["fontes"] if f["primaria"]) == (1 if cob else 0)
        for f in e["fontes"]:
            assert isinstance(f["n_camadas"], int) and f["n_camadas"] > 0
            usado[f["rolo_indice"] - 1] += f["n_camadas"] * cc[m] + (marg if f["primaria"] else 0)
    for j, n in enumerate(rolos):
        assert usado[j] <= _comp_seguro(n, cfg) + 1e-6
    compra = sum((dem[e["mapa_id"]] - e["camadas_cobertas"]) * cc[e["mapa_id"]]
                 for e in res["enfestos"])
    assert compra == pytest.approx(res["tecido_a_comprar_m"], abs=1e-3)


# --- casos reais (numeros de OPs de junho/2026, sem identificacao) -----------

def test_compra_falsa_some_quando_os_rolos_bastam():
    # O rolo a rolo mandava comprar 5,25 m; os 4 rolos cobrem tudo.
    dem, cc = {1: 4, 2: 3, 0: 4}, {1: 5.25, 2: 7.0, 0: 8.75}
    rolos, cfg = [25.0, 23.0, 18.0, 14.0], dict(CFG, folga_incerteza_pct=0.01)
    antes = _alocar_cor(dem, cc, rolos, _sem(cfg))
    depois = _alocar_cor(dem, cc, rolos, cfg)
    assert antes["tecido_a_comprar_m"] == pytest.approx(5.25)
    assert depois["tecido_a_comprar_m"] == 0.0 and not depois["camadas_em_deficit"]
    assert depois["busca_exata"] == "provado"
    _valida(depois, dem, cc, rolos, cfg)


def test_compra_minima_provada():
    # Rolo a rolo deixava uma camada de 8,75 m de fora; o otimo deixa uma de 5,25.
    dem, cc = {1: 10, 2: 8, 0: 11}, {1: 5.25, 2: 7.0, 0: 8.75}
    rolos = [59.0, 50.0, 49.0, 43.0, 10.0]
    antes = _alocar_cor(dem, cc, rolos, _sem(CFG))
    depois = _alocar_cor(dem, cc, rolos, CFG)
    assert antes["tecido_a_comprar_m"] == pytest.approx(8.75)
    assert depois["tecido_a_comprar_m"] == pytest.approx(5.25)
    assert depois["busca_exata"] == "provado"
    assert depois["resumo_compra"]["compra_recomendada_m"] == pytest.approx(5.25)
    _valida(depois, dem, cc, rolos, CFG)


def test_margem_paga_por_rolo_seguinte():
    # O rolo de 18,02 m so cabe 2 camadas do mapa 0 SEM a margem; quem paga a
    # margem do mapa 0 e o rolo de 16,5 m (achado por forca bruta).
    dem, cc = {0: 3, 1: 4}, {0: 9.0, 1: 9.0}
    rolos = [18.02, 15.2, 16.5]
    cfg = dict(CFG, margem_seguranca_enfesto_m=0.1, folga_incerteza_pct=0.0)
    antes = _alocar_cor(dem, cc, rolos, _sem(cfg))
    depois = _alocar_cor(dem, cc, rolos, cfg)
    assert antes["tecido_a_comprar_m"] > depois["tecido_a_comprar_m"]
    assert depois["tecido_a_comprar_m"] == pytest.approx(3 * 9.0)      # 4 de 7 camadas
    assert depois["busca_exata"] == "provado"
    _valida(depois, dem, cc, rolos, cfg)
    # quem paga a margem de algum mapa nao e o primeiro rolo (o maior) que o serve
    adiada = False
    for e in depois["enfestos"]:
        prim = [f["rolo_indice"] for f in e["fontes"] if f["primaria"]]
        servem = sorted({f["rolo_indice"] for f in e["fontes"]}, key=lambda j: -rolos[j - 1])
        adiada |= bool(prim) and prim[0] != servem[0]
    assert adiada


# --- forca bruta independente ------------------------------------------------

def _forca_bruta(dem, cc, rolos, cfg):
    """(maior cobertura em mm, menos rolos) por enumeracao total, mm inteiros."""
    import math
    mids = sorted(dem)
    L = [int(math.ceil(cc[m] * 1000 - 1e-6)) for m in mids]
    D = [dem[m] for m in mids]
    marg = int(math.ceil(cfg["margem_seguranca_enfesto_m"] * 1000 - 1e-6))
    caps = [int(math.floor(round(_comp_seguro(n, cfg), 6) * 1000 + 1e-6)) for n in rolos]
    M = len(mids)
    opc = []
    for cap in caps:
        o = []
        for ks in itertools.product(*[range(min(D[i], cap // L[i]) + 1) for i in range(M)]):
            serv = [i for i in range(M) if ks[i]]
            for n in range(len(serv) + 1):
                for pg in itertools.combinations(serv, n):
                    if sum(k * l for k, l in zip(ks, L)) + marg * n <= cap:
                        o.append((ks, frozenset(pg)))
        opc.append(o)
    melhor = (-1, 0)
    for esc in itertools.product(*opc):
        tot = [sum(e[0][i] for e in esc) for i in range(M)]
        if any(t > d for t, d in zip(tot, D)):
            continue
        if any(sum(1 for e in esc if i in e[1]) != (1 if tot[i] else 0) for i in range(M)):
            continue
        cob = sum(t * l for t, l in zip(tot, L))
        abertos = sum(1 for e in esc if any(e[0]))
        melhor = max(melhor, (cob, -abertos))
    return melhor[0], -melhor[1], sum(d * l for d, l in zip(D, L))


def test_busca_exata_igual_a_forca_bruta():
    rnd = random.Random(2026)
    for _ in range(60):
        M, R = rnd.randint(1, 2), rnd.randint(1, 3)
        cc = {m: rnd.randint(3, 9) / 10 for m in range(M)}
        dem = {m: rnd.randint(1, 4) for m in range(M)}
        rolos = [rnd.randint(4, 20) / 10 + rnd.choice([0, 0.01, 0.02, 0.05]) for _ in range(R)]
        cfg = dict(CFG, margem_seguranca_enfesto_m=rnd.choice([0.02, 0.05, 0.1]),
                   folga_incerteza_pct=0.0)
        cob, abertos, total = _forca_bruta(dem, cc, rolos, cfg)
        r = _alocar_cor(dem, cc, rolos, cfg)
        _valida(r, dem, cc, rolos, cfg)
        assert r["busca_exata"] == "provado"
        mm = sum(r["camadas_alocadas"][m] * round(cc[m] * 1000) for m in dem)
        assert mm == cob, (dem, cc, rolos, cfg)
        if cob == total:            # sem deficit: tambem o menor numero de rolos
            assert r["n_rolos_utilizados"] == abertos, (dem, cc, rolos, cfg)


# --- validade, nunca pior, prazo ----------------------------------------------

def _instancia(rnd, m_min, m_max):
    M = rnd.randint(m_min, m_max)
    cons = rnd.choice([1.37, 1.74, 1.87, 1.93])
    pmax = int(10 // cons)
    cc = {m: round(rnd.randint(max(1, pmax - 2), pmax) * cons, 4) for m in range(M)}
    dem = {m: rnd.randint(1, 20) for m in range(M)}
    rolos = [round(rnd.choice([rnd.uniform(40, 75)] * 3 + [rnd.uniform(5, 35)]), 1)
             for _ in range(rnd.randint(3, 20))]
    cfg = dict(CFG, margem_seguranca_enfesto_m=0.1,
               folga_incerteza_pct=rnd.choice([0.01, 0.03]))
    return dem, cc, rolos, cfg


def test_nunca_pior_e_sempre_valida(monkeypatch):
    monkeypatch.setattr(AE, "EXATA_PRAZO_COR_S", 0.15)
    rnd = random.Random(7)
    melhorou = 0
    for k in range(40):
        dem, cc, rolos, cfg = _instancia(rnd, 2, 14)
        antes = _alocar_cor(dem, cc, rolos, _sem(cfg))
        depois = _alocar_cor(dem, cc, rolos, cfg)
        _valida(depois, dem, cc, rolos, cfg)
        chave = lambda r: (r["tecido_a_comprar_m"], r["n_rolos_utilizados"])
        assert chave(depois) <= chave(antes)
        melhorou += chave(depois) < chave(antes)
    assert melhorou > 0


def test_plano_de_resultado_reconstroi_a_alocacao():
    rnd = random.Random(3)
    for _ in range(20):
        dem, cc, rolos, cfg = _instancia(rnd, 2, 6)
        r = _alocar_cor(dem, cc, rolos, _sem(cfg))
        r2 = AR._alocar_cor_plano(dem, cc, rolos, cfg, AE.plano_de_resultado(r))
        assert r2["camadas_alocadas"] == r["camadas_alocadas"]
        assert r2["tecido_a_comprar_m"] == r["tecido_a_comprar_m"]
        assert [x["usado_m"] for x in r2["rolos"]] == [x["usado_m"] for x in r["rolos"]]


def test_busca_local_melhora_cor_com_muitos_mapas():
    # 12 mapas (acima do porte da busca completa): a busca local por pares/trios
    # de rolos reduz a compra, sem prova.
    rnd = random.Random(41)
    achou = False
    for _ in range(30):
        dem, cc, rolos, cfg = _instancia(rnd, 12, 12)
        antes = _alocar_cor(dem, cc, rolos, _sem(cfg))
        if not antes["camadas_em_deficit"]:
            continue
        depois = _alocar_cor(dem, cc, rolos, cfg)
        _valida(depois, dem, cc, rolos, cfg)
        assert depois["busca_exata"] in ("nao_provado", "provado")
        assert depois["tecido_a_comprar_m"] <= antes["tecido_a_comprar_m"] + 1e-9
        if depois["tecido_a_comprar_m"] < antes["tecido_a_comprar_m"] - 1e-9:
            assert depois["busca_exata"] == "nao_provado"
            achou = True
            break
    assert achou


def test_prazo_total_da_alocacao(monkeypatch):
    monkeypatch.setattr(AE, "EXATA_PRAZO_TOTAL_S", 0.4)
    rnd = random.Random(11)
    mapas, camadas, rolos = [], {}, {}
    for m in range(14):
        mapas.append({"id": m, "comp_camada_m": round(rnd.uniform(7.5, 10), 2), "n_pecas": 1})
    for cor in ("A", "B", "C", "D", "E", "F"):
        camadas[cor] = {m: rnd.randint(2, 15) for m in range(14)}
        rolos[cor] = [round(rnd.uniform(40, 75), 1) for _ in range(12)]
    t0 = time.perf_counter()
    r = alocar_rolos({"mapas": mapas, "camadas": camadas, "consumo_peca": 1.0}, rolos, dict(CFG))
    assert time.perf_counter() - t0 < 0.4 + 1.5      # prazo + a parte rolo a rolo
    assert r["params"]["alocacao_exata"] is True


def test_desligada_mantem_o_rolo_a_rolo():
    dem, cc = {1: 10, 2: 8, 0: 11}, {1: 5.25, 2: 7.0, 0: 8.75}
    r = _alocar_cor(dem, cc, [59.0, 50.0, 49.0, 43.0, 10.0], _sem(CFG))
    assert r["busca_exata"] == "nao_tentada"
    assert r["tecido_a_comprar_m"] == pytest.approx(8.75)


# --- defeitos achados na revisao independente (23/11/2026) -------------------

def test_lotes_de_uma_cor_nao_tiram_o_prazo_das_outras(monkeypatch):
    # Cores com muitos lotes rodavam a busca em cada combinacao de lotes e
    # esgotavam o prazo global: a ultima cor (um lote so) perdia a busca e
    # voltava a comprar 5,25 m a mais.
    monkeypatch.setattr(AE, "EXATA_PRAZO_TOTAL_S", 1.5)
    rnd = random.Random(5)
    mapas = [{"id": m, "comp_camada_m": round(rnd.uniform(5, 9.5), 2), "n_pecas": 1}
             for m in range(8)]
    camadas, rolos = {}, {}
    for cor in ("AAA", "BBB", "CCC", "DDD"):
        camadas[cor] = {m: rnd.randint(5, 14) for m in range(8)}
        rolos[cor] = [{"comprimento_m": round(rnd.uniform(20, 70), 1), "lote": f"L{k % 7}"}
                      for k in range(15)]
    mapas += [{"id": 100, "comp_camada_m": 5.25, "n_pecas": 1},
              {"id": 101, "comp_camada_m": 7.0, "n_pecas": 1},
              {"id": 102, "comp_camada_m": 8.75, "n_pecas": 1}]
    camadas["ZZZ"] = {100: 4, 101: 3, 102: 4}
    rolos["ZZZ"] = [25.0, 23.0, 18.0, 14.0]
    cfg = dict(CFG, folga_incerteza_pct=0.01, considerar_lote=True)
    r = alocar_rolos({"mapas": mapas, "camadas": camadas, "consumo_peca": 1.0}, rolos, cfg)
    z = r["por_cor"]["ZZZ"]
    assert z["tecido_a_comprar_m"] == 0.0 and z["busca_exata"] == "provado"


def test_provado_no_modo_lote_diz_que_vale_para_os_lotes():
    # L1 sozinho cobre tudo com 3 rolos (o modo lote fica com ele); L2 sozinho
    # nao cobre, mas L1+L2 cobririam com 2 rolos -- "provado" nao vale para a cor.
    plano = {"mapas": [{"id": 0, "comp_camada_m": 9.0, "n_pecas": 1}],
             "camadas": {"A": {0: 6}}, "consumo_peca": 1.0}
    rolos = {"A": [{"comprimento_m": 20.0, "lote": "L1"}, {"comprimento_m": 20.0, "lote": "L1"},
                   {"comprimento_m": 20.0, "lote": "L1"},
                   {"comprimento_m": 40.0, "lote": "L2"}]}
    cfg = dict(CFG, folga_incerteza_pct=0.0, considerar_lote=True)
    r = alocar_rolos(plano, rolos, cfg)["por_cor"]["A"]
    assert r["lotes"]["utilizados"] == ["L1"] and r["n_rolos_utilizados"] == 3
    sem_lote = alocar_rolos(plano, rolos, dict(cfg, considerar_lote=False))["por_cor"]["A"]
    assert sem_lote["n_rolos_utilizados"] == 2 and sem_lote["busca_exata"] == "provado"
    assert r["busca_exata"] == "provado_nos_lotes"


def test_empate_de_arredondamento_nao_esconde_plano_melhor():
    # Planos que diferem em 0,1 mm de compra: fica o melhor, nao o rolo a rolo.
    dem, cc = {0: 2, 1: 2, 2: 2}, {0: 0.685, 1: 0.6849, 2: 0.989}
    cfg = dict(CFG, margem_seguranca_enfesto_m=1.0, folga_incerteza_pct=0.0)
    r = _alocar_cor(dem, cc, [1.727], cfg)
    assert r["camadas_alocadas"][0] == 1 and r["camadas_alocadas"][1] == 0
    assert r["busca_exata"] == "provado"


def test_rolo_absurdo_nao_estoura_a_memoria():
    import tracemalloc
    tracemalloc.start()
    r = _alocar_cor({0: 3, 1: 2}, {0: 9.0, 1: 8.0}, [1e7, 50.0], CFG)
    pico = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert pico < 50e6
    _valida(r, {0: 3, 1: 2}, {0: 9.0, 1: 8.0}, [1e7, 50.0], CFG)


def test_cor_com_milhares_de_rolos_nao_derruba_a_alocacao():
    R = 1200
    dem, cc = {0: 3 * R, 1: R}, {0: 1.0, 1: 0.7}
    rolos = [2.5 + (j % 7) * 0.01 for j in range(R)]
    r = _alocar_cor(dem, cc, rolos, dict(CFG, margem_seguranca_enfesto_m=0.1))
    assert r["tecido_a_comprar_m"] > 0


def test_busca_local_e_deterministica():
    # Para por passos, nao pelo relogio: mesma entrada, mesmo resultado.
    rnd = random.Random(41)
    for _ in range(30):
        dem, cc, rolos, cfg = _instancia(rnd, 12, 12)
        antes = _alocar_cor(dem, cc, rolos, _sem(cfg))
        if not antes["camadas_em_deficit"]:
            continue
        a = _alocar_cor(dem, cc, rolos, cfg)
        if a["tecido_a_comprar_m"] < antes["tecido_a_comprar_m"] - 1e-9:
            b = _alocar_cor(dem, cc, rolos, cfg)
            assert a["camadas_alocadas"] == b["camadas_alocadas"]
            assert [x["usado_m"] for x in a["rolos"]] == [x["usado_m"] for x in b["rolos"]]
            return
    pytest.fail("nenhum caso com melhora da busca local")


def test_rolo_a_rolo_nao_trava_com_camadas_curtas_e_rolos_longos():
    # Etapa 6 (C7): 30 mapas de 0,8-3 m e rolos de 40-150 m faziam a mochila
    # de um rolo levar minutos/horas. Agora cai no enchimento simples.
    rnd = random.Random(2)
    rnd.choice([17, 25, 30])
    M = 30
    cc = {m: round(rnd.uniform(0.8, 3.0), 3) for m in range(M)}
    dem = {m: rnd.randint(1, 30) for m in range(M)}
    rolos = [round(rnd.uniform(40, 150), 1) for _ in range(8)]
    cfg = dict(CFG, margem_seguranca_enfesto_m=0.1)
    t0 = time.perf_counter()
    r = _alocar_cor(dem, cc, rolos, _sem(cfg))
    assert time.perf_counter() - t0 < 60
    assert AR._DP_ULTIMOS_PASSOS > AR.DP_LIMITE_PASSOS       # passou pelo teto
    _valida(r, dem, cc, rolos, cfg)
    assert r["n_rolos_utilizados"] == len(rolos)


def test_enchimento_simples_respeita_rolo_e_margem():
    # 3 camadas de 3 m + margem = 9,1 m; sobram 0,9 m: nao cabe 1 m + margem.
    assert AR._encher_rolo_guloso(10_000, [(1, 3000), (2, 1000)], {1: 5, 2: 5}, 100, {1, 2}) == {1: 3}
    # camada de 0,9 m: com a margem do mapa 2 ja paga cabe na sobra; pendente, nao
    assert AR._encher_rolo_guloso(10_000, [(1, 3000), (2, 900)], {1: 5, 2: 5}, 100, {1}) == {1: 3, 2: 1}
    assert AR._encher_rolo_guloso(10_000, [(1, 3000), (2, 900)], {1: 5, 2: 5}, 100, {1, 2}) == {1: 3}
