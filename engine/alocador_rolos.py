"""
PCP Enfestos -- Alocador de Rolos v3.0 (atribuicao otima por rolo)
==================================================================

MODELO (v3): a alocacao processa os ROLOS um a um (nas duas ordens: do mais longo
para o mais curto e vice-versa, ficando com a ordem que exigir MENOR compra por
cor). Para cada rolo, um problema de mochila limitada ("bounded knapsack", em
milimetros inteiros) decide quantas camadas de cada mapa cortar daquele rolo de
forma a aproveitar o maximo de tecido util -- substitui o greedy antigo
"mapa mais longo primeiro", que deixava tecido encalhado em pontas inuteis.
Regras fisicas inalteradas: camada inteira, sem emenda, margem de faca paga 1x
por (mapa,cor) na fonte primaria, alocacao sempre contra o comp_seguro.
Nunca cruza cor; nunca corta submapa parcial; so dentro do mesmo plano (sem
estoque entre OPs). Ver engine/alocador_rolos.py::_alocar_cor e o spec
docs/superpowers/specs/2026-06-25-alocador-enfesto-por-enfesto-design.md.

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
  REPORTADA de forma FISICA: ponta_m = comprimento nominal - tecido usado.
  (O planejamento continua alocando contra o comp_seguro -- a folga de incerteza
  limita quantas camadas cabem no rolo --, mas a folga NAO e tecido consumido:
  se o nominal do ERP estiver certo, ela volta para o estoque junto com a ponta.)
  NAO E REFUGO -- e um subproduto reaproveitavel:
    - Pontas grandes (>= ponta_minima_util_m): reaproveitadas como CAMADA INTEIRA de
      outro enfesto (mapa mais curto) do mesmo plano; o que sobrar vira estoque.
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
from functools import lru_cache
from itertools import combinations


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


def _resolver_rolo_dp(cap_mm, itens_mm, rem, margem_mm, margem_pendente):
    """
    Mochila limitada ("bounded knapsack") de UM rolo, em milimetros inteiros.

    Decide quantas camadas de cada mapa cortar deste rolo de forma a maximizar
    os metros uteis aproveitados (camadas x comprimento da camada). O custo de
    k camadas de um mapa e k*cc_mm, mais a margem de faca (margem_mm) quando o
    mapa ainda nao pagou margem em nenhum rolo -- nesse caso este rolo vira a
    fonte "primaria" do mapa. Recursao com memoizacao (sem tabela densa).
    Retorna {mapa_id: n_camadas} apenas com escolhas > 0.
    """
    mids = [mid for mid, l in itens_mm if l > 0 and rem.get(mid, 0) > 0]
    lens = dict(itens_mm)

    @lru_cache(maxsize=None)
    def rec(i, cap):
        if i >= len(mids):
            return 0, ()
        mid = mids[i]
        comp = lens[mid]
        melhor, escolha = rec(i + 1, cap)
        max_k = min(rem[mid], cap // comp)
        for k in range(1, max_k + 1):
            custo = k * comp + (margem_mm if mid in margem_pendente else 0)
            if custo > cap:
                break
            sub, sub_esc = rec(i + 1, cap - custo)
            if sub + k * comp > melhor:
                melhor, escolha = sub + k * comp, sub_esc + ((mid, k),)
        return melhor, escolha

    _, escolha = rec(0, max(0, int(cap_mm)))
    rec.cache_clear()
    return dict(escolha)


def _alocar_cor_ordem(demanda, comp_camada_por_id, rolos_cor, config, crescente):
    """
    Aloca UMA cor processando os rolos numa ordem fixa (decrescente ou
    crescente de comprimento seguro), resolvendo uma mochila limitada por rolo.
    Devolve o resultado no contrato de _alocar_cor (sem o bloco resumo_compra,
    que e adicionado pelo chamador). Funcao pura.
    """
    margem    = float(config.get("margem_seguranca_enfesto_m", 0.10))
    ponta_min = float(config.get("ponta_minima_util_m", 0.5))
    # margem em mm arredondada para CIMA: nunca subestima o consumo real.
    margem_mm = int(math.ceil(margem * 1000 - 1e-6))
    _EPS = 1e-9

    # Ordem canonica dos enfestos na saida: cc desc; empate -> maior demanda.
    ordem = sorted(demanda.keys(),
                   key=lambda m: (-comp_camada_por_id.get(m, 0.0), -demanda[m]))

    rolos = []   # estado por rolo: restante + ultimo mapa servido (p/ flag honesta)
    for i, nom in enumerate(rolos_cor):
        seguro = round(_comp_seguro(nom, config), 6)
        rolos.append({
            "rolo_indice": i + 1, "nominal_m": float(nom), "seguro_m": seguro,
            "restante_m": seguro,
            "cap_mm": int(math.floor(seguro * 1000 + 1e-6)),  # capacidade p/ baixo
            "ultimo_mapa": None, "ultima_cc": 0.0,
        })

    # Camada em mm inteiros, arredondada para CIMA (conservador: mm >= metros).
    cc_mm = {mid: int(math.ceil(float(comp_camada_por_id.get(mid, 0.0)) * 1000 - 1e-6))
             for mid in demanda}
    itens_mm = [(mid, cc_mm[mid]) for mid in ordem]

    rem = {mid: int(demanda[mid]) for mid in demanda}
    margem_pendente = {mid for mid in demanda if cc_mm[mid] > 0 and rem[mid] > 0}
    fontes_por_mapa = {mid: [] for mid in demanda}

    seq = sorted(rolos, key=lambda r: r["seguro_m"], reverse=not crescente)
    for r in seq:
        if all(v <= 0 for v in rem.values()):
            break
        escolha = _resolver_rolo_dp(r["cap_mm"], itens_mm, rem, margem_mm,
                                    frozenset(margem_pendente))
        # Dentro do rolo o corte segue a ordem dos enfestos (mais longo primeiro).
        for mid in ordem:
            k = escolha.get(mid, 0)
            if k <= 0:
                continue
            cc = float(comp_camada_por_id.get(mid, 0.0))
            eh_primaria = mid in margem_pendente
            overhead = margem if eh_primaria else 0.0
            # Flag HONESTA: reaproveitamento real exige que o rolo ja tenha
            # servido um mapa mais longo E que a sobra no momento do uso ja nao
            # servisse a esse mapa anterior (restante < camada do mapa anterior).
            prev_mid, prev_cc = r["ultimo_mapa"], r["ultima_cc"]
            reap = (prev_mid is not None and prev_cc > cc + _EPS
                    and r["restante_m"] < prev_cc - _EPS)
            fontes_por_mapa[mid].append({
                "tipo": "ponta" if reap else "rolo",
                "rolo_indice": r["rolo_indice"],
                "enfesto_origem": prev_mid if reap else None,
                "n_camadas": k, "comp_camada_m": round(cc, 4),
                "comp_usado_m": round(k * cc + overhead, 4),
                "primaria": eh_primaria, "reaproveitada": reap,
            })
            r["restante_m"] = round(r["restante_m"] - (k * cc + overhead), 6)
            r["ultimo_mapa"], r["ultima_cc"] = mid, cc
            if eh_primaria:
                margem_pendente.discard(mid)
            rem[mid] -= k

    enfestos, camadas_alocadas = [], {}
    for mid in ordem:
        cc = float(comp_camada_por_id.get(mid, 0.0))
        K  = int(demanda[mid])
        cobertas = K - rem[mid]
        camadas_alocadas[mid] = cobertas
        enfestos.append({
            "mapa_id": mid, "comp_camada_m": round(cc, 4),
            "camadas_necessarias": K, "camadas_cobertas": cobertas,
            "camadas_em_deficit": K - cobertas, "margem_m": round(margem, 4),
            "tecido_usado_m": round(cobertas * cc + (margem if cobertas > 0 else 0.0), 4),
            "tecido_a_comprar_m": round((K - cobertas) * cc, 4),
            "fontes": fontes_por_mapa[mid],
        })

    # Resumo por rolo: APENAS os rolos efetivamente usados (com camadas), na
    # ordem original. A ponta reportada e FISICA: nominal - usado. A folga de
    # incerteza limita o planejamento (comp_seguro), mas nao e tecido consumido
    # -- nao deve ser descontada da sobra que volta ao estoque.
    usados_idx = {f["rolo_indice"] for fs in fontes_por_mapa.values() for f in fs}
    rolos_out, ponta_est, refugo_real, nom_total = [], 0.0, 0.0, 0.0
    nao_usados_n, nao_usados_m = 0, 0.0
    for r in rolos:
        if r["rolo_indice"] not in usados_idx:
            nao_usados_n += 1
            nao_usados_m += r["nominal_m"]
            continue
        usado = round(r["seguro_m"] - max(0.0, r["restante_m"]), 4)
        ponta = round(max(0.0, r["nominal_m"] - usado), 4)
        classe = "estoque" if ponta >= ponta_min else "refugo"
        rolos_out.append({
            "rolo_indice": r["rolo_indice"], "nominal_m": round(r["nominal_m"], 4),
            "seguro_m": round(r["seguro_m"], 4),
            "usado_m": usado,
            "ponta_m": ponta, "ponta_classe": classe,
        })
        nom_total += r["nominal_m"]
        if classe == "estoque":
            ponta_est += ponta
        else:
            refugo_real += ponta

    camadas_def = {mid: (int(demanda[mid]) - camadas_alocadas[mid])
                   for mid in demanda if int(demanda[mid]) - camadas_alocadas[mid] > 0}
    reap_camadas = sum(f["n_camadas"] for e in enfestos for f in e["fontes"]
                       if f["reaproveitada"])
    reap_tecido  = sum(f["n_camadas"] * f["comp_camada_m"] for e in enfestos
                       for f in e["fontes"] if f["reaproveitada"])
    return {
        "enfestos": enfestos, "rolos": rolos_out,
        "camadas_alocadas": camadas_alocadas, "camadas_em_deficit": camadas_def,
        "tecido_usado_m": round(sum(e["tecido_usado_m"] for e in enfestos), 3),
        "tecido_a_comprar_m": round(sum(e["tecido_a_comprar_m"] for e in enfestos), 3),
        "ponta_estoque_total_m": round(ponta_est, 3),
        "refugo_real_m": round(refugo_real, 3),
        # % sobre o nominal dos rolos USADOS (rolos intactos nao entram).
        "refugo_percentual": round(100 * refugo_real / nom_total, 2) if nom_total > 0 else 0.0,
        "n_rolos_utilizados": len(rolos_out),
        "rolos_nao_utilizados": {"quantidade": nao_usados_n,
                                 "total_nominal_m": round(nao_usados_m, 3)},
        # n_sub_enfestos = 1 por mapa coberto (NAO por pilha fisica) -- margem 1x/enfesto.
        "n_sub_enfestos": sum(1 for e in enfestos if e["camadas_cobertas"] > 0),
        "reaproveitamento": {"camadas_reaproveitadas": reap_camadas,
                             "tecido_economizado_m": round(reap_tecido, 3)},
    }


def _alocar_cor(demanda, comp_camada_por_id, rolos_cor, config, _refinar=True):
    """Aloca o tecido de UMA cor pelo modelo enfesto-por-enfesto com atribuicao
    otima por rolo (mochila limitada em mm inteiros): camada inteira, sem emenda,
    margem 1x por (mapa,cor) na fonte primaria, sempre contra o comp_seguro.
    Processa os rolos nas DUAS ordens (decrescente e crescente de comprimento
    seguro) e fica com a que resultar em MENOR compra; empate -> MENOS rolos
    abertos, depois menor refugo, depois menos fontes. Sem deficit, ainda tenta
    reduzir o numero de rolos abertos (_refinar_menos_rolos). Funcao pura."""
    res = _alocar_cor_ordem(demanda, comp_camada_por_id, rolos_cor, config,
                            crescente=False)
    if len(rolos_cor) > 1:
        alt = _alocar_cor_ordem(demanda, comp_camada_por_id, rolos_cor, config,
                                crescente=True)

        def _chave(r):
            return (r["tecido_a_comprar_m"], r["n_rolos_utilizados"],
                    r["refugo_real_m"],
                    sum(len(e["fontes"]) for e in r["enfestos"]))

        if _chave(alt) < _chave(res):
            res = alt

    # Bloco resumo_compra: visao de compra da cor (necessidade x disponibilidade).
    # fragmentacao_m = quanto da compra existe so porque as pontas dos rolos
    # ficaram curtas demais para receber camadas inteiras.
    necessario = sum(int(demanda[m]) * float(comp_camada_por_id.get(m, 0.0))
                     for m in demanda)
    disp_nom = sum(float(n) for n in rolos_cor)
    disp_seg = sum(_comp_seguro(n, config) for n in rolos_cor)
    falta  = max(0.0, necessario - disp_seg)
    compra = res["tecido_a_comprar_m"]
    res["resumo_compra"] = {
        "necessario_m": round(necessario, 3),
        "disponivel_nominal_m": round(disp_nom, 3),
        "disponivel_seguro_m": round(disp_seg, 3),
        "falta_liquida_m": round(falta, 3),
        "compra_recomendada_m": round(compra, 3),
        "fragmentacao_m": round(max(0.0, compra - falta), 3),
    }

    # Refinamento: sem deficit, tenta atender a mesma demanda abrindo MENOS
    # rolos. So no nivel de cima (_refinar=False nas chamadas internas evita
    # recursao subconjunto -> refinamento -> subconjunto).
    if _refinar and not res["camadas_em_deficit"] and res["n_rolos_utilizados"] > 1:
        res = _refinar_menos_rolos(demanda, comp_camada_por_id, rolos_cor,
                                   config, res)
    return res


def _refinar_menos_rolos(demanda, comp_camada_por_id, rolos_cor, config, res):
    """
    Tenta cobrir a demanda (sem deficit) com MENOS rolos do que `res`, testando
    os k MAIORES rolos (por comprimento seguro) para k crescente a partir do
    piso de capacidade. Dominancia: se algum subconjunto de k rolos cobre a
    demanda, os k maiores tambem cobrem (todo empacotamento continua valido
    trocando cada rolo por um maior ou igual). O empacotador por rolo continua
    sendo o greedy das duas ordens -- se ele nao achar cobertura com k rolos,
    fica o resultado original (nunca piora). Devolve `res` intacto se nenhum
    k menor cobrir.
    """
    # Piso de consumo para cobertura total: camadas + margem de faca (paga
    # exatamente 1x por mapa demandado) -- deixa o kmin justo, sem testar um
    # k que nunca caberia.
    margem = float(config.get("margem_seguranca_enfesto_m", 0.10))
    necessario = sum(int(demanda[m]) * float(comp_camada_por_id.get(m, 0.0))
                     for m in demanda)
    necessario += margem * sum(
        1 for m in demanda
        if int(demanda[m]) > 0 and float(comp_camada_por_id.get(m, 0.0)) > 0)
    ordem_idx = sorted(range(len(rolos_cor)),
                       key=lambda i: (-_comp_seguro(rolos_cor[i], config), i))
    metas = [{"comprimento_m": float(n), "rolo_id": None, "lote": None,
              "largura_m": None, "cor_fornecedor": None} for n in rolos_cor]
    acum, kmin = 0.0, None
    for j, i in enumerate(ordem_idx, 1):
        acum += _comp_seguro(rolos_cor[i], config)
        if acum >= necessario - 1e-9:
            kmin = j
            break
    if kmin is None:
        return res
    for k in range(kmin, res["n_rolos_utilizados"]):
        r2 = _alocar_cor_subconjunto(demanda, comp_camada_por_id, metas,
                                     sorted(ordem_idx[:k]), config,
                                     _refinar=False)
        if not r2["camadas_em_deficit"]:
            return r2
    return res


def _normalizar_rolos(lista):
    """
    Normaliza a lista de rolos de UMA cor para o formato interno com metadados.

    Aceita dois formatos por rolo (retrocompatibilidade):
      - numero puro (float/int/str): so o comprimento nominal (entrada manual);
      - dict: {"comprimento_m": float, "rolo_id": str|None, "lote": str|None,
               "largura_m": float|None, "cor_fornecedor": str|None} (import ERP).

    Rolos com comprimento invalido ou <= 0 sao descartados (comportamento
    identico ao filtro numerico anterior).
    """
    metas = []
    for r in lista or []:
        if isinstance(r, dict):
            try:
                comp = float(r.get("comprimento_m", 0) or 0)
            except (TypeError, ValueError):
                comp = 0.0
            # not(comp > 0) tambem descarta NaN (NaN <= 0 e False, mas NaN > 0
            # tambem) e infinito -- mesmo comportamento do filtro antigo.
            if not (comp > 0) or math.isinf(comp):
                continue
            rid  = r.get("rolo_id")
            lote = r.get("lote")
            try:
                larg = float(r.get("largura_m") or 0) or None
            except (TypeError, ValueError):
                larg = None
            metas.append({
                "comprimento_m" : comp,
                "rolo_id"       : str(rid).strip() if rid not in (None, "") else None,
                "lote"          : str(lote).strip() if lote not in (None, "", "0") else None,
                "largura_m"     : larg,
                "cor_fornecedor": r.get("cor_fornecedor") or None,
            })
        else:
            try:
                comp = float(r)
            except (TypeError, ValueError):
                comp = 0.0
            if not (comp > 0) or math.isinf(comp):
                continue
            metas.append({"comprimento_m": comp, "rolo_id": None, "lote": None,
                          "largura_m": None, "cor_fornecedor": None})
    return metas


def _anexar_metadados(cr, metas):
    """
    Anexa os metadados (rolo_id, lote, largura, cor do fornecedor) ao resultado
    de _alocar_cor. O rolo_indice (1-based) referencia a posicao em `metas`.
    """
    por_indice = {i + 1: m for i, m in enumerate(metas)}
    for r in cr.get("rolos", []):
        m = por_indice.get(r.get("rolo_indice"))
        if m:
            r["rolo_id"]        = m["rolo_id"]
            r["lote"]           = m["lote"]
            r["largura_m"]      = m["largura_m"]
            r["cor_fornecedor"] = m["cor_fornecedor"]
    for e in cr.get("enfestos", []):
        for f in e.get("fontes", []):
            m = por_indice.get(f.get("rolo_indice"))
            if m:
                f["rolo_id"]   = m["rolo_id"]
                f["lote"]      = m["lote"]
                f["largura_m"] = m["largura_m"]
    return cr


def _alocar_cor_subconjunto(demanda, comp_camada_por_id, metas, indices, config,
                            _refinar=True):
    """
    Roda _alocar_cor usando apenas os rolos de `indices` (0-based, ordenados) e
    devolve o resultado com rolo_indice remapeado para a numeracao ORIGINAL da
    lista completa. Rolos fora do subconjunto contam como NAO utilizados (mesma
    visao dos rolos que o DP nao tocou: ficam fora de rolos[] e entram no
    contador rolos_nao_utilizados).
    """
    sub_lens = [metas[i]["comprimento_m"] for i in indices]
    res = _alocar_cor(demanda, comp_camada_por_id, sub_lens, config,
                      _refinar=_refinar)

    mapa = {j + 1: indices[j] + 1 for j in range(len(indices))}
    for e in res["enfestos"]:
        for f in e["fontes"]:
            f["rolo_indice"] = mapa[f["rolo_indice"]]
    for r in res["rolos"]:
        r["rolo_indice"] = mapa[r["rolo_indice"]]

    # Rolos fora do subconjunto = nao utilizados na visao da lista completa.
    dentro = set(indices)
    fora_m = sum(m["comprimento_m"] for i, m in enumerate(metas)
                 if i not in dentro)
    ru = res["rolos_nao_utilizados"]
    ru["quantidade"] += len(metas) - len(indices)
    ru["total_nominal_m"] = round(ru["total_nominal_m"] + fora_m, 3)

    # resumo_compra: disponibilidade deve considerar TODOS os rolos da cor
    disp_nom = sum(m["comprimento_m"] for m in metas)
    disp_seg = sum(_comp_seguro(m["comprimento_m"], config) for m in metas)
    rc = res.get("resumo_compra")
    if rc is not None:
        necessario = rc["necessario_m"]
        falta  = max(0.0, necessario - disp_seg)
        compra = res["tecido_a_comprar_m"]
        rc["disponivel_nominal_m"] = round(disp_nom, 3)
        rc["disponivel_seguro_m"]  = round(disp_seg, 3)
        rc["falta_liquida_m"]      = round(falta, 3)
        rc["fragmentacao_m"]       = round(max(0.0, compra - falta), 3)
    return res


def _uso_por_rolo(cr):
    """Indices (1-based) dos rolos efetivamente usados no resultado de uma cor."""
    usados = set()
    for e in cr.get("enfestos", []):
        for f in e.get("fontes", []):
            usados.add(f["rolo_indice"])
    return usados


def _rank_candidato_lote(cr, metas):
    """
    Chave de ordenacao entre candidatos VIAVEIS (sem deficit) do modo lote:
      1. menos larguras distintas entre rolos usados (juntar largura);
      2. menos rolos abertos;
      3. menor refugo real dos rolos usados;
      4. menor soma de pontas dos rolos usados (menos sobras de pontas);
      5. menos fontes (menos fragmentacao operacional).
    """
    usados = _uso_por_rolo(cr)
    largs  = set()
    refugo = ponta = 0.0
    for r in cr.get("rolos", []):
        if r["rolo_indice"] not in usados:
            continue
        m = metas[r["rolo_indice"] - 1]
        if m["largura_m"]:
            largs.add(round(m["largura_m"], 2))
        if r["ponta_classe"] == "refugo":
            refugo += r["ponta_m"]
        else:
            ponta += r["ponta_m"]
    n_fontes = sum(len(e.get("fontes", [])) for e in cr.get("enfestos", []))
    return (len(largs), len(usados), round(refugo, 3), round(ponta, 3), n_fontes)


_MAX_COMBOS_LOTE = 400   # teto de subconjuntos avaliados por nivel k


def _alocar_cor_com_lotes(demanda, comp_camada_por_id, metas, config):
    """
    Modo "Considerar Lote": tenta atender a cor com o MENOR numero possivel de
    lotes distintos (1 lote se possivel; senao 2; e assim por diante).

    Estrategia: enumera combinacoes de lotes por tamanho crescente k e fica com
    o primeiro nivel k que tiver candidato viavel (sem deficit), desempatando
    por _rank_candidato_lote. Se a combinatoria estourar o teto, cai num greedy
    (lotes maiores primeiro). Se nem todos os rolos juntos atendem (deficit
    inevitavel), devolve None e o chamador usa todos os rolos.

    Returns:
        (resultado, lotes_usados) | (None, None)
    """
    lotes = {}
    for i, m in enumerate(metas):
        lotes.setdefault(m["lote"] or "S/LOTE", []).append(i)
    chaves = sorted(lotes.keys())
    n = len(chaves)
    if n <= 1:
        return None, None   # 0/1 lote: nada a otimizar

    necessario = sum(int(demanda[mid]) * float(comp_camada_por_id.get(mid, 0.0))
                     for mid in demanda)
    seguro_por_lote = {ch: sum(_comp_seguro(metas[i]["comprimento_m"], config)
                               for i in lotes[ch]) for ch in chaves}

    def avaliar(combo):
        idxs = sorted(i for ch in combo for i in lotes[ch])
        # Poda: capacidade segura do subconjunto nunca cobre o necessario
        if sum(seguro_por_lote[ch] for ch in combo) < necessario - 1e-9:
            return None
        res = _alocar_cor_subconjunto(demanda, comp_camada_por_id, metas, idxs, config)
        if res["camadas_em_deficit"]:
            return None
        return res

    for k in range(1, n + 1):
        if math.comb(n, k) > _MAX_COMBOS_LOTE:
            # Combinatoria alta: greedy — acumula lotes do maior para o menor.
            ordem = sorted(chaves, key=lambda ch: -seguro_por_lote[ch])
            acumulado = []
            for ch in ordem:
                acumulado.append(ch)
                if len(acumulado) < k:
                    continue
                res = avaliar(tuple(acumulado))
                if res is not None:
                    return res, sorted(acumulado)
            return None, None
        melhores = []
        for combo in combinations(chaves, k):
            res = avaliar(combo)
            if res is not None:
                melhores.append((_rank_candidato_lote(res, metas), combo, res))
        if melhores:
            melhores.sort(key=lambda x: (x[0], x[1]))
            _, combo, res = melhores[0]
            return res, sorted(combo)

    return None, None


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

    Algoritmo: para cada cor delega a alocacao a _alocar_cor (modelo
    enfesto-por-enfesto com atribuicao otima por rolo via mochila limitada,
    camada inteira sem emenda, margem 1x por enfesto, rolos processados na
    ordem -- decrescente ou crescente de comprimento seguro -- que exigir a
    menor compra) e consolida os totais, alertas e sobras no resumo_geral.

    Args:
        plano: {
            "mapas":   [{"id": int, "composicao": {tam: n}, "n_pecas": int}, ...],
            "camadas": {"COR": {mapa_id: n_camadas}, ...},
            "consumo_peca": float   # metros por peca
        }
        rolos:  {"COR": [rolo, ...]} onde cada rolo pode ser:
                  - float: comprimento nominal em metros (entrada manual); ou
                  - dict:  {"comprimento_m": float, "rolo_id": str|None,
                            "lote": str|None, "largura_m": float|None,
                            "cor_fornecedor": str|None} (import do ERP).
        config: dict (lido de config.json). Chave nova: "considerar_lote"
                (bool) -- quando True, tenta atender cada cor com o MENOR
                numero de lotes distintos (1 se possivel); se houver deficit
                mesmo com todos os rolos, a restricao e ignorada para a cor.

    Returns:
        {
            "por_cor": {
                "COR": {   # formato produzido por _alocar_cor
                    "enfestos": [{"mapa_id","comp_camada_m","camadas_necessarias",
                                  "camadas_cobertas","camadas_em_deficit","margem_m",
                                  "tecido_usado_m","tecido_a_comprar_m",
                                  "fontes": [{"tipo","rolo_indice","enfesto_origem",
                                              "n_camadas","comp_camada_m","comp_usado_m",
                                              "primaria","reaproveitada"}]}],
                    "rolos": [{"rolo_indice","nominal_m","seguro_m","usado_m",
                               "ponta_m","ponta_classe"}],
                               # APENAS rolos usados; ponta_m = nominal - usado
                    "n_rolos_utilizados":  int,
                    "rolos_nao_utilizados": {"quantidade": int,
                                             "total_nominal_m": float},
                    "camadas_alocadas":    {mapa_id: n},
                    "camadas_em_deficit":  {mapa_id: n},
                    "tecido_usado_m":      float,
                    "tecido_a_comprar_m":  float,
                    "ponta_estoque_total_m": float,
                    "refugo_real_m":       float,
                    "refugo_percentual":   float,   # % sobre o nominal dos rolos USADOS
                    "n_sub_enfestos":      int,
                    "reaproveitamento": {"camadas_reaproveitadas": int,
                                         "tecido_economizado_m": float},
                    "resumo_compra": {"necessario_m", "disponivel_nominal_m",
                                      "disponivel_seguro_m", "falta_liquida_m",
                                      "compra_recomendada_m", "fragmentacao_m"},
                }
            },
            "resumo_geral": {
                "tecido_usado_total_m", "ponta_estoque_total_m",
                "refugo_real_total_m", "refugo_percentual_medio",
                "rolos_utilizados_total",
                "rolos_nao_utilizados_total",  # {"quantidade","total_nominal_m"}
                "n_sub_enfestos_total", "cores_com_deficit",
                "camadas_reaproveitadas_total", "tecido_economizado_total_m",
                "sobras_consolidado",      # por cor: {ponta_estoque_m, refugo_m,
                                           #   n_pontas_estoque}
                "resumo_compra_total",     # mesmos campos de resumo_compra, somados
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
    considerar_lote = bool(config.get("considerar_lote", False))
    # Rolos de cores que nao estao no plano: nao entram na alocacao, mas
    # continuam inteiros em estoque -- precisam aparecer na conciliacao.
    fora_plano_n, fora_plano_m = 0, 0.0

    for cor in todas_cores:
        demanda   = {int(k): int(v) for k, v in camadas_plano.get(cor, {}).items() if int(v) > 0}
        metas     = _normalizar_rolos(rolos.get(cor))
        rolos_cor = [m["comprimento_m"] for m in metas]

        # Cor sem demanda real -> nada a alocar; os rolos informados contam
        # como nao utilizados (nunca descartar dados em silencio).
        if not demanda:
            if metas:
                tot = sum(m["comprimento_m"] for m in metas)
                fora_plano_n += len(metas)
                fora_plano_m += tot
                alertas.append(
                    f"{cor}: {len(metas)} rolo(s) informado(s) ({round(tot, 1)}m), "
                    f"mas o plano nao tem camadas dessa cor; "
                    f"permanecem inteiros em estoque."
                )
            continue

        # Ramo: cor sem rolos -> deficit total (mantem alertas existentes).
        if not rolos_cor:
            alertas.append(f"{cor}: nenhum rolo disponivel; toda a demanda vira compra.")
            cr = _alocar_cor(demanda, comp_camada_por_id, [], config)
        else:
            # Verificacao critica: camada que nao cabe em nenhum rolo.
            maior_seguro = max(_comp_seguro(r, config) for r in rolos_cor)
            for mid, cc in comp_camada_por_id.items():
                if mid in demanda and cc > maior_seguro + 0.001:
                    alertas.append(
                        f"{cor}: CRITICO -- camada do mapa {mid} ({cc:.2f}m) nao cabe "
                        f"em nenhum rolo (maior seguro {maior_seguro:.2f}m)."
                    )
            cr = _alocar_cor(demanda, comp_camada_por_id, rolos_cor, config)

            # Modo "Considerar Lote": tenta atender com o menor numero de lotes.
            if considerar_lote:
                if cr["camadas_em_deficit"]:
                    alertas.append(
                        f"{cor}: ha deficit mesmo usando todos os rolos; "
                        f"a restricao de lote foi ignorada para esta cor."
                    )
                else:
                    res_lote, _combo = _alocar_cor_com_lotes(
                        demanda, comp_camada_por_id, metas, config)
                    if res_lote is not None:
                        cr = res_lote

        # Metadados (nº do rolo, lote, largura, cor do fornecedor) no resultado.
        _anexar_metadados(cr, metas)

        # Info de lotes e larguras efetivamente usados (honesta: le do resultado).
        usados_idx = _uso_por_rolo(cr)
        lotes_usados = sorted({(metas[i - 1]["lote"] or "S/LOTE") for i in usados_idx}) \
                       if metas else []
        lotes_disp   = sorted({(m["lote"] or "S/LOTE") for m in metas}) if metas else []
        cr["lotes"] = {
            "considerado": considerar_lote,
            "disponiveis": len(lotes_disp),
            "utilizados" : lotes_usados,
        }
        if considerar_lote and len(lotes_usados) > 1:
            alertas.append(
                f"{cor}: nao foi possivel atender com um unico lote; "
                f"usados {len(lotes_usados)} lotes ({', '.join(lotes_usados)})."
            )

        largs_usadas = sorted({round(metas[i - 1]["largura_m"], 2)
                               for i in usados_idx if metas[i - 1]["largura_m"]})
        cr["larguras_utilizadas"] = largs_usadas
        if len(largs_usadas) > 1:
            alertas.append(
                f"{cor}: rolos usados tem larguras diferentes "
                f"({', '.join(str(x) for x in largs_usadas)}m). "
                f"Confira se o encaixe cabe na menor largura."
            )
        for e in cr["enfestos"]:
            ls = sorted({round(metas[f["rolo_indice"] - 1]["largura_m"], 2)
                         for f in e["fontes"]
                         if metas[f["rolo_indice"] - 1]["largura_m"]})
            if len(ls) > 1:
                alertas.append(
                    f"{cor}: mapa {e['mapa_id']} mistura larguras "
                    f"{', '.join(str(x) for x in ls)}m no mesmo encaixe."
                )

        # Alerta de compra por cor (antes dos alertas por mapa).
        if cr["camadas_em_deficit"]:
            rc = cr["resumo_compra"]
            alertas.append(
                f"{cor}: necessario {rc['necessario_m']:.1f}m, disponivel util "
                f"{rc['disponivel_seguro_m']:.1f}m -> falta {rc['falta_liquida_m']:.1f}m; "
                f"compra recomendada {rc['compra_recomendada_m']:.1f}m "
                f"(inclui {rc['fragmentacao_m']:.1f}m por fragmentacao de pontas)."
            )
        for mid, n in cr["camadas_em_deficit"].items():
            cc = comp_camada_por_id.get(mid, 0.0)
            alertas.append(f"{cor}: deficit de {n} camada(s) do mapa {mid} -- "
                           f"comprar aprox. {round(n * cc, 2)}m.")
        if cr["camadas_em_deficit"]:
            acc["cores_com_deficit"].append(cor)

        resultado_por_cor[cor] = cr
        acc["tecido_usado_total_m"]   += cr["tecido_usado_m"]
        acc["ponta_estoque_total_m"]  += cr["ponta_estoque_total_m"]
        acc["refugo_real_total_m"]    += cr["refugo_real_m"]
        acc["n_sub_enfestos_total"]   += cr["n_sub_enfestos"]

    # Totalizadores globais (nominal apenas dos rolos USADOS -- rolos[] ja vem
    # filtrado por cor; rolos intactos entram em rolos_nao_utilizados_total).
    nom_total_geral = sum(r["nominal_m"]
                          for res in resultado_por_cor.values() for r in res["rolos"])
    refugo_medio = (round(100 * acc["refugo_real_total_m"] / nom_total_geral, 2)
                    if nom_total_geral > 0 else 0.0)
    campos_compra = ("necessario_m", "disponivel_nominal_m", "disponivel_seguro_m",
                     "falta_liquida_m", "compra_recomendada_m", "fragmentacao_m")
    resumo_geral = {
        "tecido_usado_total_m"     : round(acc["tecido_usado_total_m"], 3),
        "ponta_estoque_total_m"    : round(acc["ponta_estoque_total_m"], 3),
        "refugo_real_total_m"      : round(acc["refugo_real_total_m"], 3),
        "refugo_percentual_medio"  : refugo_medio,
        "rolos_utilizados_total"   : sum(res["n_rolos_utilizados"]
                                         for res in resultado_por_cor.values()),
        "rolos_nao_utilizados_total": {
            "quantidade": fora_plano_n + sum(
                res["rolos_nao_utilizados"]["quantidade"]
                for res in resultado_por_cor.values()),
            "total_nominal_m": round(fora_plano_m + sum(
                res["rolos_nao_utilizados"]["total_nominal_m"]
                for res in resultado_por_cor.values()), 3),
        },
        "n_sub_enfestos_total"     : acc["n_sub_enfestos_total"],
        "cores_com_deficit"        : sorted(set(acc["cores_com_deficit"])),
        "camadas_reaproveitadas_total": sum(
            res["reaproveitamento"]["camadas_reaproveitadas"]
            for res in resultado_por_cor.values()),
        "tecido_economizado_total_m": round(sum(
            res["reaproveitamento"]["tecido_economizado_m"]
            for res in resultado_por_cor.values()), 3),
        "sobras_consolidado": {
            c: {
                "ponta_estoque_m": res["ponta_estoque_total_m"],
                "refugo_m": res["refugo_real_m"],
                "n_pontas_estoque": sum(1 for r in res["rolos"]
                                        if r["ponta_classe"] == "estoque" and r["ponta_m"] > 0),
            } for c, res in resultado_por_cor.items()
        },
        "resumo_compra_total": {
            campo: round(sum(res["resumo_compra"][campo]
                             for res in resultado_por_cor.values()), 3)
            for campo in campos_compra
        },
        "alertas": alertas,
    }

    params = {
        "margem_seguranca_enfesto_m": round(float(margem), 4),
        "folga_incerteza_pct": float(config.get("folga_incerteza_pct", 0.03)),
        "folga_incerteza_m": float(config.get("folga_incerteza_m", 0.0)),
        "ponta_minima_util_m": float(ponta_min),
        "considerar_lote": considerar_lote,
    }
    return {"por_cor": resultado_por_cor, "resumo_geral": resumo_geral, "params": params}
