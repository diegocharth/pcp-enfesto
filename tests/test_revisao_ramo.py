"""
Correcoes da revisao independente do ramo solver-exato (23/11/2026).
Cada teste reproduz um achado confirmado pelos revisores:

  1. ordem dos mapas dependia do hash do processo (tamanhos raros empatados)
     -> plano fora da tolerancia marcado "provado" pela busca fatiada;
  2. historico com mapa repetido duplicava o universo (alternativa = Opcao 1);
  3. resultado dependente do tempo ia para o cache e congelava;
  4. um calculo pesado ocupava o pool inteiro e um calculo trivial voltava vazio;
  5. /calcular nao dizia por que nao achou (tempo x busca concluida);
  6. selo "Otimo provado" em opcao que nao e a otima (tela e Excel);
  7. troca de aba / recalculo mexiam nos comprimentos do Audaces errados;
  8. multi-ref e plano salvo sem dizer qual opcao vale.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tools", "bench"))

from engine import solver_exato as SE
from engine.tolerancia import calcular_limites_grade
import validador

CFG = {"consumo_peca_m": 1.9, "mesa_comprimento_m": 10.0, "limite_folhas_padrao": 70,
       "num_opcoes_saida": 2, "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN"}
T5 = ["PP", "P", "M", "G", "GG"]
# Grade do revisor: PP e GG sao raros e EMPATADOS (11 pecas cada).
EMPATE = {"A": {"PP": 4, "P": 33, "M": 44, "G": 20, "GG": 1},
          "B": {"PP": 7, "P": 30, "M": 23, "G": 16, "GG": 10}}
ISADORA = {
    "BLUES": {"PP": 41, "P": 45, "M": 25, "G": 10}, "BOSSA": {"PP": 19, "P": 20, "M": 13, "G": 2},
    "JAZZ": {"PP": 44, "P": 55, "M": 30, "G": 11}, "PRETO": {"PP": 47, "P": 54, "M": 31, "G": 12},
    "SAMBA": {"PP": 39, "P": 37, "M": 18, "G": 5}, "VALSA": {"PP": 45, "P": 50, "M": 23, "G": 5},
    "VANILLA": {"PP": 49, "P": 51, "M": 27, "G": 9}}
T4 = ["PP", "P", "M", "G"]
CFG_ISA = dict(CFG, consumo_peca_m=1.0645)


def _nucleo(sols):
    return [(s["mapas"], s["folhas"], s["resumo"]["papel"], s["resumo"]["prova"]) for s in sols]


# ── 1. ordem dos mapas ──────────────────────────────────────────────────────

_SONDA_HASH = r'''
import hashlib, json, sys
sys.path.insert(0, sys.argv[1])
from engine import solver_exato as SE
from engine.tolerancia import calcular_limites_grade
g = json.loads(sys.argv[2]); t = json.loads(sys.argv[3]); c = json.loads(sys.argv[4])
ctx = SE._Ctx(g, t, calcular_limites_grade(g, t, c, {}), c, None)
print(hashlib.md5(repr(ctx.maps).encode()).hexdigest())
'''


def test_ordem_dos_mapas_nao_depende_do_hash_do_processo():
    saidas = set()
    for seed in ("1", "2", "3", "4"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-B", "-c", _SONDA_HASH, os.path.abspath(RAIZ),
                            json.dumps(EMPATE), json.dumps(T5), json.dumps(CFG)],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        saidas.add(r.stdout.strip())
    assert len(saidas) == 1, "a ordem dos mapas muda com o PYTHONHASHSEED"


def test_fatia_usa_a_lista_de_mapas_do_coordenador():
    lim = calcular_limites_grade(EMPATE, T5, CFG, {})
    ctx = SE._Ctx(EMPATE, T5, lim, CFG, None)
    invertida = list(reversed(ctx.maps))
    outro = SE._Ctx(EMPATE, T5, lim, CFG, None, mapas=invertida)
    assert outro.maps == invertida                 # usa a lista recebida, sem reordenar


def test_empate_de_tamanhos_raros_pelo_pool_igual_ao_serial_e_valido():
    from engine import paralelo
    lim = calcular_limites_grade(EMPATE, T5, CFG, {})
    serial = SE.resolver_exato(EMPATE, T5, lim, CFG, None, timeout_s=120)
    pelo_pool, _ = paralelo.executar_solve(
        "exato", dict(grade=EMPATE, tamanhos=T5, limites=lim, config=CFG, timeout_s=120),
        lambda m: None)
    for s in pelo_pool:
        assert validador.validar(s, EMPATE, T5, lim, CFG) == []
    assert serial and _nucleo(pelo_pool) == _nucleo(serial)


# ── 2. mapas repetidos no historico ─────────────────────────────────────────

def test_historico_com_mapa_repetido_nao_duplica_o_universo_nem_as_opcoes():
    grade = {"A": {"P": 200, "M": 200}}
    cfg = dict(CFG, consumo_peca_m=4.0, num_opcoes_saida=3)
    lim = calcular_limites_grade(grade, ["P", "M"], cfg, {})
    hist = [{"P": 1, "M": 1}] * 3
    ctx = SE._Ctx(grade, ["P", "M"], lim, cfg, hist)
    assert len(ctx.maps) == len(set(ctx.maps))
    sols = SE.resolver_exato(grade, ["P", "M"], lim, cfg, None, timeout_s=30, historicos=hist)
    planos = [tuple(sorted(tuple(sorted(m.items())) for m in s["mapas"])) for s in sols]
    assert len(planos) == len(set(planos)), "duas opcoes com o mesmo plano fisico"


# ── 3. cache so de resultado que nao depende do tempo ───────────────────────

def _servidor(monkeypatch, tmp_path):
    import importlib
    main = importlib.import_module("main")
    cache = main.CachePlanos(os.path.join(tmp_path, "c.json"), os.path.join(tmp_path, "t.json"))
    monkeypatch.setattr(main, "_CACHE", cache)
    for nome in ("salvar_params", "salvar_cores_arquivo", "salvar_historico"):
        monkeypatch.setattr(main, nome, lambda *a, **k: None)
    monkeypatch.setattr(main, "carregar_historico", lambda fp: [])
    monkeypatch.setattr(main, "carregar_cores_salvas", lambda: [])
    with open(os.path.join(RAIZ, "config.json"), encoding="utf-8") as f:
        base = json.load(f)
    base["motor_single"] = "exato"
    monkeypatch.setattr(main, "carregar_config", lambda: dict(base))

    def calcular(grade, tams, timeout, consumo=1.0645, num_opcoes=1):
        enviados = []

        class Falso:
            def _send(self, code, data):
                enviados.append(data)

        main.Handler._calcular(Falso(), {
            "referencia": "T", "consumo": consumo, "mesa": 10.0, "max_folhas": 70,
            "num_opcoes": num_opcoes, "tol_abs": 4, "tol_pct": 20, "criterio": "MIN",
            "timeout": timeout, "tamanhos": tams, "regras_especiais": {}, "job_id": "t-rev",
            "grade": grade})
        return enviados[-1]

    return main, cache, calcular


PEQ = {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2}, "ROSA": {"PP": 8, "P": 9, "M": 5, "G": 1}}


def test_timeout_entra_na_assinatura_do_cache_do_motor_exato(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    assert not calcular(PEQ, T4, 30).get("cache")
    assert calcular(PEQ, T4, 30).get("cache") is True
    assert not calcular(PEQ, T4, 60).get("cache")      # mais tempo: calcula de novo


def test_resultado_cortado_pelo_tempo_nao_vai_para_o_cache(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    grande = {c: {t: int(round(v * 1.5)) for t, v in ts.items()} for c, ts in ISADORA.items()}
    r = calcular(grande, T4, 3)
    assert r.get("cortado") is True
    assert cache._cache == {} and cache._tempos == {}
    assert not calcular(grande, T4, 3).get("cache")


# ── 5. /calcular diz por que nao achou ──────────────────────────────────────

def test_calcular_sem_solucao_por_tempo_informa_status_tempo(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    r = calcular(ISADORA, T4, 0)
    assert r.get("erro") and r.get("status") == "tempo"


def test_calcular_com_solucao_informa_status_ok(monkeypatch, tmp_path):
    main, cache, calcular = _servidor(monkeypatch, tmp_path)
    r = calcular(PEQ, T4, 30)
    assert r.get("status") == "ok" and r.get("cortado") is False


# ── 4. um calculo pesado nao pode matar de fome um calculo trivial ──────────

@pytest.mark.skipif((os.cpu_count() or 1) < 8,
                    reason="mede divisao de processos com muitos nucleos; com 2-4 nucleos "
                           "(maquinas do GitHub Actions) o trivial nao tem tempo de provar")
def test_calculo_pesado_nao_impede_calculo_trivial_simultaneo():
    from engine import paralelo
    grande = {c: {t: int(round(v * 1.5)) for t, v in ts.items()} for c, ts in ISADORA.items()}
    cfg1 = dict(CFG_ISA, num_opcoes_saida=1)
    res = {}

    def pesado():
        lim = calcular_limites_grade(grande, T4, cfg1, {})
        res["pesado"] = paralelo.executar_solve("exato", dict(
            grade=grande, tamanhos=T4, limites=lim, config=cfg1, timeout_s=30), lambda m: None)

    th = threading.Thread(target=pesado)
    th.start()
    time.sleep(12)                  # medido: aos ~10 s o pesado ocupa os 12 processos
    lim = calcular_limites_grade(ISADORA, T4, cfg1, {})
    t0 = time.time()
    sols, _ = paralelo.executar_solve("exato", dict(
        grade=ISADORA, tamanhos=T4, limites=lim, config=cfg1, timeout_s=15), lambda m: None)
    gasto = time.time() - t0
    th.join()
    assert sols, "calculo trivial voltou sem solucao por falta de processo livre"
    r = sols[0]["resumo"]
    assert (r["n_mapas"], r["desvio_total"], r["prova"]) == (2, 34, "provado")
    assert gasto < 12, f"calculo trivial levou {gasto:.1f}s esperando o pesado"


# ── 6. selo de prova no Excel ───────────────────────────────────────────────

def test_excel_so_chama_de_otimo_a_opcao_que_e_otima():
    from exportar.export_xlsx import _prova_txt
    r = lambda papel, prova: {"resumo": {"papel": papel, "prova": prova}}
    assert _prova_txt(r("minimo_enfestos", "provado")) == "Ótimo provado"
    assert _prova_txt(r("menor_desvio", "provado")) == "Ótimo provado"
    assert _prova_txt(r("mapas_cheios", "provado")) == "Busca completa"
    assert _prova_txt(r("alternativa", "provado")) == "Busca completa"
    assert _prova_txt(r("alternativa", "nao_provado")) == "Melhor encontrado"
    assert _prova_txt({"resumo": {}}) is None           # motor classico


# ── 6, 7, 8. tela (funcoes do interface.html rodadas no node) ───────────────

def _js(nomes):
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    partes = []
    for nome in nomes:
        m = re.search(r"\n((?:async )?function %s\(.*?\n})\r?\n" % re.escape(nome), html, flags=re.S)
        assert m, f"funcao {nome} nao encontrada no interface.html"
        partes.append(m.group(1))
    return "\n".join(partes)


def _node(codigo):
    out = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


_MOCK_DOM = r'''
var _els = {};
function _el(id){ if(!_els[id]) _els[id] = {id:id, style:{}, innerHTML:'', textContent:'', classList:{toggle:function(){}}}; return _els[id]; }
var document = {getElementById:_el, querySelectorAll:function(){ return []; }};
var window = {};
var _chamadas = [];
function _esconderResultadoAlocacao(){ _chamadas.push('esconder'); }
function _renderMapasAudaces(){ _chamadas.push('audaces'); }
function _renderPlanoAlocacaoInfo(){ _chamadas.push('info'); }
function atualizarCoresAlocacao(){ _chamadas.push('cores'); }
function _clearStaleCalculo(){}
function renderOp(){ return ''; }
function renderCmp(){ return ''; }
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_tela_selo_so_para_opcao_otima_e_contagem_de_individual_inconclusivo():
    r = _node(_js(["_seloProva", "_individualInconclusivo"]) + r'''
console.log(JSON.stringify({
  s: [['minimo_enfestos','provado'],['menor_desvio','provado'],['mapas_cheios','provado'],
      ['alternativa','provado'],['alternativa','nao_provado'],[undefined,undefined]]
      .map(function(c){ return _seloProva({papel:c[0], prova:c[1]}); }),
  i: [_individualInconclusivo(false, {erro:'x'}), _individualInconclusivo(true, {erro:'x', status:'tempo'}),
      _individualInconclusivo(true, {erro:'x', status:'nao_achou'}), _individualInconclusivo(true, {solucoes:[1], cortado:true}),
      _individualInconclusivo(true, {solucoes:[1], cortado:false})]
}));''')
    textos = [x["texto"] if x else "" for x in r["s"]]
    assert "provado" in textos[0].lower() and "provado" in textos[1].lower()
    assert "provado" not in textos[2].lower() and "completa" in textos[2].lower()
    assert "provado" not in textos[3].lower() and "encontrado" in textos[4].lower()
    assert textos[5] == ""
    assert r["i"] == [True, True, False, True, False]


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_tela_trocar_de_aba_preserva_audaces_do_plano_importado():
    r = _node(_MOCK_DOM + _js(["atOpt"]) + r'''
var resultado = {solucoes:[{}, {}]};
var _planoImportado = {plano:{mapas:[]}};
window._opAtiva = 0; window._compRealAudaces = {1: 4.37};
atOpt(1);
var comImportado = {audaces: window._compRealAudaces, opAtiva: window._opAtiva, chamadas: _chamadas.slice()};
_planoImportado = null; _chamadas = []; window._compRealAudaces = {1: 2.11};
atOpt(0);
console.log(JSON.stringify({comImportado: comImportado, semImportado: {audaces: window._compRealAudaces, chamadas: _chamadas}}));''')
    assert r["comImportado"]["audaces"] == {"1": 4.37} and r["comImportado"]["opAtiva"] == 1
    assert "esconder" not in r["comImportado"]["chamadas"]
    assert r["semImportado"]["audaces"] == {} and "esconder" in r["semImportado"]["chamadas"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_tela_resultado_novo_descarta_audaces_da_opcao_anterior():
    r = _node(_MOCK_DOM + _js(["renderResultado"]) + r'''
window._opAtiva = 1; window._compRealAudaces = {1: 2.11, 3: 1.5};
renderResultado({solucoes:[{resumo:{n_mapas:2}, mapas:[], folhas:{}}], tamanhos:[], grade:{}, limites:{}, config:{}});
console.log(JSON.stringify({audaces: window._compRealAudaces, opAtiva: window._opAtiva, chamadas: _chamadas}));''')
    assert r["audaces"] == {} and r["opAtiva"] == 0 and "audaces" in r["chamadas"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_tela_multiref_e_plano_salvo_dizem_qual_opcao_vale():
    r = _node(_MOCK_DOM + _js(["_sufixoOpcao", "_renderPlanoAlocacaoInfo"]) + r'''
function _montarPlanoParaAlocacao(){ return {mapas:[1]}; }
function _getReferencia(){ return 'REF'; }
var _planoImportado = null;
var resultado = null;
window._resultadoMulti = {grupos:[{}]};
_renderPlanoAlocacaoInfo();
var multi = document.getElementById('aloc-plano-info').textContent;
window._resultadoMulti = null;
resultado = {solucoes:[{resumo:{n_mapas:2, rotulo:'Menos enfestos'}}, {resumo:{n_mapas:3, rotulo:'Menor desvio (+1 enfesto)'}}]};
window._opAtiva = 1;
var suf1 = _sufixoOpcao();
window._opAtiva = 0;
var suf0 = _sufixoOpcao();
console.log(JSON.stringify({multi: multi, suf1: suf1, suf0: suf0}));''')
    assert "aberta em cada grupo" in r["multi"].lower()
    assert "2" in r["suf1"] and "menor desvio" in r["suf1"].lower()
    assert r["suf0"] == ""
    # o texto exibido pode ter acento (vem de escape \u); o que precisa ser ASCII
    # e o codigo-fonte novo do interface.html
    fonte = _js(["_sufixoOpcao", "_renderPlanoAlocacaoInfo", "_seloProva", "_individualInconclusivo"])
    assert all(ord(c) < 128 for c in fonte)


# ── 4b. retomada entre rodadas curtas nao perde nem repete planos ────────────

def test_rodadas_curtas_com_retomada_dao_o_mesmo_resultado_do_serial(monkeypatch):
    from engine import exato_fatias as XF
    monkeypatch.setattr(XF, "RODADA_S", 0.02)       # forca dezenas de retomadas
    monkeypatch.setattr(XF, "COMBOS_POR_FATIA", 400)
    # Isadora: nivel de 2 enfestos com todos os 714 mapas (~255 mil combos), que
    # fecha por completo -- o resultado nao depende do tempo, da para comparar.
    tams, grade = T4, ISADORA
    cfg = dict(CFG_ISA, num_opcoes_saida=1)
    lim = calcular_limites_grade(grade, tams, cfg, {})
    serial = SE.resolver_exato(grade, tams, lim, cfg, None, timeout_s=120)
    retomadas = []

    def rodar(payloads):
        retomadas.extend(tuple(p["k_ini"]) for p in payloads)
        return [SE._fatia_trabalho(p) for p in payloads]

    fatiado = SE.resolver_exato(grade, tams, lim, cfg, None, timeout_s=120,
                                rodar_fatias=rodar, n_fatias=4)
    assert serial and _nucleo(fatiado) == _nucleo(serial)
    assert sum(1 for k in retomadas if k != (0, 0)) > 3    # houve retomadas de verdade
