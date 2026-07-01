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
    assert hi == 4  # 40 * 10,5% = 4,2 -> desce para 4


def test_percentual_meio_sobe_regra_comercial():
    """Regra do Diego: fracao 0,5..0,99 sobe. 25 * 10% = 2,5 -> 3.
    O round() nativo (bancario) daria 2 -- por isso o helper proprio."""
    lo, hi = calcular_limites(25, "M", CFG, {"M": {"hi": "10%"}})
    assert hi == 3


def test_percentual_049_desce_050_sobe():
    """Fronteira exata: 0,49 desce (0) e 0,50 sobe (1)."""
    _, hi049 = calcular_limites(49, "M", CFG, {"M": {"hi": "1%"}})   # 0,49
    assert hi049 == 0
    _, hi050 = calcular_limites(5, "M", CFG, {"M": {"hi": "10%"}})   # 0,50
    assert hi050 == 1


def test_percentual_024_desce_075_sobe():
    """0,24 desce (0); 0,75 (>= 0,5) sobe (1)."""
    _, hi024 = calcular_limites(24, "M", CFG, {"M": {"hi": "1%"}})   # 0,24
    assert hi024 == 0
    _, hi075 = calcular_limites(3, "M", CFG, {"M": {"hi": "25%"}})   # 0,75
    assert hi075 == 1


def test_tol_pct_padrao_meio_sobe():
    """A regra vale tambem para a tolerancia % padrao (nao so limites especiais).
    grade 25, tol% 10 -> 2,5 -> 3 (com tol_abs baixo e criterio MAX p/ isolar o %)."""
    cfg = {"desvio_absoluto_padrao": 0, "desvio_percentual_padrao": 10,
           "criterio_combinacao": "MAX"}
    lo, hi = calcular_limites(25, "M", cfg, {})
    assert (lo, hi) == (-3, 3)


def test_limites_ausentes_usam_tol_geral():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {}})
    assert (lo, hi) == (-4, 4)


def test_retrocompat_g_hi_zero_int():
    lo, hi = calcular_limites(12, "G", CFG, {"G": {"hi": 0}})
    assert hi == 0
