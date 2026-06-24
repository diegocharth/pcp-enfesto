"""
PCP Enfestos -- Reaproveitamento de pontas (corte separado) v1.0
================================================================

Passo POS-ALOCACAO. Nao altera o plano de corte nem a alocacao principal.
Quando sobra deficit numa cor, tenta cobri-lo cortando pecas avulsas nas
PONTAS reaproveitaveis (>= ponta_minima_util) que ja sobraram nos rolos
daquela cor -- evitando comprar tecido novo.

Regras:
  - Sem emenda: cada conjunto de k camadas e casado contra UMA ponta individual
    (nunca soma duas pontas numa mesma camada).
  - Margem de faca: paga UMA vez por sub-enfesto (k*comp + margem <= ponta).
  - Candidatos por mapa em deficit, do maior para o menor comprimento:
      1) camada inteira do mapa;
      2) submapa reduzido (metade; 1-de-cada) -- so quando a camada inteira
         nao cabe em nenhuma ponta.
"""

import math

_EPS = 0.0001


def _gerar_candidatos(mid, comp_camada_por_id, composicao_por_id, cpp_por_id):
    """Lista [(comp_m, composicao, rotulo)] do maior para o menor comprimento."""
    base = composicao_por_id.get(mid, {}) or {}
    cpp = float(cpp_por_id.get(mid, 0.0))
    cands = [(float(comp_camada_por_id.get(mid, 0.0)), dict(base), "camada inteira")]
    total_base = sum(base.values())

    meia = {t: int(round(q / 2.0)) for t, q in base.items() if int(round(q / 2.0)) > 0}
    if meia and sum(meia.values()) < total_base and cpp > 0:
        cands.append((sum(meia.values()) * cpp, meia, "metade"))

    umdecada = {t: 1 for t, q in base.items() if q > 0}
    if umdecada and sum(umdecada.values()) < total_base and cpp > 0:
        cands.append((sum(umdecada.values()) * cpp, umdecada, "1 de cada"))

    cands.sort(key=lambda c: -c[0])
    return cands


def sugerir_corte_separado(deficit, comp_camada_por_id, composicao_por_id,
                           cpp_por_id, pontas, margem):
    """
    Args:
        deficit: {mapa_id(int): n_camadas_faltantes(int)}
        comp_camada_por_id: {mapa_id: comprimento_camada_m}
        composicao_por_id:  {mapa_id: {tam: qtd}}
        cpp_por_id:         {mapa_id: comprimento_por_peca_m}
        pontas: [{"rolo_origem_indice": int, "ponta_m": float}, ...] (pontas estoque da cor)
        margem: float (margem de faca por sub-enfesto)
    Returns:
        [{"mapa_id","rotulo","composicao","comp_camada","camadas_cobertas",
          "cortes":[{"rolo_origem_indice","n_camadas","comp_camada","comp_total","ponta_usada_m"}],
          "deficit_residual_camadas"}]
    """
    margem = float(margem)
    rem = [[int(p["rolo_origem_indice"]), float(p["ponta_m"])] for p in pontas]
    rem.sort(key=lambda x: -x[1])

    sugestoes = []
    for mid in sorted((m for m, n in deficit.items() if n > 0),
                      key=lambda m: -comp_camada_por_id.get(m, 0.0)):
        n_falta = int(deficit[mid])
        candidatos = _gerar_candidatos(mid, comp_camada_por_id, composicao_por_id, cpp_por_id)
        for comp, compos_sub, rotulo in candidatos:
            if comp <= 0 or n_falta <= 0:
                continue
            cortes = []
            for slot in rem:
                if n_falta <= 0:
                    break
                k = int(math.floor((slot[1] - margem + _EPS) / comp))
                if k <= 0:
                    continue
                k = min(k, n_falta)
                comp_total = round(k * comp + margem, 4)
                cortes.append({
                    "rolo_origem_indice": slot[0],
                    "n_camadas": k,
                    "comp_camada": round(comp, 4),
                    "comp_total": comp_total,
                    "ponta_usada_m": round(slot[1], 4),
                })
                slot[1] -= (k * comp + margem)
                n_falta -= k
            if cortes:
                sugestoes.append({
                    "mapa_id": mid,
                    "rotulo": rotulo,
                    "composicao": compos_sub,
                    "comp_camada": round(comp, 4),
                    "camadas_cobertas": sum(c["n_camadas"] for c in cortes),
                    "cortes": cortes,
                    "deficit_residual_camadas": n_falta,
                })
                break
    return sugestoes
