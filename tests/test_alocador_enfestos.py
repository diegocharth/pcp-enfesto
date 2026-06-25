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
