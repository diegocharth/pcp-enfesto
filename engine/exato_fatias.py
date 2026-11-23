"""
PCP Enfestos -- Motor exato: varredura fatiada entre processos
===============================================================

Coordenacao da varredura quando o calculo roda pelo pool (engine/paralelo.py):
quantas fatias, quanto tempo a prova pode usar, e o laco de RODADAS curtas
(cada tarefa devolve o processo em ate RODADA_S e a fatia retoma de onde parou),
para que um calculo pesado nao segure o pool inteiro.

O trabalho de cada fatia (_fatia_trabalho) fica em engine/solver_exato.py.
"""

import time
from math import comb

TOP_GUARDA = 48             # planos guardados por nivel (os melhores)
COMBOS_POR_FATIA = 150000   # combos por processo ao fatiar uma varredura
FRACAO_PROVA = 0.5          # fatiado: a prova pode usar ate metade do tempo restante
RITMO_MAX = 3_000_000       # combos/s por processo no caso mais leve ja medido
RODADA_S = 3.0              # fatiado: cada tarefa no pool dura no maximo isto


def _ordem(s):
    """Ordem total dos planos: chave do ranking e, no empate, os indices dos
    mapas -- assim o resultado nao depende de como a varredura foi fatiada."""
    return (s[0], s[1])


def _n_partes(n, K, K_ja, n_fatias):
    """Em quantas fatias dividir uma varredura (1 = nao vale a pena dividir)."""
    if n_fatias <= 1:
        return 1
    combos = comb(K + n - 1, n) - comb(K_ja + n - 1, n)
    return max(1, min(int(n_fatias), combos // COMBOS_POR_FATIA + 1))


def _orcamento_prova(combos, partes, restante, teto):
    """Segundos que a varredura completa pode usar quando ja existe solucao.
    Com varios processos a prova costuma fechar (60 milhoes de combos em ~70 s
    com 12 processos), entao vale ate metade do tempo restante -- a menos que
    nao caiba nem no ritmo mais rapido ja medido: ai so melhora por `teto`."""
    orc = max(teto, FRACAO_PROVA * restante)
    return teto if combos / (partes * RITMO_MAX) > orc else orc


def varrer_no_pool(ctx, base, partes, top, prazo, prazo_ao_achar, rodar_fatias):
    """Roda uma varredura fatiada em `partes`, em rodadas, fundindo tudo em
    top/ctx. base: payload comum das fatias. Retorna True se terminou."""
    # Rodadas curtas: cada tarefa devolve o processo em ate RODADA_S e a fatia
    # retoma de onde parou. Assim um calculo pesado nao segura o pool inteiro
    # e um calculo simultaneo (outra aba, multi-ref) entra na fila e roda.
    pend = {i: (0, 0) for i in range(partes)}
    lentas = set()          # fatia que rodou uma rodada sem sair do lugar
    while pend:
        agora = time.time()
        if agora >= prazo:
            return False
        curto = min(prazo, agora + RODADA_S)
        itens = sorted(pend.items())
        res = rodar_fatias([dict(base, fatia=(i, partes), k_ini=k,
                                 prazo=prazo if i in lentas else curto)
                            for i, k in itens])
        for (i, k), r in zip(itens, res):
            top.extend(r["top"])
            ctx.truncou = ctx.truncou or r["truncou"]
            ctx.avaliadas += r["avaliadas"]
            ctx.viaveis += r["viaveis"]
            for pecas, v in r["fronteira"].items():
                atual = ctx.fronteira.get(pecas)
                if atual is None or (v[0], v[1]) < (atual[0], atual[1]):
                    ctx.fronteira[pecas] = v
            if r["completo"]:
                del pend[i]
            else:
                novo = tuple(r["parou_em"])
                if novo <= tuple(k) and r["avaliadas"] > 0:
                    lentas.add(i)         # uma linha so ja passa da rodada
                pend[i] = novo
        if prazo_ao_achar is not None and top:
            prazo, prazo_ao_achar = prazo_ao_achar, None   # achou: nivel ganha o resto
        # a retomada refaz a linha interrompida: tira repetidos e guarda so os melhores
        top.sort(key=_ordem)
        top[:] = [s for j, s in enumerate(top) if j == 0 or s[1] != top[j - 1][1]]
        del top[TOP_GUARDA:]
    return True
