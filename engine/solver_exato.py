"""
PCP Enfestos -- Motor exato single-ref (v1)
===========================================

Mesmo problema e mesmo contrato de engine.solver.resolver (que continua intacto
como reserva), com tres heuristicas trocadas por calculo exato:

1. FOLHAS POR COR: propagacao de intervalos + enumeracao da caixa. Devolve
   TODOS os pontos viaveis da cor (a descida de coordenadas do solver classico
   perdia pontos viaveis com tolerancia assimetrica, ex.: "G nao cresce").
2. CAPACIDADE CONJUNTA: o limite de folhas por enfesto e repartido entre as
   cores por busca exata (o classico repartia cor a cor, de forma gulosa).
3. VARREDURA COMPLETA: ate 3 enfestos varre TODOS os mapas possiveis, com
   repeticao (o classico olhava so os 80-125 mais bem ranqueados). Pelo
   servidor, cada varredura e fatiada entre os processos do pool.

Ranking dentro de um mesmo numero de enfestos: menor desvio -> mais pecas/mapa
-> menor desvio relativo. As opcoes devolvidas tem papel definido (ver
resolver_exato): menos enfestos; 1 enfesto a mais com desvio menor; mapas mais
cheios. Cada solucao traz resumo["prova"]:
  "provado"     = a busca cobriu todos os mapas daquele numero de enfestos (e,
                  no primeiro nivel com solucao, provou que menos enfestos e
                  impossivel);
  "nao_provado" = melhor encontrado dentro do tempo ou do pool.

Sem dependencias externas (Python puro) e sem estado global.
"""

import time
from math import comb

from engine.mapas import (gerar_mapas, filtrar_mapas_relevantes, priorizar_mapas,
                          max_pecas_por_mapa)
from engine.exato_fatias import (TOP_GUARDA, COMBOS_POR_FATIA,  # noqa: F401
                                 _ordem, _n_partes, _orcamento_prova,
                                 varrer_no_pool)
from engine.exato_folhas import (MOTOR_ID, _pontos_cor, _conjunto,  # noqa: F401
                                 _distintos, _montar, _comparar)

LIM_POOL = {1: 125, 2: 125, 3: 80, 4: 50, 5: 30, 6: 20, 7: 15}  # = solver classico
N_MAX_COMPLETO = 3          # ate aqui a varredura cobre todos os mapas
N_TETO = 13                 # niveis testados: 1..12
ORC_NIVEL_EXTRA_S = 20.0    # nivel que so completa as opcoes pedidas
FRACAO_SEM_SOLUCAO = 0.6    # nivel sem solucao no pool: deixa tempo p/ o seguinte
TETO_SEM_PROVA_S = 30.0     # ja ha solucao e a prova nao cabe no tempo: melhora so isto


class _Tempo(Exception):
    """Orcamento de tempo esgotado no meio de uma varredura."""


class _Ctx:
    """Dados imutaveis do problema, em listas indexadas (rapido no laco quente)."""

    def __init__(self, grade, tamanhos, limites, config, historicos, mapas=None):
        """mapas: lista ja ordenada (a do coordenador, nas fatias do pool). Sem ela
        a lista e gerada aqui -- e precisa sair igual em qualquer processo."""
        self.tams = list(tamanhos)
        self.T = len(self.tams)
        self.RT = range(self.T)
        self.consumo = float(config.get("consumo_peca_m", 1.0645))
        self.mesa = float(config.get("mesa_comprimento_m", 10.0))
        self.F = int(config.get("limite_folhas_padrao", 70))
        self.P = max_pecas_por_mapa(self.mesa, self.consumo)
        tams = self.tams
        self.cores = sorted(grade.keys(),
                            key=lambda c: sum(grade[c].get(t, 0) for t in tams),
                            reverse=True)
        self.C = len(self.cores)
        self.G, self.LO, self.HI = [], [], []
        for c in self.cores:
            g = [int(grade[c].get(t, 0)) for t in tams]
            lim = [limites.get(c, {}).get(t, (0, 0)) for t in tams]
            self.G.append(g)
            self.LO.append([max(0, g[i] + int(lim[i][0])) for i in self.RT])
            self.HI.append([g[i] + int(lim[i][1]) for i in self.RT])

        if mapas is None:
            grade_total = {t: sum(grade[c].get(t, 0) for c in grade) for t in tams}
            todos = gerar_mapas(tams, self.P) if self.P >= 1 else []
            self.n_todos = len(todos)
            rel = filtrar_mapas_relevantes(todos, grade_total, tams)
            # Mesma ordem do solver classico: o prefixo [:LIM_POOL[n]] e o pool dele.
            prior = priorizar_mapas(rel, grade_total, tams, top_n=max(1, len(rel)),
                                    historicos=historicos) if rel else []
            mapas = [tuple(int(m.get(t, 0)) for t in tams) for m in prior]
            vistos = set()            # um mapa aparece uma vez so no universo
            mapas = [m for m in mapas if not (m in vistos or vistos.add(m))]
        else:
            mapas = [tuple(m) for m in mapas]
            self.n_todos = len(mapas)

        # UB[c][k]: maximo de folhas do mapa k na cor c sem estourar nenhum tamanho.
        ub_all = []
        for c in range(self.C):
            hi = self.HI[c]
            linha = []
            for m in mapas:
                u = self.F * N_TETO
                for t in self.RT:
                    if m[t]:
                        v = hi[t] // m[t] if hi[t] >= 0 else -1
                        if v < u:
                            u = v
                linha.append(max(u, 0))
            ub_all.append(linha)
        # Mapa que nao aceita nem 1 folha em cor nenhuma nunca entra numa solucao.
        usaveis = [k for k in range(len(mapas))
                   if any(ub_all[c][k] >= 1 for c in range(self.C))]
        self.maps = [mapas[k] for k in usaveis]
        self.K = len(self.maps)
        self.UB = [[ub_all[c][k] for k in usaveis] for c in range(self.C)]
        self.pecas = [sum(m) for m in self.maps]
        # CAP0[k][t]: maximo que o mapa k entrega do tamanho t na cor mais pesada.
        ub0 = self.UB[0] if self.C else []
        self.CAP0 = [tuple(m[t] * ub0[k] for t in self.RT)
                     for k, m in enumerate(self.maps)]
        self.truncou = False        # alguma guarda de enumeracao disparou
        self.avaliadas = 0
        self.viaveis = 0
        self.prazo = float("inf")   # limite de tempo da varredura em curso
        self.prazo_ao_achar = None  # se definido, vira o prazo ao achar 1 viavel
        self.teto_sem_prova = None  # se definido, encurta varredura que nao fecha
        self.fronteira = {}         # pecas totais -> melhor plano viavel do nivel
        self.parou_em = (0, 0)      # (1o, 2o) indice em curso quando o tempo acabou

    def piso_enfestos(self):
        """Minimo de enfestos por capacidade de folhas (prova; nunca superestima)."""
        if self.P < 1:
            return 1
        folhas = sum(-(-sum(lo) // self.P) for lo in self.LO)
        return max(1, -(-folhas // max(1, self.F)))


# ---------------------------------------------------------------------------
# Varredura de um nivel (n enfestos)
# ---------------------------------------------------------------------------

def _avaliar(ctx, idx, top):
    """Resolve o combo exato; guarda em `top` se for viavel."""
    ctx.avaliadas += 1
    if time.time() > ctx.prazo:       # a cada combo: combos caros nao estouram o prazo
        raise _Tempo()
    ks, mu = _distintos(idx)
    rows = [ctx.maps[k] for k in ks]
    caps = [ctx.F * m for m in mu]    # mapa repetido = pilha com mais capacidade
    pts = []
    for c in range(ctx.C):
        p = _pontos_cor(ctx, c, ks, rows, caps)
        if p is None:
            return
        pts.append(p)
    r = _conjunto(ctx, pts, caps)
    if r is None:
        return
    ctx.viaveis += 1
    if ctx.prazo_ao_achar is not None:   # achou: o nivel merece o tempo todo
        ctx.prazo = ctx.prazo_ao_achar
        ctx.prazo_ao_achar = None
    pecas = sum(ctx.pecas[k] for k in idx)
    top.append(((r[0], -pecas, r[1]), tuple(idx), r[2]))
    atual = ctx.fronteira.get(pecas)   # melhor desvio para cada enchimento dos mapas
    if atual is None or ((r[0], r[1]), tuple(idx)) < (atual[0], atual[1]):
        ctx.fronteira[pecas] = ((r[0], r[1]), tuple(idx), r[2])
    if len(top) > 8 * TOP_GUARDA:
        top.sort(key=_ordem)
        del top[TOP_GUARDA:]


def _varrer(ctx, n, K, K_ja, top, fatia=(0, 1), k_ini=(0, 0)):
    """Varre todos os multiconjuntos de n mapas entre os K primeiros do universo.
    Combos inteiramente dentro dos K_ja primeiros ja foram varridos e sao pulados.
    fatia=(parte, n_partes) divide o trabalho pelo primeiro indice (para rodar em
    varios processos); k_ini=(i, j) retoma do 1o indice i e, nele, do 2o indice j.
    O limite de tempo e ctx.prazo. Retorna True se terminou; False se o tempo
    acabou (e deixa em ctx.parou_em de onde retomar)."""
    i_ini, j_ini = k_ini
    ctx.parou_em = (i_ini, j_ini)
    if ctx.C == 0 or K < 1:
        return True
    cap0 = ctx.CAP0
    lo0 = ctx.LO[0]
    RT = ctx.RT
    parte, n_partes = fatia
    # maximo que UM mapa qualquer entrega por tamanho (poda dos niveis internos)
    maxcap = [max(cap0[k][t] for k in range(K)) for t in RT]
    clock = time.time
    t_ini = clock()
    # Trabalho desta fatia, em combos: cada primeiro indice i abre um bloco de
    # comb(K - i + n - 2, n - 1) combos. Serve para projetar quando ela termina.
    pesos = {i: comb(K - i + n - 2, n - 1) for i in range(parte, K, n_partes)}
    total = float(sum(pesos.values())) or 1.0
    feito = [float(sum(w for i, w in pesos.items() if i < i_ini)), 0.0]  # [varrido, bloco atual]

    def projetar(parcial):
        """Sem pool: se a varredura nao vai fechar no prazo, limita o tempo gasto
        nela -- a prova nao sai de qualquer forma e ja ha solucao para devolver."""
        gasto = clock() - t_ini
        if gasto < 2.0:
            return
        frac = (feito[0] + parcial) / total    # fracao aproximada ja varrida
        if frac > 0 and gasto / frac > ctx.prazo - t_ini:
            ctx.prazo = min(ctx.prazo, t_ini + ctx.teto_sem_prova)
            ctx.teto_sem_prova = None

    def desce(d, ini, falta, idx, dentro):
        resto = n - d - 1              # mapas ainda por escolher depois deste
        if resto == 0:                 # laco quente: ultimo mapa do combo
            k0 = max(ini, K_ja) if dentro else ini
            passo = n_partes if d == 0 else 1
            if d == 0:
                k0 = max(k0, i_ini)
                if n_partes > 1:
                    k0 += (parte - k0) % n_partes
            for k in range(k0, K, passo):
                ck = cap0[k]
                for t in RT:
                    if ck[t] < falta[t]:
                        break
                else:
                    _avaliar(ctx, idx + (k,), top)
            return
        passo = n_partes if d == 0 else 1
        k0 = ini
        if d == 0:
            k0 = max(k0, i_ini)
            if n_partes > 1:
                k0 += (parte - k0) % n_partes
        elif d == 1 and idx[0] == i_ini:
            k0 = max(k0, j_ini)        # retomada: continua da linha interrompida
        for k in range(k0, K, passo):
            if d == 0:
                ctx.parou_em = (k, 0)
            elif d == 1:
                ctx.parou_em = (idx[0], k)
            if clock() > ctx.prazo:
                raise _Tempo()
            if d == 0:
                feito[1] = pesos[k]
                if ctx.teto_sem_prova is not None:
                    projetar(0.0)
            elif d == 1 and ctx.teto_sem_prova is not None:
                projetar(feito[1] * (1.0 - ((K - k) / (K - idx[0])) ** (n - 1)))
            ck = cap0[k]
            f2 = [falta[t] - ck[t] for t in RT]
            for t in RT:
                if f2[t] > resto * maxcap[t]:
                    break
            else:
                desce(d + 1, k, f2, idx + (k,), dentro and k < K_ja)
            if d == 0:
                feito[0] += feito[1]

    try:
        desce(0, 0, list(lo0), (), True)
    except _Tempo:
        return False
    return True


# ---------------------------------------------------------------------------
# Varredura fatiada entre processos
# ---------------------------------------------------------------------------

def _fatia_trabalho(p):
    """Varre UMA fatia de um nivel num processo separado, por no maximo uma
    rodada (p["prazo"]). Usa a lista de mapas do COORDENADOR (p["mapas"]): os
    indices devolvidos precisam apontar para os mesmos mapas la. Funcao de
    modulo: exigencia do pool (pickle)."""
    ctx = _Ctx(p["grade"], p["tamanhos"], p["limites"], p["config"], None,
               mapas=p["mapas"])
    ctx.prazo = p["prazo"]
    top = []
    completo = _varrer(ctx, p["n"], p["K"], p["K_ja"], top, fatia=p["fatia"],
                       k_ini=tuple(p.get("k_ini", (0, 0))))
    top.sort(key=_ordem)
    return {"completo": completo, "top": top[:TOP_GUARDA], "fronteira": ctx.fronteira,
            "truncou": ctx.truncou, "avaliadas": ctx.avaliadas, "viaveis": ctx.viaveis,
            "parou_em": ctx.parou_em}


# ---------------------------------------------------------------------------
# Solver principal
# ---------------------------------------------------------------------------

def resolver_exato(grade, tamanhos, limites, config, callback_progresso=None,
                   timeout_s=120, min_n_mapas=1, skip_combos=0, historicos=None,
                   resume_out=None, rodar_fatias=None, n_fatias=1):
    """Mesma assinatura e mesmo formato de retorno de engine.solver.resolver.
    skip_combos e aceito por compatibilidade (a retomada e por nivel).

    rodar_fatias(lista_de_payloads) -> lista de resultados de _fatia_trabalho:
    quando informado (pelo engine.paralelo), cada varredura roda em processos do
    pool, dividida em ate n_fatias partes (int ou funcao, reavaliada a cada
    varredura) e em rodadas de RODADA_S, para que outros calculos simultaneos
    consigam processo livre; sem ele, roda aqui mesmo, em serie. O resultado e
    identico nos dois modos quando as varreduras terminam.

    Opcoes devolvidas (resumo["papel"]), nesta ordem:
      minimo_enfestos  melhor plano com o menor numero de enfestos (sempre);
      menor_desvio     melhor plano com 1 enfesto a mais, so se o desvio cair;
      mapas_cheios     mesmo numero de enfestos, mapas mais cheios, desvio maior
                       (o de menor desvio entre os mais cheios) -- a aprovar;
      alternativa      proximos melhores do mesmo nivel, ate num_opcoes_saida.
    Com num_opcoes_saida = 1 volta so a primeira."""
    def log(msg):
        if callback_progresso:
            callback_progresso(msg)

    t0 = time.time()
    deadline = t0 + float(timeout_s)
    num_opcoes = max(1, int(config.get("num_opcoes_saida", 2)))
    log("Gerando mapas candidatos...")
    ctx = _Ctx(grade, tamanhos, limites, config, historicos)
    log(f"Mesa: {ctx.mesa}m | Consumo: {ctx.consumo}m/pca | Max pecas/mapa: {ctx.P}")
    log(f"Limite folhas/enfesto: {ctx.F}")
    log(f"Mapas candidatos: {ctx.K} (de {ctx.n_todos} totais) | motor {MOTOR_ID}")

    piso = ctx.piso_enfestos()
    n_ini = max(1, int(min_n_mapas))
    if piso > 1:
        log(f"Niveis 1..{piso - 1}: impossiveis por capacidade de folhas (prova).")
    # Retomada ("Continuar") acima do piso: os niveis pulados nao foram provados aqui.
    menor_n_provado = n_ini <= piso
    inviaveis = []
    estado = {"cortado": False, "pool_ok": True}

    def varrer(n, K, K_ja, top, prazo, prazo_ao_achar=None, teto_sem_prova=None):
        """Uma varredura, aqui mesmo ou fatiada pelo pool; funde tudo em top/ctx."""
        if rodar_fatias is None:
            ctx.prazo, ctx.prazo_ao_achar, ctx.teto_sem_prova = (
                prazo, prazo_ao_achar, teto_sem_prova)
            return _varrer(ctx, n, K, K_ja, top)
        nf = n_fatias() if callable(n_fatias) else n_fatias
        partes = _n_partes(n, K, K_ja, nf)
        base = {"grade": grade, "tamanhos": list(tamanhos), "limites": limites,
                "config": config, "mapas": ctx.maps, "n": n, "K": K, "K_ja": K_ja}

        if teto_sem_prova is not None:        # ja existe solucao: orcamento de prova
            combos = comb(K + n - 1, n) - comb(K_ja + n - 1, n)
            orc = _orcamento_prova(combos, partes, prazo - time.time(), teto_sem_prova)
            prazo = min(prazo, time.time() + orc)
        return varrer_no_pool(ctx, base, partes, top, prazo, prazo_ao_achar,
                              rodar_fatias)

    def nivel(n, extra):
        """Varre o nivel n; devolve (planos ordenados, completo, fronteira).
        extra=True: nivel de 1 enfesto a mais, com orcamento curto."""
        K_pool = min(ctx.K, LIM_POOL.get(n, 10))
        completo_possivel = n <= N_MAX_COMPLETO
        ctx.truncou = False
        ctx.avaliadas = ctx.viaveis = 0
        ctx.fronteira = {}
        top = []
        log(f"\nTestando {n} mapa(s)... (pool {K_pool}"
            + (f", depois todos os {ctx.K} mapas)" if completo_possivel and ctx.K > K_pool
               else ")"))
        limite = min(deadline, time.time() + ORC_NIVEL_EXTRA_S) if extra else deadline
        ok = varrer(n, K_pool, 0, top, limite)
        completo = False
        if not ok:
            if time.time() >= deadline:        # corte pelo tempo total do calculo
                estado["cortado"] = True
                estado["pool_ok"] = False
        elif completo_possivel and ctx.K > K_pool:
            agora = time.time()
            if extra:
                completo = varrer(n, ctx.K, K_pool, top, limite)
            elif top:                 # nivel principal: prova/melhora ate o fim
                completo = varrer(n, ctx.K, K_pool, top, deadline,
                                  teto_sem_prova=TETO_SEM_PROVA_S)
            else:                     # nada no pool: guarda tempo p/ o proximo
                completo = varrer(n, ctx.K, K_pool, top,
                                  agora + FRACAO_SEM_SOLUCAO * (deadline - agora),
                                  prazo_ao_achar=deadline)
            if not completo and time.time() >= deadline:
                estado["cortado"] = True
        else:
            completo = ctx.K <= K_pool   # o pool ja era o universo inteiro
        completo = completo and not ctx.truncou
        top.sort(key=_ordem)
        log(f"  Combinacoes avaliadas: {ctx.avaliadas:,} | Validas: {ctx.viaveis:,} | "
            + ("completo" if completo else "parcial"))
        if top:
            log(f"  → Melhor: {n} mapas, desvio={top[0][0][0]}pcs, "
                f"{round(-top[0][0][1] / n, 1)}pcs/mapa")
        return top, completo, ctx.fronteira

    # ── menor numero de enfestos com solucao ────────────────────────────────
    nivel_n, top_n, completo_n, front_n = None, [], False, {}
    ultimo_n = max(n_ini, piso)
    proximo_n = ultimo_n              # nivel a (re)fazer se o usuario continuar
    for n in range(max(n_ini, piso), N_TETO):
        proximo_n = n
        if deadline - time.time() <= 0:
            estado["cortado"] = True
            break
        if ctx.K < 1:
            break
        ultimo_n = n
        top, completo, front = nivel(n, extra=False)
        if not estado["cortado"]:
            proximo_n = n + 1
        if top:
            nivel_n, top_n, completo_n, front_n = n, top, completo, front
            break
        if completo:
            inviaveis.append(n)
            log(f"  Nivel {n}: nenhuma combinacao viavel (prova por varredura completa).")
        else:
            menor_n_provado = False
        if estado["cortado"]:
            break

    # ── opcoes: (n, (chave, idx, escolha), provado, papel) ──────────────────
    opcoes = []
    if top_n:
        a = top_n[0]
        dev_a, pecas_a = a[0][0], -a[0][1]
        opcoes.append((nivel_n, a, completo_n and menor_n_provado, "minimo_enfestos"))
        if num_opcoes >= 2:
            # 1 enfesto a mais: so entra se reduzir o desvio
            if (dev_a > 0 and nivel_n + 1 < N_TETO and not estado["cortado"]
                    and deadline - time.time() > 1.0):
                top_b, completo_b, _ = nivel(nivel_n + 1, extra=True)
                if top_b and top_b[0][0][0] < dev_a:
                    opcoes.append((nivel_n + 1, top_b[0], completo_b, "menor_desvio"))
            # mapas mais cheios no mesmo numero de enfestos: custa desvio, entao
            # nunca e automatico -- aparece como opcao para o operador aprovar
            cheios = [(v[0][0], -p, v[0][1], v[1], p, v) for p, v in front_n.items()
                      if p > pecas_a]
            if cheios:
                dev_c, _, drel_c, _, p_c, v = min(cheios, key=lambda x: x[:4])
                opcoes.append((nivel_n, ((dev_c, -p_c, drel_c), v[1], v[2]),
                               completo_n, "mapas_cheios"))
            usados = {o[1][1] for o in opcoes if o[0] == nivel_n}
            for s in top_n[1:]:
                if len(opcoes) >= num_opcoes:
                    break
                if s[1] not in usados:
                    usados.add(s[1])
                    opcoes.append((nivel_n, s, completo_n, "alternativa"))

    if estado["cortado"]:
        log(f"Tempo esgotado ({timeout_s}s) — usando melhor resultado encontrado")

    result = [_montar(ctx, n, ent[1], ent[2], grade,
                      "provado" if provado else "nao_provado", papel)
              for n, ent, provado, papel in opcoes]
    if result:
        base = result[0]["resumo"]
        log("")
        for i, s in enumerate(result, 1):
            r = s["resumo"]
            if i > 1:
                r["comparacao"] = _comparar(base, r)
            log(f"Opcao {i} - {r['rotulo']}: {r['n_mapas']} enfesto(s), desvio "
                f"{r['desvio_total']}pcs, {r['media_pecas_mapa']}pcs/mapa "
                f"({'otimo provado' if r['prova'] == 'provado' else 'melhor encontrado'})")
        log(f"OK {len(result)} opcao(oes). Tempo {time.time() - t0:.1f}s.")
    else:
        log("\nNenhuma solucao encontrada dentro do tempo.")

    if resume_out is not None:
        resume_out["niveis_esgotados"] = inviaveis
        resume_out["ultimo_n_explorado"] = ultimo_n
        resume_out["proximo_n"] = proximo_n
        # 0 = nada foi cortado pelo prazo total (resultado cacheavel, como no
        # classico). Corte pelo prazo = resultado depende do tempo: nao cachear.
        resume_out["skip_combos"] = 0 if estado["pool_ok"] and not estado["cortado"] else 1
        resume_out["cortado"] = bool(estado["cortado"])
        resume_out["motor"] = MOTOR_ID
        resume_out["prova"] = result[0]["resumo"]["prova"] if result else None
    return result
