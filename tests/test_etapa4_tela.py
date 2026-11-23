"""Etapa 4 (tela do multi-ref), funcoes puras do interface.html rodadas no node:
- agrupamentos empatados em enfestos desempatam pelo menor desvio;
- teto de enfestos de um grupo usa a melhor particao interna ja calculada;
- a alocacao usa a opcao aberta em cada grupo (nao sempre a Opcao 1)."""
import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
NOVAS = {"_avaliarParticoesCache", "_tetoGrupo", "_solucaoDoGrupo"}
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")


def _js(nomes):
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    partes = []
    for nome in nomes:
        m = re.search(r"\n((?:async )?function %s\(.*?\n})\r?\n" % re.escape(nome), html, flags=re.S)
        assert m, f"funcao {nome} nao encontrada no interface.html"
        if nome in NOVAS:     # funcoes criadas nesta etapa: codigo-fonte so ASCII
            assert all(ord(c) < 128 for c in m.group(1)), f"{nome}: codigo novo precisa ser ASCII"
        partes.append(m.group(1))
    return "\n".join(partes)


def _node(codigo):
    out = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _g(n, desvio, tipo="single"):
    return {"nEnfestos": n, "tipo": tipo, "data": {"solucoes": [{"resumo": {"n_mapas": n, "desvio_total": desvio}}]}}


def test_particoes_empatadas_desempatam_pelo_menor_desvio():
    cache = {"0": _g(3, 13), "1": _g(2, 13), "2": _g(2, 24),
             "0,1": _g(4, 57, "multiref"), "0,2": _g(4, 30, "multiref")}
    r = _node(_js(["_particoes", "_avaliarParticoesCache"]) + r'''
var out = _avaliarParticoesCache([0,1,2], %s);
console.log(JSON.stringify(out.map(function(p){ return [p.total, p.desvio, p.grupos.map(function(g){ return g.key; })]; })));''' % json.dumps(cache))
    assert r[0][0] == 6 and r[1][0] == 6                       # [0,1]+2 e [0,2]+1
    assert r[0][1] < r[1][1]                                   # menor desvio primeiro
    assert sorted(r[0][2]) == ["0,2", "1"] and r[0][1] == 30 + 13
    assert r[-1][0] == 7                                       # tudo separado por ultimo


def test_teto_do_grupo_usa_a_melhor_particao_interna():
    cache = {"0": _g(3, 13), "1": _g(2, 13), "2": _g(2, 24), "0,1": _g(4, 57, "multiref"),
             "0,2": {"erro": "sem ganho"}, "1,2": {"erro": "sem ganho"}}
    r = _node(_js(["_particoes", "_tetoGrupo"]) + r'''
var cache = %s;
console.log(JSON.stringify({
  trio: _tetoGrupo([0,1,2], cache, Infinity),
  trioGlobal: _tetoGrupo([0,1,2], cache, 5),
  par: _tetoGrupo([1,2], cache, Infinity),
  semIndividual: _tetoGrupo([0,3], cache, Infinity)
}));''' % json.dumps(cache))
    # trio: separado 7, [0,1]+2 = 6 -> so vale se fizer em ate 5
    assert r["trio"] == 5
    assert r["trioGlobal"] == 4                                # melhor particao global 5 -> ate 4
    assert r["par"] == 3                                       # 2 + 2 separados -> ate 3
    assert r["semIndividual"] >= 99                            # sem dado: nao limita


def test_alocacao_multiref_usa_a_opcao_aberta_em_cada_grupo():
    r = _node(_js(["_montarPlanoParaAlocacao", "_solucaoDoGrupo"]) + r'''
var window = {_compRealAudaces: {}};
var _planoImportado = null, resultado = null;
function sol(n){ var mapas=[], folhas={AZUL:[]}; for(var k=0;k<n;k++){ mapas.push({P:1}); folhas.AZUL.push(5); }
  return {mapas: mapas, folhas: folhas, resumo: {n_mapas: n}}; }
window._resultadoMulti = {grupos: [
  {tipo: 'single', data: {config: {consumo_peca_m: 1}, solucoes: [sol(2), sol(3)]}},
  {tipo: 'single', data: {config: {consumo_peca_m: 1}, solucoes: [sol(1), sol(4)]}}]};
window._opGrupo = {0: 1};
var p = _montarPlanoParaAlocacao();
window._opGrupo = {};
var p0 = _montarPlanoParaAlocacao();
console.log(JSON.stringify({com: p.mapas.length, sem: p0.mapas.length}));''')
    assert r["com"] == 3 + 1          # grupo 0 na Opcao 2 (3 enfestos), grupo 1 na Opcao 1
    assert r["sem"] == 2 + 1
