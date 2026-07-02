"""Novo alocador enfesto-por-enfesto: _alocar_cor (por cor)."""
from engine.alocador_rolos import _alocar_cor

CFG = {"margem_seguranca_enfesto_m": 0.10, "folga_incerteza_pct": 0.0,
       "folga_incerteza_m": 0.0, "ponta_minima_util_m": 0.5}


def test_um_mapa_cabe_tudo():
    # mapa 0 cc=4.0, precisa 3; rolo de 20m (seguro=20, folga 0) cabe 4 camadas.
    r = _alocar_cor({0: 3}, {0: 4.0}, [20.0], CFG)
    assert r["camadas_alocadas"] == {0: 3}
    assert r["camadas_em_deficit"] == {}
    e = r["enfestos"][0]
    assert e["mapa_id"] == 0 and e["camadas_cobertas"] == 3
    assert e["camadas_em_deficit"] == 0
    # margem 1x: 3*4.0 + 0.10
    assert abs(e["tecido_usado_m"] - 12.10) < 1e-6
    assert len(e["fontes"]) == 1
    f = e["fontes"][0]
    assert f["tipo"] == "rolo" and f["rolo_indice"] == 1
    assert f["n_camadas"] == 3 and f["reaproveitada"] is False and f["primaria"] is True
    # ponta final do rolo = 20 - (12.10) = 7.90 -> estoque
    assert len(r["rolos"]) == 1
    assert abs(r["rolos"][0]["ponta_m"] - 7.90) < 1e-6
    assert r["rolos"][0]["ponta_classe"] == "estoque"
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 0


def test_reaproveita_ponta_de_mapa_longo_em_mapa_curto():
    # E1 cc=7.8 (4 camadas), E2 cc=4.0 (3). Rolos 20 e 12 (folga 0).
    r = _alocar_cor({0: 4, 1: 3}, {0: 7.8, 1: 4.0}, [20.0, 12.0], CFG)
    # Ordem: mapa 0 (longo) primeiro.
    assert [e["mapa_id"] for e in r["enfestos"]] == [0, 1]
    e0, e1 = r["enfestos"]
    # E1: rolo 20 -> 2 camadas (primaria, 2*7.8+0.10=15.7); rolo 12 -> 1 (7.8). Cobertas 3, deficit 1.
    assert e0["camadas_cobertas"] == 3 and e0["camadas_em_deficit"] == 1
    # E2: pontas 4.3 (do rolo 20) e 4.2 (do rolo 12) -> 1 camada cada. Cobertas 2, deficit 1.
    assert e1["camadas_cobertas"] == 2 and e1["camadas_em_deficit"] == 1
    assert all(f["reaproveitada"] for f in e1["fontes"])
    assert all(f["tipo"] == "ponta" for f in e1["fontes"])
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 2
    assert abs(r["reaproveitamento"]["tecido_economizado_m"] - 8.0) < 1e-6


def test_ponta_menor_que_camada_nao_e_usada():
    # E1 cc=7.8 (precisa 2). Rolo 8.0 -> 1 camada, ponta 0.10. E2 cc=4.0 (precisa 1).
    # A ponta 0.10 < 4.0 nao serve ao E2 (nada de submapa parcial).
    r = _alocar_cor({0: 2, 1: 1}, {0: 7.8, 1: 4.0}, [8.0], CFG)
    e1 = [e for e in r["enfestos"] if e["mapa_id"] == 1][0]
    assert e1["camadas_cobertas"] == 0
    assert e1["fontes"] == []
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 0


def test_sem_emenda_cada_fonte_um_pedaco():
    r = _alocar_cor({0: 4}, {0: 7.8}, [20.0, 12.0], CFG)
    e0 = r["enfestos"][0]
    # rolo 20 -> 2 camadas; rolo 12 -> 1 camada; cada fonte sai de um unico rolo.
    assert sorted(f["n_camadas"] for f in e0["fontes"]) == [1, 2]
    assert e0["camadas_cobertas"] == 3


def test_deficit_sem_pedaco_para_primaria():
    # cc=7.8 + margem 0.10 = 7.90; rolo 7.0 (<7.90) nao hospeda a pilha -> deficit total.
    r = _alocar_cor({0: 1}, {0: 7.8}, [7.0], CFG)
    assert r["enfestos"][0]["camadas_cobertas"] == 0
    assert r["camadas_em_deficit"] == {0: 1}
    assert abs(r["tecido_a_comprar_m"] - 7.8) < 1e-6


def test_ordem_empate_maior_demanda_primeiro():
    # dois mapas com mesma cc; o de maior demanda vem primeiro.
    r = _alocar_cor({0: 2, 1: 5}, {0: 4.0, 1: 4.0}, [50.0], CFG)
    assert [e["mapa_id"] for e in r["enfestos"]] == [1, 0]


# ---------------------------------------------------------------------------
# Atribuicao otima por rolo (DP): casos que o greedy antigo nao resolvia
# ---------------------------------------------------------------------------

def test_dp_cobre_tudo_onde_greedy_encalhava():
    # Greedy antigo (mapa longo primeiro): mapa 0 (7.8) enchia o rolo de 16m
    # com 2 camadas (15.7), sobrando 0.3m inutil; o mapa 1 (4.0) so conseguia
    # 1 camada no rolo de 8m -> deficit de 1 camada (compra 4.0m), com 3.9m
    # encalhados no rolo de 8m.
    # DP (verificado a mao): rolo 16 = 1x7.8 + 0.1 + 2x4.0 + 0.1 = 16.0 exato;
    # rolo 8 = 1x7.8 = 7.8 <= 8.0. Cobre TUDO, compra zero.
    r = _alocar_cor({0: 2, 1: 2}, {0: 7.8, 1: 4.0}, [16.0, 8.0], CFG)
    assert r["camadas_em_deficit"] == {}
    assert r["camadas_alocadas"] == {0: 2, 1: 2}
    assert r["tecido_a_comprar_m"] == 0.0


def test_reaproveitada_honesta_sobra_ampla_nao_conta():
    # Rolo de 30m serve o mapa 0 (6.0) e depois o mapa 1 (3.0), mas no momento
    # do uso do mapa 1 restavam 23.9m (>= 6.0): a sobra AINDA servia ao mapa 0,
    # logo usar o rolo de novo nao e reaproveitamento real.
    r = _alocar_cor({0: 1, 1: 1}, {0: 6.0, 1: 3.0}, [30.0], CFG)
    e1 = [e for e in r["enfestos"] if e["mapa_id"] == 1][0]
    assert e1["camadas_cobertas"] == 1
    f = e1["fontes"][0]
    assert f["reaproveitada"] is False
    assert f["tipo"] == "rolo"
    assert f["enfesto_origem"] is None
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 0


def test_reaproveitada_honesta_sobra_genuina_conta():
    # Rolo de 21.5m: mapa 0 (6.0) corta 3 camadas (18.1m); sobram 3.4m < 6.0
    # -- a sobra ja nao serve ao mapa 0. O mapa 1 (3.0) usa essa sobra:
    # reaproveitamento REAL (tipo ponta, origem = mapa 0).
    r = _alocar_cor({0: 3, 1: 1}, {0: 6.0, 1: 3.0}, [21.5], CFG)
    assert r["camadas_em_deficit"] == {}
    e1 = [e for e in r["enfestos"] if e["mapa_id"] == 1][0]
    f = e1["fontes"][0]
    assert f["reaproveitada"] is True
    assert f["tipo"] == "ponta"
    assert f["enfesto_origem"] == 0
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 1
    assert abs(r["reaproveitamento"]["tecido_economizado_m"] - 3.0) < 1e-6


def test_identidade_compra_falta_mais_fragmentacao():
    # necessario 2x7.8 + 3x4.0 = 27.6m; disponivel seguro 24.0m -> falta 3.6m.
    # Melhor cobertura possivel deixa 1 camada de 4.0 de fora -> compra 4.0m,
    # logo fragmentacao = 0.4m. Identidade: compra = falta + fragmentacao.
    r = _alocar_cor({0: 2, 1: 3}, {0: 7.8, 1: 4.0}, [16.0, 8.0], CFG)
    rc = r["resumo_compra"]
    assert abs(rc["necessario_m"] - 27.6) < 1e-6
    assert abs(rc["disponivel_seguro_m"] - 24.0) < 1e-6
    assert abs(rc["falta_liquida_m"] - 3.6) < 1e-6
    assert abs(rc["compra_recomendada_m"] - 4.0) < 1e-6
    assert abs(rc["compra_recomendada_m"]
               - (rc["falta_liquida_m"] + rc["fragmentacao_m"])) < 0.01


def test_conservacao_camadas_dp():
    # Conservacao continua valendo com a atribuicao por DP e varios rolos:
    # alocadas + deficit == demanda, para todo mapa.
    dem = {0: 5, 1: 4, 2: 6}
    r = _alocar_cor(dem, {0: 9.9, 1: 8.6, 2: 4.1}, [25.0, 18.0, 12.0, 7.0], CFG)
    for mid, K in dem.items():
        assert r["camadas_alocadas"][mid] + r["camadas_em_deficit"].get(mid, 0) == K
