"""
Módulo de tolerância v2.2
Premissa: minimizar desvio da grade é objetivo primário.
PP e P com sobra positiva têm custo reduzido (são tamanhos prioritários).
"""

import math


def _resolver_limite(valor, grade_valor):
    """Magnitude inteira (>=0 p/ percentual) de um limite especial.
    String terminando em '%' -> relativo a grade (round); senao absoluto."""
    if isinstance(valor, str):
        s = valor.strip()
        if s.endswith('%'):
            pct = float(s[:-1].strip().replace(',', '.'))
            return int(round(float(grade_valor) * pct / 100.0))
        return int(round(float(s.replace(',', '.'))))
    return int(valor)


def calcular_limites(grade_valor: float, tamanho: str, config: dict,
                     regras_especiais: dict = None) -> tuple:
    """
    Retorna (lo, hi) — desvio mínimo e máximo permitido (cortado - grade).
    Regra: min(absoluto, percentual) — mais restritivo.
    Regras especiais sobrepõem tudo.
    """
    if regras_especiais and tamanho in regras_especiais:
        r = regras_especiais[tamanho]
        # Calcular tol geral para usar quando lo ou hi não forem informados
        tol_abs = int(config.get("desvio_absoluto_padrao", 4))
        tol_pct = max(1, round(float(grade_valor) * float(config.get("desvio_percentual_padrao", 20)) / 100.0))
        criterio = config.get("criterio_combinacao", "MIN").upper()
        tol_geral = min(tol_abs, tol_pct) if criterio == "MIN" else max(tol_abs, tol_pct)
        # 'lo': percentual -> magnitude negada; absoluto (int ou str) -> sinal preservado.
        if "lo" in r:
            v = r["lo"]
            if isinstance(v, str) and v.strip().endswith('%'):
                lo = -_resolver_limite(v, grade_valor)
            elif isinstance(v, str):
                lo = int(round(float(v.strip().replace(',', '.'))))
            else:
                lo = int(v)
        else:
            lo = -tol_geral
        hi = _resolver_limite(r["hi"], grade_valor) if "hi" in r else tol_geral
        return (lo, hi)

    tol_abs = int(config.get("desvio_absoluto_padrao", 4))
    tol_pct = max(1, round(float(grade_valor) * float(config.get("desvio_percentual_padrao", 20)) / 100.0))
    criterio = config.get("criterio_combinacao", "MIN").upper()
    tol = min(tol_abs, tol_pct) if criterio == "MIN" else max(tol_abs, tol_pct)
    return (-tol, tol)


def calcular_limites_grade(grade: dict, tamanhos: list, config: dict,
                            regras_especiais: dict = None) -> dict:
    """Retorna {cor: {tamanho: (lo, hi)}} para toda a grade."""
    limites = {}
    for cor, tam_dict in grade.items():
        limites[cor] = {}
        for t in tamanhos:
            gval = float(tam_dict.get(t, 0))
            limites[cor][t] = calcular_limites(gval, t, config, regras_especiais)
    return limites


def check_viavel(cortado: dict, grade_cor: dict, limites_cor: dict) -> bool:
    """True se cortado está dentro dos limites para todos os tamanhos."""
    for t, lim in limites_cor.items():
        diff = cortado.get(t, 0) - grade_cor.get(t, 0)
        if diff < lim[0] or diff > lim[1]:
            return False
    return True


def desvio_absoluto_total(cortado_dict: dict, grade: dict, tamanhos: list) -> int:
    """
    Soma do desvio absoluto total de todas as cores e tamanhos.
    Usado para ranqueamento primário: menor = melhor.
    """
    total = 0
    for cor in grade:
        for t in tamanhos:
            total += abs(cortado_dict[cor].get(t, 0) - grade[cor].get(t, 0))
    return total
