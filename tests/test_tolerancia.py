"""B2: calcular_limites aceita limite especial absoluto (com sinal preservado)
ou percentual ('N%', relativo a grade). Regra critica: so o ramo percentual
nega a magnitude do lo; o absoluto preserva o sinal digitado."""
from engine.tolerancia import calcular_limites

CFG = {"desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN"}


def test_lo_absoluto_int_preserva_sinal():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"lo": -4, "hi": 4}})
    assert (lo, hi) == (-4, 4)


def test_lo_absoluto_str_preserva_sinal():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"lo": "-4", "hi": "4"}})
    assert (lo, hi) == (-4, 4)


def test_hi_percentual_grade_40():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"hi": "10%"}})
    assert hi == 4
    assert lo == -4


def test_lo_percentual_magnitude_negada():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"lo": "10%"}})
    assert lo == -4


def test_percentual_zero():
    lo, hi = calcular_limites(40, "G", CFG, {"G": {"hi": "0%"}})
    assert hi == 0


def test_percentual_virgula_decimal():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"hi": "10,5%"}})
    assert hi == round(40 * 10.5 / 100)  # round(4.2) == 4


def test_limites_ausentes_usam_tol_geral():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {}})
    assert (lo, hi) == (-4, 4)


def test_retrocompat_g_hi_zero_int():
    lo, hi = calcular_limites(12, "G", CFG, {"G": {"hi": 0}})
    assert hi == 0
