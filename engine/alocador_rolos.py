"""
PCP Enfestos -- Alocador de Rolos v1.0
=======================================

GLOSSARIO (para leitura por nao-tecnicos)
------------------------------------------

CAMADA:
  Uma passagem de tecido estendido sobre a mesa de corte. O comprimento de uma camada
  e fixo para cada mapa e calculado como:
    comp_camada = n_pecas_no_mapa x consumo_peca_m
  Exemplo: mapa com 4 pecas, consumo 1.0645m por peca -> camada de 4.258m.

SUB-ENFESTO:
  Um grupo de camadas IDENTICAS (mesmo mapa) empilhadas sobre a mesa. Ao final de cada
  sub-enfesto ha uma folga de faca nas duas extremidades (cabeca e cauda da pilha).
  Essa folga e cobrada UMA VEZ por sub-enfesto, independente de quantas camadas tem.
  Formula: comp_sub_enfesto = (n_camadas x comp_camada) + margem_seguranca_enfesto_m
  Importante: trocar de mapa = comecar um novo sub-enfesto = pagar a folga de faca de novo.

PONTA DE ROLO:
  A sobra de tecido no final de um rolo apos esgotar todos os sub-enfestos possiveis.
  Comprimento insuficiente para mais uma camada do mapa atual.
  NAO E REFUGO -- e um subproduto reaproveitavel:
    - Pontas grandes (>= ponta_minima_util_m): vao para estoque ou viram mini-enfestos.
    - Pontas pequenas (< ponta_minima_util_m): refugo real (irrecuperavel).

EMENDA:
  Quando uma camada comeca em um rolo e continua em outro. COMPLETAMENTE PROIBIDA.
  Uma emenda no meio do enfesto inutiliza a camada e gera refugo irrecuperavel.
  O sistema previne emendas alocando sempre contra o COMP_SEGURO, nunca o nominal.

COMP_SEGURO:
  O comprimento conservador que o sistema usa para planejamento:
    comp_seguro = comp_nominal x (1 - folga_incerteza_pct)
  Motivo: o comprimento informado pelo ERP pode nao bater com o rolo fisico. Se alocarmos
  ate o limite nominal e o rolo real for mais curto, criamos exatamente a emenda que
  queremos evitar. A folga de incerteza (default 3%) cobre essa imprecisao.

HIERARQUIA DE PERDA (do mais grave ao menos importante):
  1. EMENDA            -- proibicao dura; resolvida pelo comp_seguro (nunca ocorre).
  2. DEFICIT           -- rolos insuficientes; precisa comprar mais tecido.
  3. FRAGMENTACAO      -- muitos sub-enfestos = custo operacional + margem de faca extra.
  4. REFUGO REAL       -- ponta menor que ponta_minima_util_m (irrecuperavel).
  5. PONTA REAPROVEITAVEL -- ponta >= ponta_minima_util_m (vai para estoque; nao e perda).

PREMISSAS FIXAS (documentadas para quem for manter):
  - Largura de rolo e uniforme para todas as cores: restricao e apenas de COMPRIMENTO.
  - Cada sub-enfesto usa um unico mapa (mesma composicao para todas as camadas).
  - Uma camada nunca pode cruzar a fronteira entre dois rolos.
"""

import math

from engine.reaproveitamento import sugerir_corte_separado


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def _comp_seguro(nominal, config):
    """
    Calcula o comprimento seguro de um rolo (aplica folga de incerteza).
    Se folga_incerteza_m > 0, usa subtrato fixo; caso contrario, usa percentual.
    """
    folga_m = float(config.get("folga_incerteza_m", 0.0))
    if folga_m > 0:
        return max(0.0, float(nominal) - folga_m)
    folga_pct = float(config.get("folga_incerteza_pct", 0.03))
    return max(0.0, float(nominal) * (1.0 - folga_pct))


def _validar_entradas(plano, config):
    """Valida parametros obrigatorios. Lanca ValueError com mensagem clara."""
    consumo = float(plano.get("consumo_peca", 0))
    if consumo <= 0:
        raise ValueError(
            "consumo_peca deve ser maior que zero. "
            "Verifique o campo 'consumo por peca (m)' no plano."
        )
    margem = float(config.get("margem_seguranca_enfesto_m", 0.10))
    if margem < 0:
        raise ValueError(
            "margem_seguranca_enfesto_m nao pode ser negativa. "
            "Verifique o config.json."
        )
    return consumo, margem


# ---------------------------------------------------------------------------
# Funcao principal
# ---------------------------------------------------------------------------

def alocar_rolos(plano, rolos, config):
    """
    Aloca rolos de tecido para cobrir a demanda de camadas do plano de corte.

    Algoritmo: FFD adaptado (First Fit Decreasing) com fechamento de ponta e
    margem por sub-enfesto. Para cada cor, tenta preencher cada rolo (do maior
    para o menor) com tantos sub-enfestos quantos couberem, escolhendo sempre o
    mapa que maximiza o numero de camadas alocadas no espaco disponivel.

    Args:
        plano: {
            "mapas":   [{"id": int, "composicao": {tam: n}, "n_pecas": int}, ...],
            "camadas": {"COR": {mapa_id: n_camadas}, ...},
            "consumo_peca": float   # metros por peca
        }
        rolos:  {"COR": [comprimento_nominal_m, ...]}   # um valor por rolo
        config: dict (lido de config.json; ver parametros novos no final)

    Returns:
        {
            "por_cor": {
                "COR": {
                    "rolos": [{"indice", "comprimento_nominal_m", "comprimento_seguro_m",
                               "sub_enfestos": [{"mapa_id","n_camadas","comp_camada",
                                                 "margem_m","comp_total"}],
                               "usado_m", "ponta_m", "ponta_classe"}, ...],
                    "camadas_alocadas":    {mapa_id: n},
                    "camadas_em_deficit":  {mapa_id: n},
                    "tecido_usado_m":      float,
                    "ponta_estoque_total_m": float,
                    "refugo_real_m":       float,
                    "refugo_percentual":   float,   # % sobre comprimento nominal total
                    "tecido_a_comprar_m":  float,
                    "n_sub_enfestos":      int,
                    "sugestoes_corte_separado": [ ... ],  # cortes avulsos sugeridos a
                                                          #   partir das pontas
                    "sobras_por_rolo":     [{"rolo_indice", "ponta_m", "ponta_classe",
                                             "reaproveitada_em"}, ...],  # sobras por rolo
                }
            },
            "resumo_geral": {
                "tecido_usado_total_m", "ponta_estoque_total_m",
                "refugo_real_total_m", "refugo_percentual_medio",
                "n_sub_enfestos_total", "cores_com_deficit",
                "sugestoes_corte_total",   # contador de cortes separados sugeridos
                "sobras_consolidado",      # por cor: {ponta_estoque_m, refugo_m,
                                           #   n_pontas_estoque}
                "alertas"
            }
        }
    """
    consumo_peca, margem = _validar_entradas(plano, config)
    ponta_min   = float(config.get("ponta_minima_util_m", 0.5))
    mapas_plano = plano.get("mapas", [])
    camadas_plano = plano.get("camadas", {})

    # Comprimento de camada por mapa_id
    comp_camada_por_id = {}
    for m in mapas_plano:
        mid    = int(m["id"])
        # Comprimento explicito da camada (m) tem prioridade -- necessario para enfesto
        # combinado multi-ref, onde a camada = soma de pecas x consumo de cada referencia
        # (consumos diferentes). Sem ele, usa n_pecas x consumo_peca (caso single-ref).
        comp_m = float(m.get("comp_camada_m", 0) or 0)
        if comp_m > 0:
            comp_camada_por_id[mid] = round(comp_m, 6)
        else:
            n_pecs = int(m.get("n_pecas", sum(m.get("composicao", {}).values())))
            comp_camada_por_id[mid] = round(n_pecs * consumo_peca, 6)

    composicao_por_id = {}
    cpp_por_id = {}
    for m in mapas_plano:
        mid_ = int(m["id"])
        composicao_por_id[mid_] = dict(m.get("composicao", {}))
        n_pecs = int(m.get("n_pecas", sum(m.get("composicao", {}).values()))) or 1
        cpp_por_id[mid_] = round(comp_camada_por_id.get(mid_, 0.0) / n_pecs, 6)

    resultado_por_cor = {}
    alertas           = []
    acc = {
        "tecido_usado_total_m"  : 0.0,
        "ponta_estoque_total_m" : 0.0,
        "refugo_real_total_m"   : 0.0,
        "n_sub_enfestos_total"  : 0,
        "cores_com_deficit"     : [],
    }

    todas_cores = sorted(set(list(camadas_plano.keys()) + list(rolos.keys())))

    for cor in todas_cores:
        demanda   = {int(k): int(v) for k, v in camadas_plano.get(cor, {}).items() if int(v) > 0}
        rolos_cor = [float(r) for r in rolos.get(cor, []) if float(r) > 0]

        # Cor sem demanda real -> ignora
        if not demanda:
            continue

        # Sem rolos disponíveis -> deficit total
        if not rolos_cor:
            alertas.append(
                f"{cor}: nenhum rolo disponivel. Toda a demanda em deficit."
            )
            tecido_def = sum(
                demanda.get(mid, 0) * comp_camada_por_id.get(mid, 0.0)
                for mid in demanda
            )
            resultado_por_cor[cor] = {
                "rolos"                 : [],
                "camadas_alocadas"      : {mid: 0 for mid in demanda},
                "camadas_em_deficit"    : dict(demanda),
                "tecido_usado_m"        : 0.0,
                "ponta_estoque_total_m" : 0.0,
                "refugo_real_m"         : 0.0,
                "refugo_percentual"     : 0.0,
                "tecido_a_comprar_m"    : round(tecido_def, 3),
                "n_sub_enfestos"        : 0,
                "sugestoes_corte_separado" : [],
                "sobras_por_rolo"       : [],
            }
            acc["cores_com_deficit"].append(cor)
            continue

        # Verificacao critica: camada maior que o maior rolo
        maior_seguro = max(_comp_seguro(r, config) for r in rolos_cor)
        for mid, cc in comp_camada_por_id.items():
            if mid in demanda and cc > maior_seguro + 0.001:
                alertas.append(
                    f"CRITICO -- {cor}: camada do mapa {mid} ({cc:.4f}m) nao cabe em nenhum "
                    f"rolo disponivel (maior comp_seguro: {maior_seguro:.2f}m). "
                    f"Reduza pecas/mapa ou utilize um rolo maior."
                )

        # Estado mutavel durante a alocacao
        pendentes = dict(demanda)  # {mapa_id: n_pendentes}

        # Ordena rolos DESC por comp_seguro (maiores primeiro - FFD)
        rolos_ordenados = sorted(
            [(nom, _comp_seguro(nom, config)) for nom in rolos_cor],
            key=lambda x: -x[1]
        )

        rolos_resultado  = []
        camadas_alocadas = {mid: 0 for mid in demanda}

        for idx_rolo, (nominal, seguro) in enumerate(rolos_ordenados):
            pct_desc = round((1.0 - seguro / nominal) * 100, 1) if nominal > 0 else 0.0
            alertas.append(
                f"{cor}: rolo {idx_rolo + 1} informado {nominal}m; "
                f"alocado contra {seguro:.2f}m (folga de incerteza {pct_desc}%)."
            )

            if seguro <= 0:
                rolos_resultado.append({
                    "indice"               : idx_rolo,
                    "comprimento_nominal_m": nominal,
                    "comprimento_seguro_m" : 0.0,
                    "sub_enfestos"         : [],
                    "usado_m"              : 0.0,
                    "ponta_m"              : 0.0,
                    "ponta_classe"         : "refugo",
                })
                continue

            restante          = seguro
            sub_enfestos_rolo = []

            # Empilha sub-enfestos enquanto houver pendentes e espaco no rolo
            while pendentes and restante >= margem:
                # Tenta abrir novo sub-enfesto (paga margem)
                restante -= margem

                # Escolhe o mapa que maximiza camadas no espaco disponivel
                melhor_mid  = None
                melhor_n    = 0
                melhor_comp = 0.0

                for mid, n_pend in pendentes.items():
                    cc = comp_camada_por_id.get(mid, 0.0)
                    if cc <= 0 or cc > restante + 0.0001:
                        continue
                    n_fit = min(n_pend, int(math.floor(restante / cc + 0.0001)))
                    if n_fit <= 0:
                        continue
                    # Criterio: mais camadas > maior comp_camada (tira duvida em empate)
                    if n_fit > melhor_n or (n_fit == melhor_n and cc > melhor_comp):
                        melhor_n    = n_fit
                        melhor_mid  = mid
                        melhor_comp = cc

                if melhor_mid is None or melhor_n == 0:
                    # Nada cabe no espaco restante; devolve a margem paga
                    restante += margem
                    break

                # Registra o sub-enfesto
                usado_sub      = melhor_n * melhor_comp
                comp_total_sub = round(usado_sub + margem, 4)
                sub_enfestos_rolo.append({
                    "mapa_id"    : melhor_mid,
                    "n_camadas"  : melhor_n,
                    "comp_camada": round(melhor_comp, 4),
                    "margem_m"   : round(margem, 4),
                    "comp_total" : comp_total_sub,
                })
                restante -= usado_sub
                camadas_alocadas[melhor_mid] = (
                    camadas_alocadas.get(melhor_mid, 0) + melhor_n
                )
                pendentes[melhor_mid] -= melhor_n
                if pendentes[melhor_mid] <= 0:
                    del pendentes[melhor_mid]

            # Classifica a ponta
            ponta_m      = round(max(0.0, restante), 4)
            ponta_classe = "estoque" if ponta_m >= ponta_min else "refugo"
            usado_rolo   = round(seguro - ponta_m, 4)

            rolos_resultado.append({
                "indice"               : idx_rolo,
                "comprimento_nominal_m": nominal,
                "comprimento_seguro_m" : round(seguro, 4),
                "sub_enfestos"         : sub_enfestos_rolo,
                "usado_m"              : usado_rolo,
                "ponta_m"              : ponta_m,
                "ponta_classe"         : ponta_classe,
            })

        # Deficit: camadas nao alocadas apos esgotar todos os rolos
        deficit = {mid: n for mid, n in pendentes.items() if n > 0}
        for mid, n in deficit.items():
            comp = comp_camada_por_id.get(mid, 0.0)
            alertas.append(
                f"{cor}: deficit de {n} camada(s) do mapa {mid} -- "
                f"comprar aprox. {round(n * comp, 2)}m."
            )
        if deficit:
            acc["cores_com_deficit"].append(cor)

        tecido_usado  = round(sum(r["usado_m"] for r in rolos_resultado), 3)
        ponta_est     = round(sum(
            r["ponta_m"] for r in rolos_resultado if r["ponta_classe"] == "estoque"
        ), 3)
        refugo_real   = round(sum(
            r["ponta_m"] for r in rolos_resultado if r["ponta_classe"] == "refugo"
        ), 3)
        n_sub         = sum(len(r["sub_enfestos"]) for r in rolos_resultado)
        nom_total_cor = sum(r["comprimento_nominal_m"] for r in rolos_resultado)
        refugo_pct    = round(100 * refugo_real / nom_total_cor, 2) if nom_total_cor > 0 else 0.0
        tecido_comprar = round(sum(
            deficit.get(mid, 0) * comp_camada_por_id.get(mid, 0.0)
            for mid in deficit
        ), 3)

        pontas_estoque = [
            {"rolo_origem_indice": r["indice"], "ponta_m": r["ponta_m"]}
            for r in rolos_resultado if r["ponta_classe"] == "estoque" and r["ponta_m"] > 0
        ]
        sobras_por_rolo = [
            {
                "rolo_indice"  : r["indice"] + 1,
                "nominal_m"    : r["comprimento_nominal_m"],
                "seguro_m"     : r["comprimento_seguro_m"],
                "usado_m"      : r["usado_m"],
                "ponta_m"      : r["ponta_m"],
                "ponta_classe" : r["ponta_classe"],
                "reaproveitada_em": None,
            }
            for r in rolos_resultado
        ]
        sugestoes_cs = sugerir_corte_separado(
            deficit, comp_camada_por_id, composicao_por_id, cpp_por_id,
            pontas_estoque, margem
        ) if deficit else []

        resultado_por_cor[cor] = {
            "rolos"                 : rolos_resultado,
            "camadas_alocadas"      : camadas_alocadas,
            "camadas_em_deficit"    : deficit,
            "tecido_usado_m"        : tecido_usado,
            "ponta_estoque_total_m" : ponta_est,
            "refugo_real_m"         : refugo_real,
            "refugo_percentual"     : refugo_pct,
            "tecido_a_comprar_m"    : tecido_comprar,
            "n_sub_enfestos"        : n_sub,
            "sugestoes_corte_separado" : sugestoes_cs,
            "sobras_por_rolo"       : sobras_por_rolo,
        }

        acc["tecido_usado_total_m"]  += tecido_usado
        acc["ponta_estoque_total_m"] += ponta_est
        acc["refugo_real_total_m"]   += refugo_real
        acc["n_sub_enfestos_total"]  += n_sub

    # Totalizadores globais
    nom_total_geral = sum(
        r["comprimento_nominal_m"]
        for res in resultado_por_cor.values()
        for r in res["rolos"]
    )
    refugo_medio = round(
        100 * acc["refugo_real_total_m"] / nom_total_geral, 2
    ) if nom_total_geral > 0 else 0.0

    resumo_geral = {
        "tecido_usado_total_m"    : round(acc["tecido_usado_total_m"], 3),
        "ponta_estoque_total_m"   : round(acc["ponta_estoque_total_m"], 3),
        "refugo_real_total_m"     : round(acc["refugo_real_total_m"], 3),
        "refugo_percentual_medio" : refugo_medio,
        "n_sub_enfestos_total"    : acc["n_sub_enfestos_total"],
        "cores_com_deficit"       : sorted(set(acc["cores_com_deficit"])),
        "sugestoes_corte_total"   : sum(
            len(res.get("sugestoes_corte_separado", []))
            for res in resultado_por_cor.values()
        ),
        "sobras_consolidado"      : {
            c: {
                "ponta_estoque_m"  : res["ponta_estoque_total_m"],
                "refugo_m"         : res["refugo_real_m"],
                "n_pontas_estoque" : sum(
                    1 for s in res.get("sobras_por_rolo", [])
                    if s["ponta_classe"] == "estoque" and s["ponta_m"] > 0
                ),
            }
            for c, res in resultado_por_cor.items()
        },
        "alertas"                 : alertas,
    }

    params = {
        "margem_seguranca_enfesto_m": round(float(margem), 4),
        "folga_incerteza_pct": float(config.get("folga_incerteza_pct", 0.03)),
        "folga_incerteza_m": float(config.get("folga_incerteza_m", 0.0)),
        "ponta_minima_util_m": float(ponta_min),
    }
    return {"por_cor": resultado_por_cor, "resumo_geral": resumo_geral, "params": params}
