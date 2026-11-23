"""Etapa 3: avisos honestos e cache por revisao do motor.

- O multi-ref informa POR QUE parou: "impossivel" (prova de capacidade),
  "nao_achou" (a busca terminou por conta propria), "tempo" (o orcamento
  acabou: resultado inconclusivo) ou "ok".
- "convergiu" so e verdadeiro se a busca NAO foi limitada pelo tempo (so esses
  resultados sao cacheados e ensinam o tempo ao sistema).
- Cache e tempos aprendidos levam a revisao do motor.
- A tela traduz cada caso num aviso diferente (funcao pura, testada no Node).
"""
import importlib
import json
import os
import re
import shutil
import subprocess

import pytest

from engine import solver_multiref as SM
from engine.tolerancia import calcular_limites_grade

RAIZ = os.path.join(os.path.dirname(__file__), "..")
CFG = {"mesa_comprimento_m": 10.0, "limite_folhas_padrao": 70, "num_opcoes_saida": 2,
       "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN"}
TAMS = ["PP", "P", "M", "G"]
PEQ_A = {"BLUES": {"PP": 10, "P": 12, "M": 6, "G": 2}}
PEQ_B = {"BLUES": {"PP": 8, "P": 10, "M": 5, "G": 2}}
GRANDE = {"BLUES": {"PP": 300, "P": 300, "M": 300, "G": 300}}


def _ref(nome, grade, consumo=1.0645):
    cfg_r = dict(CFG, consumo_peca_m=consumo)
    return {"nome": nome, "grade": grade, "consumo": consumo,
            "limites": calcular_limites_grade(grade, TAMS, cfg_r, {})}


# ── motivo da parada no solver multi-ref ─────────────────────────────────────

def test_status_impossivel_por_prova_de_capacidade():
    ro = {}
    sols = SM.resolver_multiref([_ref("A", GRANDE), _ref("B", GRANDE)], TAMS, CFG,
                                timeout_s=10, n_mapas_max=1, resume_out=ro)
    assert sols == [] and ro["status"] == "impossivel"
    assert ro["convergiu"] is True                # prova: nao depende de tempo


def test_status_tempo_quando_o_orcamento_acaba():
    # Cores diferentes: a folha compartilhada cortaria pecas nao pedidas, entao
    # nao ha combinacao facil; com 1 s a busca e cortada pelo relogio.
    ro = {}
    refs = [_ref("A", {"BLUES": {"PP": 41, "P": 45, "M": 25, "G": 10}}),
            _ref("B", {"JAZZ": {"PP": 44, "P": 55, "M": 30, "G": 11}}, consumo=1.4)]
    sols = SM.resolver_multiref(refs, TAMS, CFG, timeout_s=1, n_mapas_max=3, resume_out=ro)
    assert sols == [] and ro["status"] == "tempo"
    assert ro["convergiu"] is False               # inconclusivo: nao cachear


def test_status_ok_com_solucao():
    ro = {}
    sols = SM.resolver_multiref([_ref("A", PEQ_A), _ref("B", PEQ_B)], TAMS, CFG,
                                timeout_s=30, n_mapas_max=3, resume_out=ro)
    assert sols and ro["status"] == "ok"


# ── servidor: /calcular_grupo ───────────────────────────────────────────────

def _grupo(monkeypatch, tmp_path, resposta=None):
    """main com cache em pasta temporaria. resposta=(convergiu, status): troca o
    motor multi-ref por uma resposta controlada (testa so a logica do servidor)."""
    main = importlib.import_module("main")
    cache = main.CachePlanos(os.path.join(tmp_path, "c.json"), os.path.join(tmp_path, "t.json"))
    monkeypatch.setattr(main, "_CACHE", cache)
    monkeypatch.setattr(main, "salvar_cores_arquivo", lambda *a, **k: None)
    monkeypatch.setattr(main, "carregar_cores_salvas", lambda: [])
    if resposta is not None:
        convergiu, status = resposta
        sol = {"n_mapas": 2, "refs_sol": [], "comprimentos": [9.0, 9.0], "desvio_total": 7,
               "resumo": {"n_mapas": 2, "desvio_total": 7, "media_pecas_mapa": 5.0}}

        def falso(tipo, kwargs, cb):
            assert tipo == "multiref"
            return ([sol] if status == "ok" else []), {"convergiu": convergiu, "status": status}

        monkeypatch.setattr(main.paralelo, "executar_solve", falso)

    def chamar(refs, n_mapas_max=3, timeout=30):
        enviados = []

        class Falso:
            def _send(self, code, data):
                enviados.append(data)

        main.Handler._calcular_grupo(Falso(), {
            "mesa": 10.0, "max_folhas": 70, "num_opcoes": 2, "tol_abs": 4, "tol_pct": 20,
            "criterio": "MIN", "timeout": timeout, "tamanhos": TAMS, "regras_especiais": {},
            "n_mapas_max": n_mapas_max, "job_id": "t-grupo", "referencia": "A + B",
            "refs": [{"nome": n, "grade": g, "consumo": 1.0645} for n, g in refs]})
        return enviados[-1]

    return main, cache, chamar


def test_grupo_impossivel_responde_com_status(monkeypatch, tmp_path):
    main, cache, chamar = _grupo(monkeypatch, tmp_path)          # motor de verdade
    r = chamar([("A", GRANDE), ("B", GRANDE)], n_mapas_max=1, timeout=10)
    assert r["status"] == "impossivel" and r["erro"]
    assert "imposs" in r["erro"].lower()
    assert cache._tempos == {}            # prova em milissegundos nao ensina tempo


def test_grupo_convergido_cacheia_por_revisao_do_motor(monkeypatch, tmp_path):
    main, cache, chamar = _grupo(monkeypatch, tmp_path, resposta=(True, "ok"))
    r = chamar([("A", PEQ_A), ("B", PEQ_B)])
    assert r["status"] == "ok" and r["convergiu"] is True and not r.get("cache")
    assert chamar([("A", PEQ_A), ("B", PEQ_B)]).get("cache") is True
    # mudou a revisao do motor multi-ref: o plano antigo nao e mais devolvido
    monkeypatch.setattr(main, "MOTOR_MULTIREF_ID", "multiref-teste")
    assert not chamar([("A", PEQ_A), ("B", PEQ_B)]).get("cache")
    # o tempo aprendido fica separado por revisao do motor
    assert cache._tempos and all(k.endswith((":" + SM.MOTOR_ID, ":multiref-teste"))
                                 for k in cache._tempos)


def test_grupo_cortado_pelo_tempo_nao_cacheia_nem_ensina_tempo(monkeypatch, tmp_path):
    main, cache, chamar = _grupo(monkeypatch, tmp_path, resposta=(False, "ok"))
    r = chamar([("A", PEQ_A), ("B", PEQ_B)])
    assert r["status"] == "ok" and r["convergiu"] is False
    assert not chamar([("A", PEQ_A), ("B", PEQ_B)]).get("cache")
    assert cache._cache == {} and cache._tempos == {}


def test_grupo_sem_solucao_por_tempo_avisa_inconclusivo(monkeypatch, tmp_path):
    main, cache, chamar = _grupo(monkeypatch, tmp_path, resposta=(False, "tempo"))
    r = chamar([("A", PEQ_A), ("B", PEQ_B)])
    assert r["status"] == "tempo" and "inconclusivo" in r["erro"].lower()


def test_descida_cortada_pelo_relogio_nao_conta_como_concluida():
    """Medido: com 30 s a busca por 1 enfesto a menos termina no prazo do nivel
    (cortada); com 60 s ela desiste sozinha por estagnacao (concluida)."""
    ro = {}
    sols = SM.resolver_multiref([_ref("A", PEQ_A), _ref("B", PEQ_B)], TAMS, CFG,
                                timeout_s=30, n_mapas_max=3, resume_out=ro)
    assert sols and ro["status"] == "ok" and ro["convergiu"] is False


def test_tempos_aprendidos_separados_por_motor():
    main = importlib.import_module("main")
    g = {"A": {}, "B": {}}
    assert main._bucket_single(g) == "indiv:2c"                    # motor classico
    assert main._bucket_single(g, "exato-9") == "indiv:2c:exato-9"
    assert main._bucket_grupo(2, 4).startswith("grupo:2r:4c:")
    suf = main._sufixos_tempos({"motor_single": "exato"})
    assert suf["sufixo_indiv"] == ":" + main.MOTOR_EXATO_ID
    assert suf["sufixo_grupo"] == ":" + main.MOTOR_MULTIREF_ID
    assert main._sufixos_tempos({"motor_single": "classico"})["sufixo_indiv"] == ""


# ── tela: traducao do status em aviso (funcao pura do interface.html) ───────

@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_tela_distingue_impossivel_tempo_erro_e_sem_ganho():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    m = re.search(r"function _avisoGrupoSemSolucao\(.*?\n}\r?\n", html, flags=re.S)
    assert m, "funcao _avisoGrupoSemSolucao nao encontrada no interface.html"
    casos = [[True, {"erro": "x", "status": "impossivel"}],
             [True, {"erro": "x", "status": "tempo"}],
             [True, {"erro": "x", "status": "nao_achou"}],
             [True, {"erro": "x"}],                       # servidor antigo: sem status
             [False, {"erro": "Erro interno"}]]           # HTTP 500
    js = m.group(0) + "\nconsole.log(JSON.stringify(%s.map(c=>_avisoGrupoSemSolucao(c[0],c[1]))));" % json.dumps(casos)
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert [x["classe"] for x in r] == ["ok", "aviso", "ok", "ok", "erro"]
    assert [x["inconclusivo"] for x in r] == [False, True, False, False, True]
    assert len({x["etiqueta"] for x in r[:3]}) == 3       # tres avisos diferentes
    assert "imposs" in r[0]["msg"].lower() and "tempo" in r[1]["msg"].lower()
    assert "erro" in r[4]["msg"].lower()
    assert all(ord(ch) < 128 for x in r for ch in m.group(0))   # bloco novo so ASCII
