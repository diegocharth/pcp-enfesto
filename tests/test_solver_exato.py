"""
Motor exato single-ref (engine/solver_exato.py).

O que estes testes travam:
  - folhas por cor: TODOS os pontos viaveis, conferidos contra forca bruta;
  - capacidade conjunta: reparte as folhas entre as cores sem ser guloso;
  - solucao final: igual a forca bruta em casos pequenos e nunca pior que o
    motor classico; toda solucao passa no validador independente da bancada;
  - mapa repetido, tolerancia assimetrica ("G nao cresce"), selo de prova,
    corte por tempo e determinismo.
"""
import itertools
import os
import random
import sys

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools", "bench"))

from engine import solver_exato as SE
from engine import exato_fatias as XF
from engine.solver import resolver as resolver_classico
from engine.tolerancia import calcular_limites_grade
import validador

CFG = {"consumo_peca_m": 1.0645, "mesa_comprimento_m": 10.0, "limite_folhas_padrao": 70,
       "num_opcoes_saida": 2, "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN"}
TAMS = ["PP", "P", "M", "G"]
ISADORA = {
    "BLUES":   {"PP": 41, "P": 45, "M": 25, "G": 10},
    "BOSSA":   {"PP": 19, "P": 20, "M": 13, "G": 2},
    "JAZZ":    {"PP": 44, "P": 55, "M": 30, "G": 11},
    "PRETO":   {"PP": 47, "P": 54, "M": 31, "G": 12},
    "SAMBA":   {"PP": 39, "P": 37, "M": 18, "G": 5},
    "VALSA":   {"PP": 45, "P": 50, "M": 23, "G": 5},
    "VANILLA": {"PP": 49, "P": 51, "M": 27, "G": 9},
}


def _resolver(grade, tams, cfg, regras=None, timeout=60, **kw):
    lim = calcular_limites_grade(grade, tams, cfg, regras or {})
    resume = {}
    sols = SE.resolver_exato(grade, tams, lim, cfg, None, timeout_s=timeout,
                             resume_out=resume, **kw)
    for s in sols:
        assert validador.validar(s, grade, tams, lim, cfg) == [], validador.validar(
            s, grade, tams, lim, cfg)
    return sols, resume, lim


# ── folhas por cor ───────────────────────────────────────────────────────────

def test_pontos_cor_bate_com_forca_bruta():
    rnd = random.Random(11)
    tams = ["P", "M", "G"]
    for _ in range(60):
        grade = {"X": {t: rnd.randint(0, 40) for t in tams}}
        cfg = dict(CFG, consumo_peca_m=2.5, limite_folhas_padrao=rnd.choice([12, 30, 70]))
        regras = rnd.choice([{}, {"G": {"hi": 0}}, {"P": {"lo": 0}}])
        lim = calcular_limites_grade(grade, tams, cfg, regras)
        ctx = SE._Ctx(grade, tams, lim, cfg, None)
        if ctx.K < 2:
            continue
        ks = sorted(rnd.sample(range(ctx.K), 2))
        rows = [ctx.maps[k] for k in ks]
        caps = [ctx.F, ctx.F]
        achado = SE._pontos_cor(ctx, 0, ks, rows, caps) or []
        esperado = set()
        for f in itertools.product(range(ctx.F + 1), repeat=2):
            ok = True
            for ti in range(3):
                ct = f[0] * rows[0][ti] + f[1] * rows[1][ti]
                if not (ctx.LO[0][ti] <= ct <= ctx.HI[0][ti]):
                    ok = False
                    break
            if ok:
                esperado.add(f)
        assert {p[3] for p in achado} == esperado
        assert achado == sorted(achado)          # melhor desvio primeiro
        assert not ctx.truncou


# ── capacidade conjunta ─────────────────────────────────────────────────────

class _CtxFalso:
    truncou = False


def test_conjunto_caminho_rapido_quando_o_melhor_de_cada_cor_cabe():
    pts = [[(0, 0.0, 10, (10, 0))], [(1, 0.1, 5, (0, 5))]]
    assert SE._conjunto(_CtxFalso(), pts, [70, 70]) == (1, 0.1, [(10, 0), (0, 5)])


def test_conjunto_troca_o_ponto_de_uma_cor_para_caber():
    # O melhor de cada cor usa 10+10 folhas no mapa 1 (cap 12): nao cabe. A
    # reparticao exata troca a segunda cor para (0,10) e paga desvio 2.
    pts = [[(0, 0.0, 10, (10, 0)), (1, 0.1, 10, (5, 5))],
           [(0, 0.0, 10, (10, 0)), (2, 0.2, 10, (0, 10))]]
    dev, drel, esc = SE._conjunto(_CtxFalso(), pts, [12, 70])
    assert dev == 2 and esc == [(10, 0), (0, 10)]
    assert abs(drel - 0.2) < 1e-9


def test_conjunto_inviavel_quando_nem_os_minimos_cabem():
    pts = [[(0, 0.0, 10, (10,))], [(0, 0.0, 10, (10,))]]
    assert SE._conjunto(_CtxFalso(), pts, [15]) is None


# ── solucao final contra forca bruta ────────────────────────────────────────

def _forca_bruta(grade, tams, lim, cfg, n_max=2):
    """(n, desvio) otimo por enumeracao ingenua, ou None ate n_max enfestos."""
    P = int(cfg["mesa_comprimento_m"] // cfg["consumo_peca_m"])
    F = cfg["limite_folhas_padrao"]
    mapas = [m for m in itertools.product(range(P + 1), repeat=len(tams)) if 1 <= sum(m) <= P]
    cores = list(grade)
    for n in range(1, n_max + 1):
        melhor = None
        for combo in itertools.combinations_with_replacement(mapas, n):
            por_cor = []
            for c in cores:
                pts = []
                for f in itertools.product(range(F + 1), repeat=n):
                    dev, ok = 0, True
                    for ti, t in enumerate(tams):
                        ct = sum(f[k] * combo[k][ti] for k in range(n))
                        d = ct - grade[c].get(t, 0)
                        if d < lim[c][t][0] or d > lim[c][t][1]:
                            ok = False
                            break
                        dev += abs(d)
                    if ok:
                        pts.append((dev, f))
                if not pts:
                    por_cor = None
                    break
                por_cor.append(pts)
            if por_cor is None:
                continue
            for esc in itertools.product(*por_cor):
                if all(sum(e[1][k] for e in esc) <= F for k in range(n)):
                    dev = sum(e[0] for e in esc)
                    if melhor is None or dev < melhor:
                        melhor = dev
        if melhor is not None:
            return n, melhor
    return None


def test_solucao_igual_a_forca_bruta_em_casos_pequenos():
    rnd = random.Random(5)
    tams = ["P", "M"]
    conferidos = 0
    for _ in range(25):
        grade = {c: {t: rnd.randint(2, 14) for t in tams} for c in ("X", "Y")}
        cfg = dict(CFG, consumo_peca_m=3.0, limite_folhas_padrao=rnd.choice([4, 5, 6]))
        sols, resume, lim = _resolver(grade, tams, cfg, timeout=30)
        ref = _forca_bruta(grade, tams, lim, cfg)
        if ref is None:
            assert not sols or sols[0]["n_mapas"] >= 3
            continue
        conferidos += 1
        assert sols, f"forca bruta achou {ref} e o motor nao achou nada: {grade}"
        r = sols[0]["resumo"]
        assert (r["n_mapas"], r["desvio_total"]) == ref, (grade, cfg["limite_folhas_padrao"])
        assert r["prova"] == "provado"
    assert conferidos >= 10


def test_nunca_pior_que_o_motor_classico():
    rnd = random.Random(21)
    tams = ["PP", "P", "M"]
    for _ in range(8):
        grade = {c: {t: rnd.randint(5, 45) for t in tams} for c in ("A", "B")}
        cfg = dict(CFG, consumo_peca_m=rnd.choice([1.9, 2.4]))
        lim = calcular_limites_grade(grade, tams, cfg, {})
        classico = resolver_classico(grade, tams, lim, cfg, None, timeout_s=20)
        sols, _, _ = _resolver(grade, tams, cfg, timeout=30)
        if classico:
            assert sols
            assert validador.chave_ranking(sols[0]) <= validador.chave_ranking(classico[0])


# ── casos de referencia ─────────────────────────────────────────────────────

def test_blazer_isadora_otimo_provado_e_rapido():
    import time
    t0 = time.time()
    sols, resume, _ = _resolver(ISADORA, TAMS, dict(CFG, num_opcoes_saida=1), timeout=60)
    r = sols[0]["resumo"]
    # gabarito CP-SAT: 2 enfestos, desvio 34 (o motor classico parava em 39)
    assert (r["n_mapas"], r["desvio_total"]) == (2, 34)
    assert r["prova"] == "provado" and r["motor"] == SE.MOTOR_ID
    assert len(sols) == 1                      # 1 opcao pedida = so a de menos enfestos
    assert time.time() - t0 < 30
    assert resume["skip_combos"] == 0 and resume["motor"] == SE.MOTOR_ID


# ── opcoes: menos enfestos, 1 enfesto a mais, mapas mais cheios ──────────────

def _papeis(sols):
    return [s["resumo"]["papel"] for s in sols]


def test_opcoes_menos_enfestos_mais_um_enfesto_e_mapas_cheios():
    sols, _, _ = _resolver(ISADORA, TAMS, CFG, timeout=90)
    assert _papeis(sols) == ["minimo_enfestos", "menor_desvio", "mapas_cheios"]
    a, b, c = (s["resumo"] for s in sols)
    assert (a["n_mapas"], a["desvio_total"]) == (2, 34) and a["prova"] == "provado"
    # B: 1 enfesto a mais e desvio MENOR (so entra na lista se for menor)
    assert b["n_mapas"] == 3 and b["desvio_total"] < a["desvio_total"]
    # C: mesmo numero de enfestos, mapas mais cheios, desvio maior (a aprovar)
    assert c["n_mapas"] == 2 and c["media_pecas_mapa"] > a["media_pecas_mapa"]
    assert c["desvio_total"] > a["desvio_total"] and c["prova"] == "provado"
    for r in (a, b, c):
        assert r["rotulo"] and isinstance(r["comparacao"], str)
    assert a["comparacao"] == "" and "enfesto" in b["comparacao"] and "mapa" in c["comparacao"]


def test_sem_opcao_de_mais_enfestos_quando_o_desvio_ja_e_zero():
    grade = {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2}, "ROSA": {"PP": 8, "P": 9, "M": 5, "G": 1}}
    sols, _, _ = _resolver(grade, TAMS, CFG)
    assert sols[0]["resumo"]["desvio_total"] == 0
    assert "menor_desvio" not in _papeis(sols)
    assert len(sols) >= 2                      # completa com alternativa do mesmo nivel


def test_uma_opcao_pedida_devolve_so_a_de_menos_enfestos():
    grade = {"UNICA": {"PP": 82, "P": 104, "M": 62, "G": 17}}
    sols, _, _ = _resolver(grade, TAMS, dict(CFG, consumo_peca_m=1.87, num_opcoes_saida=1))
    assert _papeis(sols) == ["minimo_enfestos"]


def test_tres_opcoes_pedidas_completa_com_alternativas():
    grade = {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2}, "ROSA": {"PP": 8, "P": 9, "M": 5, "G": 1}}
    sols, _, _ = _resolver(grade, TAMS, dict(CFG, num_opcoes_saida=3))
    assert len(sols) >= 3 and _papeis(sols)[0] == "minimo_enfestos"
    assert len({tuple(sorted(tuple(sorted(m.items())) for m in s["mapas"])) for s in sols}) == len(sols)
    assert set(_papeis(sols)[1:]) <= {"menor_desvio", "mapas_cheios", "alternativa"}


def _forca_bruta_nivel(grade, tams, lim, cfg, n):
    """{pecas_totais: menor desvio} de TODOS os planos viaveis com n enfestos."""
    P = int(cfg["mesa_comprimento_m"] // cfg["consumo_peca_m"])
    F = cfg["limite_folhas_padrao"]
    mapas = [m for m in itertools.product(range(P + 1), repeat=len(tams)) if 1 <= sum(m) <= P]
    cores = list(grade)
    out = {}
    for combo in itertools.combinations_with_replacement(mapas, n):
        por_cor = []
        for c in cores:
            pts = []
            for f in itertools.product(range(F + 1), repeat=n):
                dev, ok = 0, True
                for ti, t in enumerate(tams):
                    d = sum(f[k] * combo[k][ti] for k in range(n)) - grade[c].get(t, 0)
                    if d < lim[c][t][0] or d > lim[c][t][1]:
                        ok = False
                        break
                    dev += abs(d)
                if ok:
                    pts.append((dev, f))
            if not pts:
                por_cor = None
                break
            por_cor.append(pts)
        if por_cor is None:
            continue
        melhor = None
        for esc in itertools.product(*por_cor):
            if all(sum(e[1][k] for e in esc) <= F for k in range(n)):
                dev = sum(e[0] for e in esc)
                melhor = dev if melhor is None else min(melhor, dev)
        if melhor is not None:
            pecas = sum(sum(m) for m in combo)
            out[pecas] = min(out.get(pecas, melhor), melhor)
    return out


def test_mapas_cheios_e_o_menor_desvio_entre_os_planos_mais_cheios():
    rnd = random.Random(9)
    tams = ["P", "M"]
    conferidos = 0
    for _ in range(160):
        grade = {c: {t: rnd.randint(2, 14) for t in tams} for c in ("X", "Y")}
        cfg = dict(CFG, consumo_peca_m=3.0, limite_folhas_padrao=rnd.choice([5, 6, 8]),
                   desvio_absoluto_padrao=6, desvio_percentual_padrao=60)
        sols, _, lim = _resolver(grade, tams, cfg, timeout=30)
        if not sols or sols[0]["n_mapas"] > 2:
            continue
        n = sols[0]["n_mapas"]
        ref = _forca_bruta_nivel(grade, tams, lim, cfg, n)
        pecas_a = sum(sum(m.values()) for m in sols[0]["mapas"])
        assert sols[0]["resumo"]["desvio_total"] == min(ref.values())
        assert pecas_a == max(p for p, d in ref.items() if d == min(ref.values()))
        mais_cheios = {p: d for p, d in ref.items() if p > pecas_a}
        cheio = [s for s in sols if s["resumo"]["papel"] == "mapas_cheios"]
        if not mais_cheios:
            assert not cheio
            continue
        conferidos += 1
        assert len(cheio) == 1
        assert cheio[0]["resumo"]["desvio_total"] == min(mais_cheios.values())
        assert sum(sum(m.values()) for m in cheio[0]["mapas"]) == max(
            p for p, d in mais_cheios.items() if d == min(mais_cheios.values()))
    assert conferidos >= 5


def test_tolerancia_assimetrica_g_nao_cresce():
    # Caso em que a descida de coordenadas do classico perde pontos viaveis.
    grade = {"UNICA": {"PP": 82, "P": 104, "M": 62, "G": 17}}
    cfg = dict(CFG, consumo_peca_m=1.87)
    sols, _, lim = _resolver(grade, TAMS, cfg, regras={"G": {"hi": 0}})
    r = sols[0]["resumo"]
    assert (r["n_mapas"], r["desvio_total"]) == (2, 6) and r["prova"] == "provado"
    cortado_g = sum(sols[0]["folhas"]["UNICA"][e] * sols[0]["mapas"][e]["G"] for e in range(2))
    assert cortado_g <= 17


def test_mapa_repetido_divide_a_pilha_entre_enfestos():
    # 200 camadas do mesmo mapa nao cabem em 70 folhas: o otimo repete o mapa.
    grade = {"A": {"P": 200, "M": 200}}
    cfg = dict(CFG, consumo_peca_m=4.0)            # 2 pecas por mapa
    sols, _, _ = _resolver(grade, ["P", "M"], cfg)
    s = sols[0]
    assert s["n_mapas"] == 3 and s["resumo"]["desvio_total"] == 0
    assert s["mapas"] == [{"P": 1, "M": 1}] * 3
    assert sorted(s["folhas"]["A"]) == [60, 70, 70]
    assert s["resumo"]["prova"] == "provado"


def test_tempo_esgotado_nao_quebra_e_informa_retomada():
    resume = {}
    lim = calcular_limites_grade(ISADORA, TAMS, CFG, {})
    sols = SE.resolver_exato(ISADORA, TAMS, lim, CFG, None, timeout_s=0, resume_out=resume)
    assert sols == []
    assert resume["proximo_n"] >= 1 and resume["motor"] == SE.MOTOR_ID


def test_deterministico():
    cfg = dict(CFG, num_opcoes_saida=1)
    a, _, _ = _resolver(ISADORA, TAMS, cfg)
    b, _, _ = _resolver(ISADORA, TAMS, cfg)
    assert [(s["mapas"], s["folhas"]) for s in a] == [(s["mapas"], s["folhas"]) for s in b]


def test_grade_vazia_e_peca_que_nao_cabe_na_mesa():
    lim = calcular_limites_grade({}, TAMS, CFG, {})
    assert SE.resolver_exato({}, TAMS, lim, CFG, None, timeout_s=5) == []
    cfg = dict(CFG, consumo_peca_m=12.0)           # nenhuma peca cabe em 10 m
    g = {"A": {"PP": 5, "P": 5, "M": 5, "G": 5}}
    lim = calcular_limites_grade(g, TAMS, cfg, {})
    assert SE.resolver_exato(g, TAMS, lim, cfg, None, timeout_s=5) == []


def test_varredura_fatiada_e_identica_a_serial(monkeypatch):
    """As fatias (base para rodar um nivel em varios processos) cobrem exatamente
    os mesmos combos da varredura serial, sem repetir nenhum; e a 2a fase pula so
    o que a 1a ja varreu."""
    monkeypatch.setattr(SE, "TOP_GUARDA", 10 ** 6)     # sem descarte: compara tudo
    grade = {"A": {"PP": 30, "P": 41, "M": 22, "G": 9}, "B": {"PP": 18, "P": 25, "M": 15, "G": 4}}
    cfg = dict(CFG, consumo_peca_m=1.9)
    lim = calcular_limites_grade(grade, TAMS, cfg, {})
    for n in (1, 2, 3):
        ctx = SE._Ctx(grade, TAMS, lim, cfg, None)
        K = min(ctx.K, 40)
        serial = []
        assert SE._varrer(ctx, n, K, 0, serial) is True
        ids_serial = sorted(s[1] for s in serial)
        fatiado = []
        for parte in range(3):
            top = []
            assert SE._varrer(ctx, n, K, 0, top, fatia=(parte, 3)) is True
            fatiado.extend(s[1] for s in top)
        assert sorted(fatiado) == ids_serial and len(set(fatiado)) == len(fatiado)
        duas_fases = []
        SE._varrer(ctx, n, K // 2, 0, duas_fases)
        SE._varrer(ctx, n, K, K // 2, duas_fases)
        assert sorted(s[1] for s in duas_fases) == ids_serial
        if n >= 2:
            assert ids_serial, "o caso de teste deveria ter combos viaveis"


# ── integracao com o servidor (/calcular) ───────────────────────────────────

_PAYLOAD = {"referencia": "TESTE", "consumo": 1.0645, "mesa": 10.0, "max_folhas": 70,
            "num_opcoes": 2, "tol_abs": 4, "tol_pct": 20, "criterio": "MIN", "timeout": 30,
            "tamanhos": TAMS, "regras_especiais": {}, "job_id": "t-exato",
            "grade": {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2},
                      "ROSA": {"PP": 8, "P": 9, "M": 5, "G": 1}}}


def _servidor(monkeypatch, tmp_path):
    """main com cache em pasta temporaria e sem gravar nos dados do usuario."""
    import importlib
    import json
    main = importlib.import_module("main")
    cache = main.CachePlanos(os.path.join(tmp_path, "cache.json"),
                             os.path.join(tmp_path, "tempos.json"))
    monkeypatch.setattr(main, "_CACHE", cache)
    for nome in ("salvar_params", "salvar_cores_arquivo", "salvar_historico"):
        monkeypatch.setattr(main, nome, lambda *a, **k: None)
    monkeypatch.setattr(main, "carregar_historico", lambda fp: [])
    monkeypatch.setattr(main, "carregar_cores_salvas", lambda: [])
    with open(os.path.join(RAIZ, "config.json"), encoding="utf-8") as f:
        base = json.load(f)
    base.pop("motor_single", None)                 # testa o padrao do codigo

    def calcular(cfg_extra=None):
        monkeypatch.setattr(main, "carregar_config", lambda: dict(base, **(cfg_extra or {})))
        enviados = []

        class Falso:
            def _send(self, code, data):
                enviados.append((code, data))

        main.Handler._calcular(Falso(), dict(_PAYLOAD))
        return enviados[-1][1]

    return main, cache, calcular


def test_calcular_usa_motor_exato_por_padrao_e_cacheia(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    r = calcular()
    assert r["motor"] == SE.MOTOR_ID and not r.get("cache")
    assert r["solucoes"][0]["resumo"]["prova"] == "provado"
    r2 = calcular()
    assert r2.get("cache") is True and r2["solucoes"] == r["solucoes"]


def test_calcular_motor_classico_por_flag_tem_cache_separado(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    calcular()                                     # grava o cache do motor exato
    r = calcular({"motor_single": "classico"})
    assert r["motor"] == "classico" and not r.get("cache")
    assert "prova" not in r["solucoes"][0]["resumo"]
    assert len(cache._cache) == 2                  # uma entrada por motor


def test_calcular_cai_no_classico_se_o_motor_exato_falhar(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    real = main.paralelo.executar_solve

    def quebrado(tipo, kwargs, cb):
        if tipo == "exato":
            raise RuntimeError("falha simulada do motor exato")
        return real(tipo, kwargs, cb)

    monkeypatch.setattr(main.paralelo, "executar_solve", quebrado)
    r = calcular()
    assert r["solucoes"] and r["motor"] == "classico"
    assert any("classico" in m for m in r["log"])
    assert cache._cache == {}                      # nao cacheia como se fosse exato


def test_motor_exato_pelo_pool_de_processos():
    from engine import paralelo
    grade = {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2}}
    msgs = []
    sols, resume = paralelo.executar_solve("exato", dict(
        grade=grade, tamanhos=TAMS, limites=calcular_limites_grade(grade, TAMS, CFG, {}),
        config=CFG, timeout_s=30), msgs.append)
    assert sols and sols[0]["resumo"]["motor"] == SE.MOTOR_ID
    assert msgs and resume.get("motor") == SE.MOTOR_ID


# ── varredura fatiada entre processos ───────────────────────────────────────

def _nucleo(sols):
    return [(s["mapas"], s["folhas"], s["resumo"]["papel"], s["resumo"]["prova"]) for s in sols]


def test_resultado_fatiado_e_identico_ao_serial(monkeypatch):
    monkeypatch.setattr(XF, "COMBOS_POR_FATIA", 400)      # forca fatiar um caso pequeno
    grade = {"A": {"PP": 30, "P": 41, "M": 22, "G": 9}, "B": {"PP": 18, "P": 25, "M": 15, "G": 4}}
    cfg = dict(CFG, consumo_peca_m=1.9, num_opcoes_saida=3)
    lim = calcular_limites_grade(grade, TAMS, cfg, {})
    serial = SE.resolver_exato(grade, TAMS, lim, cfg, None, timeout_s=120)
    chamadas = []

    def rodar(payloads):
        chamadas.append(len(payloads))
        return [SE._fatia_trabalho(p) for p in payloads]

    fatiado = SE.resolver_exato(grade, TAMS, lim, cfg, None, timeout_s=120,
                                rodar_fatias=rodar, n_fatias=4)
    assert serial and max(chamadas) == 4          # fatiou de verdade
    assert _nucleo(fatiado) == _nucleo(serial)
    assert serial[0]["resumo"]["prova"] == "provado"


def test_numero_de_fatias_cresce_com_o_trabalho():
    assert SE._n_partes(2, 80, 0, 12) == 1        # varredura pequena: 1 processo
    assert SE._n_partes(3, 791, 80, 12) == 12     # 82 milhoes de combos: todos os processos
    assert SE._n_partes(3, 791, 80, 1) == 1


def test_motor_exato_pelo_pool_igual_ao_serial():
    from engine import paralelo
    grade = {"UNICA": {"PP": 82, "P": 104, "M": 62, "G": 17}}
    cfg = dict(CFG, consumo_peca_m=1.87)
    lim = calcular_limites_grade(grade, TAMS, cfg, {"G": {"hi": 0}})
    serial = SE.resolver_exato(grade, TAMS, lim, cfg, None, timeout_s=120)
    msgs = []
    pelo_pool, resume = paralelo.executar_solve(
        "exato", dict(grade=grade, tamanhos=TAMS, limites=lim, config=cfg, timeout_s=120),
        msgs.append)
    assert serial and _nucleo(pelo_pool) == _nucleo(serial)
    assert msgs and resume["motor"] == SE.MOTOR_ID


def test_orcamento_de_prova():
    # cabe folgado: a prova pode usar metade do tempo restante
    assert SE._orcamento_prova(60_000_000, 12, 160.0, 30.0) == 80.0
    # nao cabe nem no ritmo mais rapido: so o tempo curto de melhora
    assert SE._orcamento_prova(20_000_000_000, 12, 160.0, 30.0) == 30.0
    # pouco tempo restante: nunca menos que o tempo de melhora
    assert SE._orcamento_prova(1_000_000, 12, 20.0, 30.0) == 30.0
