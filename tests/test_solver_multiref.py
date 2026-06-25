"""
Testes do solver multi-referencia (engine/solver_multiref.py).

Regressao: o calculo combinado crashava ao computar total_pecas (somava
dict_values em vez de inteiros). Aqui garantimos que um grupo simples de
2 referencias produz solucao valida.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.solver_multiref import resolver_multiref
from engine.tolerancia import calcular_limites_grade

CFG = {
    "mesa_comprimento_m": 10.0,
    "limite_folhas_padrao": 70,
    "num_opcoes_saida": 2,
    "desvio_absoluto_padrao": 4,
    "desvio_percentual_padrao": 20,
    "criterio_combinacao": "MIN",
}
TAMS = ["PP", "P", "M", "G"]


def _ref(nome, grade, consumo=1.0645):
    cfg_r = dict(CFG); cfg_r["consumo_peca_m"] = consumo
    return {
        "nome": nome,
        "grade": grade,
        "consumo": consumo,
        "limites": calcular_limites_grade(grade, TAMS, cfg_r, {}),
    }


def test_grupo_2_refs_retorna_solucao_valida():
    """2 referencias, 1 cor cada -> deve produzir ao menos uma solucao combinada."""
    refs = [
        _ref("VESTIDO", {"BLUES": {"PP": 10, "P": 12, "M": 6, "G": 2}}),
        _ref("CAMISA",  {"BLUES": {"PP": 8,  "P": 10, "M": 5, "G": 2}}),
    ]
    sols = resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=30)
    assert sols, "deveria retornar ao menos uma solucao combinada"
    s = sols[0]
    assert s["resumo"]["n_mapas"] >= 1
    # total de pecas coerente: media_pecas_mapa > 0
    assert s["resumo"]["media_pecas_mapa"] > 0


def test_n_mapas_max_limita_a_busca():
    """Com n_mapas_max=2, nenhuma solucao retornada pode ter mais de 2 enfestos.

    Este e o nucleo do branch-and-bound: combinar refs so vale se usar MENOS
    enfestos que mante-las separadas. Limitar a busca evita gastar minutos
    procurando combinacoes profundas que serao descartadas de qualquer forma.
    """
    refs = [
        _ref("A", {"BLUES": {"PP": 40, "P": 40, "M": 17, "G": 2}}, consumo=2.48),
        _ref("B", {"BLUES": {"PP": 75, "P": 101, "M": 54, "G": 19}}, consumo=1.37),
    ]
    sols = resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=20, n_mapas_max=2)
    for s in sols:
        assert s["resumo"]["n_mapas"] <= 2, f"violou n_mapas_max: {s['resumo']['n_mapas']}"


def test_convergiu_flag_setado_apos_busca_completa():
    """Apos uma busca que termina sem estourar o timeout, _convergiu deve ser True.

    main.py usa esse sinal exato para so cachear/aprender tempos de buscas completas
    (evita vies na ETA), em vez de uma heuristica de tempo.
    """
    refs = [
        _ref("A", {"BLUES": {"PP": 4, "P": 4, "M": 2}}),
        _ref("B", {"BLUES": {"PP": 3, "P": 3, "M": 1}}),
    ]
    _r = {}
    resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=60, resume_out=_r)
    assert _r.get("convergiu") is True


def test_n_mapas_max_zero_retorna_vazio():
    """n_mapas_max < 1 significa 'combinar nao ajuda' -> retorna vazio sem buscar."""
    refs = [
        _ref("A", {"BLUES": {"PP": 10, "P": 12}}),
        _ref("B", {"BLUES": {"PP": 8, "P": 10}}),
    ]
    sols = resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=20, n_mapas_max=0)
    assert sols == []


def test_grupo_2_refs_estrutura_da_solucao():
    """A solucao traz uma composicao por referencia em cada enfesto."""
    refs = [
        _ref("A", {"PRETO": {"PP": 6, "P": 6, "M": 3, "G": 1}}),
        _ref("B", {"PRETO": {"PP": 5, "P": 5, "M": 2, "G": 1}}),
    ]
    sols = resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=30)
    assert sols
    s = sols[0]
    n = s["resumo"]["n_mapas"]
    assert len(s["refs_sol"]) == 2
    for rs in s["refs_sol"]:
        assert len(rs["mapas"]) == n  # uma composicao por enfesto
