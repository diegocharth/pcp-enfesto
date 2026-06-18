"""
Módulo de tolerância v2.2
Premissa: minimizar desvio da grade é objetivo primário.
PP e P com sobra positiva têm custo reduzido (são tamanhos prioritários).
"""

import math


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
        lo = int(r["lo"]) if "lo" in r else -tol_geral
        hi = int(r["hi"]) if "hi" in r else tol_geral
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


def custo_desvio(cortado: dict, grade_cor: dict, tamanhos: list, config: dict) -> float:
    """
    Custo do desvio de uma cor em relação à grade.
    
    PREMISSA: minimizar desvio é objetivo primário.
    - Desvio zero = custo zero (ideal)
    - Desvio positivo em PP e P: custo reduzido (sobra aceitável, vai p/ estoque/reposição)
    - Desvio negativo em PP e P: custo alto (falta nos tamanhos mais vendidos)
    - G: qualquer desvio positivo tem custo máximo (premissa G não aumenta)
    - XPP e M: custo padrão em ambas as direções
    """
    pesos = config.get("peso_desvio_por_tamanho", {})
    prioritarios = config.get("tamanhos_prioritarios_positivo", ["PP", "P"])
    custo = 0.0

    for t in tamanhos:
        diff = cortado.get(t, 0) - grade_cor.get(t, 0)
        if diff == 0:
            continue  # desvio zero = sem custo

        peso_base = float(pesos.get(t, 1.0))

        if t in prioritarios:
            if diff > 0:
                # Sobra em PP/P: custo baixo (0.3x) — aceitável
                custo += peso_base * 0.3 * abs(diff)
            else:
                # Falta em PP/P: custo alto (2.0x) — problemático
                custo += peso_base * 2.0 * abs(diff)
        elif t == "G":
            if diff > 0:
                # G aumentando: custo máximo (3.0x) — contra a premissa
                custo += peso_base * 3.0 * abs(diff)
            else:
                # G diminuindo: custo normal
                custo += peso_base * abs(diff)
        else:
            custo += peso_base * abs(diff)

    return custo


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
