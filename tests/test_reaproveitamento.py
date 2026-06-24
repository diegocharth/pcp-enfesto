"""C1: sugerir_corte_separado monta cortes avulsos que cabem nas pontas
reaproveitaveis (sem emenda), cobrindo deficit sem comprar tecido."""
from engine.reaproveitamento import sugerir_corte_separado

COMP = {0: 7.8}
COMPOS = {0: {"P": 3, "M": 3}}
CPP = {0: 1.3}
MARGEM = 0.10


def test_sem_pontas_nao_sugere():
    sugs = sugerir_corte_separado({0: 2}, COMP, COMPOS, CPP, [], MARGEM)
    assert sugs == []


def test_camada_inteira_cabe_em_ponta():
    sugs = sugerir_corte_separado({0: 1}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 1, "ponta_m": 8.0}], MARGEM)
    assert len(sugs) == 1
    s = sugs[0]
    assert s["mapa_id"] == 0
    assert s["rotulo"] == "camada inteira"
    assert s["camadas_cobertas"] == 1
    assert s["deficit_residual_camadas"] == 0
    assert s["cortes"][0]["rolo_origem_indice"] == 1
    assert s["cortes"][0]["n_camadas"] == 1


def test_margem_respeitada_nao_gera_emenda():
    sugs = sugerir_corte_separado({0: 1}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 0, "ponta_m": 7.85}], MARGEM)
    assert len(sugs) == 1
    s = sugs[0]
    assert s["rotulo"] != "camada inteira"
    assert s["cortes"][0]["comp_total"] <= 7.85 + 1e-9


def test_varias_camadas_numa_ponta_uma_margem():
    sugs = sugerir_corte_separado({0: 5}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 0, "ponta_m": 24.0}], MARGEM)
    s = sugs[0]
    assert s["cortes"][0]["n_camadas"] == 3
    assert s["cortes"][0]["comp_total"] == round(3 * 7.8 + 0.10, 4)
    assert s["deficit_residual_camadas"] == 2


def test_combina_varias_pontas_sem_emenda():
    sugs = sugerir_corte_separado({0: 2}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 0, "ponta_m": 8.0},
                                   {"rolo_origem_indice": 1, "ponta_m": 8.0}], MARGEM)
    s = sugs[0]
    assert s["camadas_cobertas"] == 2
    assert len(s["cortes"]) == 2
    assert s["deficit_residual_camadas"] == 0
