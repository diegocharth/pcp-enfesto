"""
Testes do alocador v2.13: rolos com metadados (nº, lote, largura, cor do
fornecedor) e o modo "Considerar Lote".
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.alocador_rolos import alocar_rolos

CONFIG = {
    "margem_seguranca_enfesto_m": 0.10,
    "folga_incerteza_pct": 0.03,
    "folga_incerteza_m": 0.0,
    "ponta_minima_util_m": 0.5,
}

PLANO = {
    "mapas": [{"id": 1, "composicao": {"P": 2, "M": 2}, "n_pecas": 4},
              {"id": 2, "composicao": {"G": 1}, "n_pecas": 1}],
    "camadas": {"AZUL": {1: 10, 2: 5}},
    "consumo_peca": 1.0,
}
# demanda: 10 camadas de 4m + 5 de 1m = 45m + 2 margens


def _rolo(comp, rid=None, lote=None, larg=None, cf=None):
    return {"comprimento_m": comp, "rolo_id": rid, "lote": lote,
            "largura_m": larg, "cor_fornecedor": cf}


def test_retrocompat_numeros_e_dicts_dao_o_mesmo_resultado():
    """Entrada numerica (manual) e dicts sem metadados devem alocar identico."""
    rolos_num  = {"AZUL": [30.0, 20.0, 10.0]}
    rolos_dict = {"AZUL": [_rolo(30.0), _rolo(20.0), _rolo(10.0)]}
    r1 = alocar_rolos(PLANO, rolos_num, dict(CONFIG))
    r2 = alocar_rolos(PLANO, rolos_dict, dict(CONFIG))
    c1, c2 = r1["por_cor"]["AZUL"], r2["por_cor"]["AZUL"]
    assert c1["tecido_usado_m"] == c2["tecido_usado_m"]
    assert c1["tecido_a_comprar_m"] == c2["tecido_a_comprar_m"]
    assert c1["camadas_alocadas"] == c2["camadas_alocadas"]
    assert [x["usado_m"] for x in c1["rolos"]] == [x["usado_m"] for x in c2["rolos"]]


def test_metadados_chegam_no_resultado():
    rolos = {"AZUL": [_rolo(30.0, "4347", "L1", 1.40, "FRAPE"),
                      _rolo(20.0, "4348", "L2", 1.41, "FRAPE")]}
    r = alocar_rolos(PLANO, rolos, dict(CONFIG))
    cr = r["por_cor"]["AZUL"]
    por_id = {x["rolo_indice"]: x for x in cr["rolos"]}
    assert por_id[1]["rolo_id"] == "4347" and por_id[1]["lote"] == "L1"
    assert por_id[1]["largura_m"] == 1.40 and por_id[1]["cor_fornecedor"] == "FRAPE"
    assert por_id[2]["rolo_id"] == "4348"
    # fontes tambem carregam os metadados
    fontes = [f for e in cr["enfestos"] for f in e["fontes"]]
    assert fontes and all("rolo_id" in f and "lote" in f for f in fontes)


def test_considerar_lote_escolhe_lote_unico():
    """Ha um lote que cobre tudo sozinho -- com a flag, so ele e usado."""
    rolos = {"AZUL": [
        _rolo(25.0, "1", "A"), _rolo(25.0, "2", "A"),   # lote A: 50m (cobre)
        _rolo(30.0, "3", "B"),                            # lote B: 30m
        _rolo(28.0, "4", "C"),                            # lote C: 28m
    ]}
    r = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": True})
    cr = r["por_cor"]["AZUL"]
    assert cr["camadas_em_deficit"] == {}
    assert cr["lotes"]["utilizados"] == ["A"]
    assert cr["lotes"]["considerado"] is True
    # sem a flag, o alocador e livre para misturar
    r2 = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": False})
    assert r2["por_cor"]["AZUL"]["lotes"]["considerado"] is False


def test_considerar_lote_minimiza_quando_um_so_nao_da():
    """Nenhum lote cobre sozinho; dois lotes especificos cobrem -- usa 2, nao 3."""
    rolos = {"AZUL": [
        _rolo(25.0, "1", "A"),
        _rolo(25.0, "2", "B"),
        _rolo(12.0, "3", "C"),
        _rolo(10.0, "4", "D"),
    ]}
    r = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": True})
    cr = r["por_cor"]["AZUL"]
    assert cr["camadas_em_deficit"] == {}
    assert len(cr["lotes"]["utilizados"]) == 2
    assert any("nao foi possivel atender com um unico lote" in a
               for a in r["resumo_geral"]["alertas"])


def test_considerar_lote_com_deficit_usa_todos():
    """Se nem todos os rolos juntos cobrem, a restricao de lote e ignorada."""
    rolos = {"AZUL": [_rolo(10.0, "1", "A"), _rolo(10.0, "2", "B")]}
    r = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": True})
    cr = r["por_cor"]["AZUL"]
    assert cr["tecido_a_comprar_m"] > 0
    assert any("restricao de lote foi ignorada" in a
               for a in r["resumo_geral"]["alertas"])


def test_rolos_fora_do_subconjunto_aparecem_como_nao_usados():
    rolos = {"AZUL": [
        _rolo(50.0, "1", "A"),
        _rolo(30.0, "2", "B"),
    ]}
    r = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": True})
    cr = r["por_cor"]["AZUL"]
    assert cr["lotes"]["utilizados"] == ["A"]
    assert len(cr["rolos"]) == 2   # o rolo do lote B aparece, zerado
    rolo_b = [x for x in cr["rolos"] if x["rolo_indice"] == 2][0]
    assert rolo_b["usado_m"] == 0.0
    assert rolo_b["rolo_id"] == "2"
    # indices das fontes referenciam a numeracao ORIGINAL
    assert all(f["rolo_indice"] == 1 for e in cr["enfestos"] for f in e["fontes"])


def test_alerta_de_larguras_misturadas():
    rolos = {"AZUL": [_rolo(30.0, "1", "A", 1.40), _rolo(20.0, "2", "A", 1.46)]}
    r = alocar_rolos(PLANO, rolos, dict(CONFIG))
    cr = r["por_cor"]["AZUL"]
    assert cr["larguras_utilizadas"] == [1.4, 1.46]
    assert any("larguras diferentes" in a for a in r["resumo_geral"]["alertas"])


def test_sem_largura_nao_gera_alerta():
    rolos = {"AZUL": [30.0, 20.0]}
    r = alocar_rolos(PLANO, rolos, dict(CONFIG))
    assert not any("largura" in a.lower() for a in r["resumo_geral"]["alertas"])
    assert r["por_cor"]["AZUL"]["larguras_utilizadas"] == []


def test_desempate_por_largura_no_modo_lote():
    """Dois lotes cobrem sozinhos; o de largura unica... ambos tem 1 largura,
    entao desempata por menor sobra: o lote mais justo vence."""
    rolos = {"AZUL": [
        _rolo(60.0, "1", "GRANDE", 1.40),   # sobra muita ponta
        _rolo(48.0, "2", "JUSTO", 1.40),    # cobre com pouca sobra
    ]}
    r = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": True})
    cr = r["por_cor"]["AZUL"]
    assert cr["lotes"]["utilizados"] == ["JUSTO"]


def test_sem_lote_agrupa_como_pseudo_lote():
    """Rolos sem lote (None) formam o grupo S/LOTE e podem atender sozinhos."""
    rolos = {"AZUL": [_rolo(50.0, "1", None), _rolo(30.0, "2", "B")]}
    r = alocar_rolos(PLANO, rolos, {**CONFIG, "considerar_lote": True})
    cr = r["por_cor"]["AZUL"]
    assert cr["lotes"]["utilizados"] == ["S/LOTE"]


# ---------------------------------------------------------------------------
# Regressoes da revisao adversarial v2.13
# ---------------------------------------------------------------------------

def test_nan_e_infinito_sao_descartados():
    """NaN/inf no comprimento nao podem vazar para a resposta (JSON invalido)."""
    import math, json
    rolos = {"AZUL": [float("nan"), 30.0, float("inf"),
                      _rolo(float("nan")), _rolo(20.0)]}
    r = alocar_rolos(PLANO, rolos, dict(CONFIG))
    cr = r["por_cor"]["AZUL"]
    assert len(cr["rolos"]) == 2   # so os rolos 30 e 20 sobram
    json.dumps(r, allow_nan=False)  # nao pode haver NaN em lugar nenhum
