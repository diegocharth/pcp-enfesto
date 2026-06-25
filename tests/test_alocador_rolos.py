"""
Testes do modulo engine/alocador_rolos.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.alocador_rolos import alocar_rolos, _comp_seguro


# ---------------------------------------------------------------------------
# Fixtures de plano e config
# ---------------------------------------------------------------------------

MAPAS_BASE = [
    {"id": 0, "composicao": {"PP": 2, "P": 1, "M": 1}, "n_pecas": 4},
    {"id": 1, "composicao": {"M": 2, "G": 1},           "n_pecas": 3},
]

CONFIG_BASE = {
    "margem_seguranca_enfesto_m": 0.10,
    "folga_incerteza_pct"       : 0.03,
    "folga_incerteza_m"         : 0.0,
    "ponta_minima_util_m"       : 0.5,
}

CONSUMO = 1.0645
# comp_camada mapa 0 = 4 x 1.0645 = 4.2580
# comp_camada mapa 1 = 3 x 1.0645 = 3.1935


# ---------------------------------------------------------------------------
# 1. Trivial: 1 mapa, 1 rolo, cabe tudo -> zero deficit
# ---------------------------------------------------------------------------

def test_trivial_cabe_tudo():
    """Camadas cabem no unico rolo disponivel; zero deficit."""
    plano = {
        "mapas"      : [MAPAS_BASE[0]],
        "camadas"    : {"PRETO": {0: 5}},  # 5 camadas de mapa 0
        "consumo_peca": CONSUMO,
    }
    # comp_camada = 4.258; 5 camadas = 21.29m + margem 0.10 = 21.39m
    # comp_seguro do rolo 50m = 50 * 0.97 = 48.5m > 21.39m => cabe tudo
    rolos = {"PRETO": [50.0]}
    res = alocar_rolos(plano, rolos, CONFIG_BASE)

    assert res["por_cor"]["PRETO"]["camadas_em_deficit"] == {}
    assert res["por_cor"]["PRETO"]["camadas_alocadas"][0] == 5


# ---------------------------------------------------------------------------
# 2. Margem por sub-enfesto aplicada corretamente
# ---------------------------------------------------------------------------

def test_comp_camada_m_explicito_tem_prioridade():
    """
    Em enfesto combinado (multi-ref), o comprimento da camada nao e n_pecas x consumo
    unico -- e a soma de pecas x consumo de cada referencia. O alocador deve usar o
    comp_camada_m informado por mapa quando presente, ignorando n_pecas x consumo.
    """
    plano = {
        "mapas": [{"id": 0, "composicao": {"PP": 2, "P": 1, "M": 1}, "n_pecas": 4,
                   "comp_camada_m": 8.0}],
        "camadas": {"PRETO": {0: 5}},
        "consumo_peca": 1.0,
    }
    res = alocar_rolos(plano, {"PRETO": [60.0]}, dict(CONFIG_BASE))
    e = res["por_cor"]["PRETO"]["enfestos"][0]
    assert e["comp_camada_m"] == 8.0
    assert abs(e["tecido_usado_m"] - 40.10) < 1e-3   # 5*8.0 + 0.10


def test_margem_uma_vez_por_enfesto():
    """
    1 rolo, 1 mapa, N camadas.
    tecido_usado do enfesto deve ser N * comp_camada + margem (so uma vez).
    """
    plano = {"mapas": [{"id": 0, "composicao": {"PP": 2, "P": 1, "M": 1}, "n_pecas": 4}],
             "camadas": {"PRETO": {0: 10}}, "consumo_peca": CONSUMO}
    res = alocar_rolos(plano, {"PRETO": [100.0]}, dict(CONFIG_BASE))
    e = res["por_cor"]["PRETO"]["enfestos"][0]
    assert e["camadas_cobertas"] == 10
    assert abs(e["tecido_usado_m"] - (10 * 4 * CONSUMO + 0.10)) < 1e-3


# ---------------------------------------------------------------------------
# 3. comp_seguro: alocacao respeita nominal x (1-pct), nunca o nominal cheio
# ---------------------------------------------------------------------------

def test_comp_seguro_nao_usa_nominal():
    """
    Rolo de 10.00m. 3% de folga = comp_seguro de 9.70m.
    Uma unica camada de 9.80m nao cabe em 9.70m -> deve ir para deficit.
    """
    # mapa com 2 pecas de consumo grande
    plano = {
        "mapas"      : [{"id": 0, "composicao": {"M": 2}, "n_pecas": 2}],
        "camadas"    : {"PRETO": {0: 1}},
        "consumo_peca": 4.90,  # comp_camada = 9.80m
    }
    rolos = {"PRETO": [10.0]}
    res = alocar_rolos(plano, rolos, CONFIG_BASE)
    # comp_seguro = 10.0 * 0.97 = 9.70 < 9.80 => nao cabe
    assert res["por_cor"]["PRETO"]["camadas_em_deficit"].get(0, 0) == 1

    # Se usassemos comp = 10.0 nominal, 9.80 + 0.10 margem = 9.90 <= 10.0 => caberia (ERRADO)
    # O teste garante que isso nao acontece.


def test_comp_seguro_formula_percentual():
    """_comp_seguro com pct deve retornar nominal * (1 - pct)."""
    assert abs(_comp_seguro(100.0, {"folga_incerteza_pct": 0.03}) - 97.0) < 0.001


def test_comp_seguro_formula_fixo():
    """_comp_seguro com folga_incerteza_m deve retornar nominal - m."""
    assert abs(_comp_seguro(100.0, {"folga_incerteza_m": 2.0}) - 98.0) < 0.001


# ---------------------------------------------------------------------------
# 4. Reaproveitamento real: ponta de enfesto longo vira camada de enfesto curto
# ---------------------------------------------------------------------------

def test_reaproveitamento_real_mapa_longo_para_curto():
    """
    Enfesto do mapa 0 (cc=7.8) deixa uma ponta grande no rolo; o mapa 1 (cc=3.9)
    reaproveita essa ponta como camada inteira (sem emenda).
    """
    # Rolo unico de 24.0m: seguro = 23.28m.
    # mapa 0 (cc=7.8), 2 camadas -> 2*7.8 + 0.10 = 15.70m usado; ponta = 7.58m.
    # mapa 1 (cc=3.9): ponta 7.58 >= cc+margem (4.0) -> 1 camada reaproveitada.
    plano = {
        "mapas": [{"id": 0, "composicao": {"M": 6}, "n_pecas": 6},
                  {"id": 1, "composicao": {"P": 3}, "n_pecas": 3}],
        "camadas": {"PRETO": {0: 2, 1: 1}}, "consumo_peca": 1.3,
    }  # cc0 = 7.8, cc1 = 3.9
    res = alocar_rolos(plano, {"PRETO": [24.0]}, dict(CONFIG_BASE))
    cr = res["por_cor"]["PRETO"]
    assert [e["mapa_id"] for e in cr["enfestos"]] == [0, 1]
    assert cr["reaproveitamento"]["camadas_reaproveitadas"] >= 1
    e1 = [e for e in cr["enfestos"] if e["mapa_id"] == 1][0]
    assert any(f["reaproveitada"] for f in e1["fontes"])


# ---------------------------------------------------------------------------
# 5. Classificacao de ponta
# ---------------------------------------------------------------------------

def test_ponta_estoque():
    """Ponta >= ponta_minima_util_m deve ser classificada como estoque."""
    plano = {"mapas": [{"id": 0, "composicao": {"P": 4}, "n_pecas": 4}],
             "camadas": {"PRETO": {0: 1}}, "consumo_peca": 1.0}  # cc=4.0
    res = alocar_rolos(plano, {"PRETO": [10.0]}, dict(CONFIG_BASE))
    rolo = res["por_cor"]["PRETO"]["rolos"][0]
    assert rolo["ponta_classe"] == "estoque"
    assert rolo["ponta_m"] >= CONFIG_BASE["ponta_minima_util_m"]


def test_ponta_refugo():
    """Ponta < ponta_minima_util_m deve ser classificada como refugo."""
    plano = {"mapas": [{"id": 0, "composicao": {"P": 4}, "n_pecas": 4}],
             "camadas": {"PRETO": {0: 2}}, "consumo_peca": 1.0}  # cc=4.0
    # Rolo nominal 8.5m -> seguro = 8.5 * 0.97 = 8.245m.
    # 2 camadas usam 2*4.0 + 0.10 (margem) = 8.10m; ponta = 8.245 - 8.10 = 0.145m < 0.5 -> refugo.
    res = alocar_rolos(plano, {"PRETO": [8.5]}, dict(CONFIG_BASE))
    rolo = res["por_cor"]["PRETO"]["rolos"][0]
    assert rolo["ponta_classe"] == "refugo"


# ---------------------------------------------------------------------------
# 6. Deficit: rolos insuficientes -> reporta faltantes
# ---------------------------------------------------------------------------

def test_deficit_rolos_insuficientes():
    """Rolos nao cobrem toda a demanda -> camadas_em_deficit > 0."""
    plano = {
        "mapas"      : [MAPAS_BASE[0]],
        "camadas"    : {"PRETO": {0: 20}},  # 20 camadas
        "consumo_peca": CONSUMO,
    }
    # 20 camadas x 4.258m + margem = ~85.26m; rolo de 10m (seguro 9.7m) so cabe 2 camadas
    rolos = {"PRETO": [10.0]}
    res = alocar_rolos(plano, rolos, CONFIG_BASE)
    deficit = res["por_cor"]["PRETO"]["camadas_em_deficit"].get(0, 0)
    assert deficit > 0, "Esperava deficit com rolo insuficiente"
    assert res["por_cor"]["PRETO"]["tecido_a_comprar_m"] > 0


def test_deficit_sem_rolos():
    """Cor sem nenhum rolo disponivel -> tudo em deficit."""
    plano = {
        "mapas"      : [MAPAS_BASE[0]],
        "camadas"    : {"PRETO": {0: 5}},
        "consumo_peca": CONSUMO,
    }
    rolos = {}  # sem rolos
    res = alocar_rolos(plano, rolos, CONFIG_BASE)
    assert "PRETO" in res["resumo_geral"]["cores_com_deficit"]
    assert res["por_cor"]["PRETO"]["camadas_em_deficit"][0] == 5


# ---------------------------------------------------------------------------
# 7. Camada maior que qualquer rolo -> alerta critico
# ---------------------------------------------------------------------------

def test_camada_maior_que_rolo():
    """Camada que nao cabe em nenhum rolo deve gerar alerta critico."""
    plano = {
        "mapas"      : [{"id": 0, "composicao": {"M": 5}, "n_pecas": 5}],
        "camadas"    : {"PRETO": {0: 1}},
        "consumo_peca": 3.0,  # comp_camada = 15.0m
    }
    rolos = {"PRETO": [10.0]}  # comp_seguro = 9.7m < 15.0m
    res = alocar_rolos(plano, rolos, CONFIG_BASE)
    alertas_texto = " ".join(res["resumo_geral"]["alertas"])
    assert "CRITICO" in alertas_texto or "nao cabe" in alertas_texto.lower()
    assert res["por_cor"]["PRETO"]["camadas_em_deficit"].get(0, 0) == 1


# ---------------------------------------------------------------------------
# 8. Regra dura: usado_m <= seguro_m para todo rolo; ponta nunca negativa
# ---------------------------------------------------------------------------

def test_regra_dura_nunca_violada():
    """O tecido usado em cada rolo nunca pode exceder o comp_seguro; ponta >= 0."""
    plano = {"mapas": MAPAS_BASE, "camadas": {"PRETO": {0: 8, 1: 6}}, "consumo_peca": CONSUMO}
    res = alocar_rolos(plano, {"PRETO": [30.0, 25.0, 20.0]}, dict(CONFIG_BASE))
    for rolo in res["por_cor"]["PRETO"]["rolos"]:
        assert rolo["usado_m"] <= rolo["seguro_m"] + 1e-3
        assert rolo["ponta_m"] >= -1e-9


# ---------------------------------------------------------------------------
# 9. Conservacao: alocadas + deficit == demanda original
# ---------------------------------------------------------------------------

def test_conservacao_camadas():
    """Camadas alocadas + deficit deve igualar a demanda original."""
    plano = {
        "mapas"      : MAPAS_BASE,
        "camadas"    : {"PRETO": {0: 10, 1: 7}},
        "consumo_peca": CONSUMO,
    }
    rolos = {"PRETO": [30.0, 20.0]}
    res = alocar_rolos(plano, rolos, CONFIG_BASE)

    cor_res  = res["por_cor"]["PRETO"]
    demanda  = plano["camadas"]["PRETO"]
    for mid, n_dem in demanda.items():
        n_aloc = cor_res["camadas_alocadas"].get(mid, 0)
        n_def  = cor_res["camadas_em_deficit"].get(mid, 0)
        assert n_aloc + n_def == n_dem, (
            f"mapa {mid}: {n_aloc} alocadas + {n_def} deficit != {n_dem} demanda"
        )


# ---------------------------------------------------------------------------
# 10. Input invalido -> ValueError com mensagem clara
# ---------------------------------------------------------------------------

def test_consumo_invalido():
    plano = {"mapas": [MAPAS_BASE[0]], "camadas": {"PRETO": {0: 1}}, "consumo_peca": 0}
    with pytest.raises(ValueError, match="consumo_peca"):
        alocar_rolos(plano, {"PRETO": [10.0]}, CONFIG_BASE)


def test_margem_negativa():
    plano = {"mapas": [MAPAS_BASE[0]], "camadas": {"PRETO": {0: 1}}, "consumo_peca": CONSUMO}
    cfg = dict(CONFIG_BASE, margem_seguranca_enfesto_m=-0.1)
    with pytest.raises(ValueError, match="margem"):
        alocar_rolos(plano, {"PRETO": [10.0]}, cfg)


# ---------------------------------------------------------------------------
# 11. Multiplas cores independentes
# ---------------------------------------------------------------------------

def test_multiplas_cores_independentes():
    """Resultado de uma cor nao interfere na outra."""
    plano = {
        "mapas"      : MAPAS_BASE,
        "camadas"    : {
            "PRETO"  : {0: 5, 1: 3},
            "BRANCO" : {0: 4, 1: 2},
        },
        "consumo_peca": CONSUMO,
    }
    rolos = {
        "PRETO"  : [50.0, 30.0],
        "BRANCO" : [40.0],
    }
    res = alocar_rolos(plano, rolos, CONFIG_BASE)
    assert "PRETO" in res["por_cor"]
    assert "BRANCO" in res["por_cor"]
    # Ambas devem ter zero deficit com rolos suficientes
    assert res["por_cor"]["PRETO"]["camadas_em_deficit"] == {}
    assert res["por_cor"]["BRANCO"]["camadas_em_deficit"] == {}


# ---------------------------------------------------------------------------
# 12. folga_incerteza_m fixo (alternativa ao percentual)
# ---------------------------------------------------------------------------

def test_folga_fixa():
    """Com folga_incerteza_m=2.0, comp_seguro = nominal - 2."""
    cfg = dict(CONFIG_BASE, folga_incerteza_m=2.0)
    seg = _comp_seguro(100.0, cfg)
    assert abs(seg - 98.0) < 0.001


def test_resultado_inclui_bloco_params():
    """A3: o resultado deve carregar os parametros de alocacao usados, para
    aparecerem no Excel sem depender do frontend."""
    plano = {
        "mapas": [{"id": 0, "n_pecas": 4}],
        "camadas": {"AZUL": {0: 3}},
        "consumo_peca": 1.0,
    }
    rolos = {"AZUL": [20.0]}
    cfg = dict(CONFIG_BASE)
    cfg["margem_seguranca_enfesto_m"] = 0.10
    cfg["folga_incerteza_pct"] = 0.03
    cfg["folga_incerteza_m"] = 0.0
    cfg["ponta_minima_util_m"] = 0.5

    res = alocar_rolos(plano, rolos, cfg)

    assert "params" in res
    p = res["params"]
    assert p["margem_seguranca_enfesto_m"] == 0.10
    assert p["folga_incerteza_pct"] == 0.03
    assert p["folga_incerteza_m"] == 0.0
    assert p["ponta_minima_util_m"] == 0.5


def test_rolos_resumo_e_consolidado():
    """C3: cada cor expoe o resumo por rolo; resumo_geral expoe sobras_consolidado."""
    plano = {"mapas": [{"id": 0, "composicao": {"P": 4}, "n_pecas": 4}],
             "camadas": {"AZUL": {0: 2}}, "consumo_peca": 1.0}
    res = alocar_rolos(plano, {"AZUL": [20.0]}, dict(CONFIG_BASE))
    cr = res["por_cor"]["AZUL"]
    assert len(cr["rolos"]) == 1
    r0 = cr["rolos"][0]
    for k in ("rolo_indice", "nominal_m", "seguro_m", "usado_m", "ponta_m", "ponta_classe"):
        assert k in r0
    assert "sobras_consolidado" in res["resumo_geral"]
    assert "AZUL" in res["resumo_geral"]["sobras_consolidado"]


def test_resumo_geral_tem_reaproveitamento():
    plano = {"mapas": [{"id": 0, "composicao": {"M": 6}, "n_pecas": 6},
                       {"id": 1, "composicao": {"P": 3}, "n_pecas": 3}],
             "camadas": {"PRETO": {0: 2, 1: 1}}, "consumo_peca": 1.3}
    res = alocar_rolos(plano, {"PRETO": [24.0]}, dict(CONFIG_BASE))
    rg = res["resumo_geral"]
    assert "camadas_reaproveitadas_total" in rg
    assert "tecido_economizado_total_m" in rg
    assert "sugestoes_corte_total" not in rg


def test_export_alocacao_tem_sobras_e_enfestos():
    import tempfile, openpyxl
    from exportar.export_xlsx import exportar_alocacao
    plano = {"mapas": [{"id": 0, "composicao": {"M": 6}, "n_pecas": 6},
                       {"id": 1, "composicao": {"P": 3}, "n_pecas": 3}],
             "camadas": {"AZUL": {0: 2, 1: 1}}, "consumo_peca": 1.3}
    res = alocar_rolos(plano, {"AZUL": [24.0]}, dict(CONFIG_BASE))
    with tempfile.TemporaryDirectory() as d:
        cam = exportar_alocacao(res, "TESTE", d, {**res.get("params", {}), "versao": "x"})
        wb = openpyxl.load_workbook(cam)
        ws = [s for s in wb.sheetnames if s.startswith("Rolos")][0]
        textos = " ".join(str(c.value) for row in wb[ws].iter_rows()
                           for c in row if c.value is not None)
    assert "Sobras por rolo" in textos
    assert "Mapa" in textos
    assert "Corte separado" not in textos
