"""Etapa 6 (confiabilidade da tela), funcoes do interface.html rodadas no node:
- A1: plano desatualizado (grade/parametros mudaram) nao vai para a alocacao;
- A2: "Exportar Planilha" depois de um calculo de 1 referencia nao exporta o
  agrupamento multi-ref de um calculo anterior;
- A3: linhas do PDF de rolos que o leitor nao entendeu aparecem como aviso."""
import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")


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
    return json.loads(out.stdout.strip().splitlines()[-1])


DOM = r'''
var _els = {};
var document = {getElementById: function(id){
  if (!_els[id]) _els[id] = {id: id, textContent: '', innerHTML: '', value: '30', style: {display: 'block'}};
  return _els[id]; }};
'''


def test_a2_exportar_depois_de_single_nao_usa_agrupamento_antigo():
    r = _node(DOM + _js(["exportarTodos"]) + r'''
var chamadas = [];
async function exportar(d){ chamadas.push('single'); }
async function fetch(url){ chamadas.push(url); return {json: async function(){ return {}; }}; }
async function _autoSalvarPlano(){}
var window = {_multiGrupoValidos: [{grupos: [{tipo: 'single', data: {}}]}], _resultadoMulti: null};
(async function(){
  await exportarTodos();                       // resultado atual: 1 referencia
  var depoisSingle = chamadas.slice();
  chamadas = [];
  window._resultadoMulti = {grupos: []};       // resultado atual: multi-ref
  await exportarTodos();
  console.log(JSON.stringify({single: depoisSingle, multi: chamadas}));
})();''')
    assert r["single"] == ["single"]
    assert r["multi"] == ["/exportar_particao"]


def test_a2_calcular_e_limpar_esquecem_o_agrupamento_anterior():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    ini = html.index("resultado=null; window._resultadoMulti=null;")
    assert "_multiGrupoValidos=null" in html[ini:ini + 400]
    lim = re.search(r"\nfunction limpar\(\)\{.*?\n}\r?\n", html, flags=re.S).group(0)
    assert "_multiGrupoValidos=null" in lim


def test_a1_plano_desatualizado_nao_vai_para_a_alocacao():
    r = _node(DOM + _js(["_esconderResultadoPlano", "_esconderResultadoAlocacao",
                         "_montarPlanoParaAlocacao", "_renderPlanoAlocacaoInfo",
                         "_getReferencia", "_sufixoOpcao", "_solucaoDoGrupo"]) + r'''
var window = {_compRealAudaces: {}, _opAtiva: 0};
var _planoImportado = null;
var resultado = {referencia: 'REF', config: {consumo_peca_m: 1},
  solucoes: [{mapas: [{P: 2}], folhas: {AZUL: [5]}, resumo: {n_mapas: 1}}]};
var antes = _montarPlanoParaAlocacao();
_esconderResultadoPlano();                     // operador mudou a grade
var depois = _montarPlanoParaAlocacao();
_renderPlanoAlocacaoInfo();
var info = document.getElementById('aloc-plano-info').textContent;
_planoImportado = {referencia: 'IMP', plano: {mapas: [{id: 1, composicao: {P: 1}, n_pecas: 1}],
  camadas: {AZUL: {1: 3}}, consumo_peca: 1}};
var importado = _montarPlanoParaAlocacao();    // plano importado nao depende da grade
console.log(JSON.stringify({antes: !!antes, depois: depois, info: info, importado: !!importado}));''')
    assert r["antes"] is True
    assert r["depois"] is None
    assert "desatualizado" in r["info"]
    assert r["importado"] is True


def test_a1_resultado_novo_volta_a_valer():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    for nome in ("renderResultado", "renderResultadoGrupos", "renderResultadoComComparacao"):
        m = re.search(r"\nfunction %s\(.*?\n}\r?\n" % nome, html, flags=re.S)
        assert m and "_planoObsoleto=false" in m.group(0).replace(" ", ""), nome


def test_a3_linhas_do_pdf_nao_entendidas_viram_aviso():
    r = _node(DOM + _js(["importarRolosPdf"]) + r'''
var resumoFinal = null;
function _finalizarImportRolos(p, resumo){ resumoFinal = resumo; }
function _addRolosImportados(x){ return {novos: 2, repetidos: 0}; }
function FileReader(){}
FileReader.prototype.readAsDataURL = function(f){ this.result = 'data:x;base64,QUJD'; var s = this; setTimeout(function(){ s.onload(); }, 0); };
async function fetch(url, o){ return {json: async function(){ return {
  total_rolos: 2, formato: 'Reserva', rolos_por_cor_comercial: {AZUL: [{comprimento_m: 50}]},
  nao_mapeados: {}, linhas_nao_parseadas: ['123 4A5 49,6', 'XYZ 77 lote?', 'AVISO: o PDF informa 3 rolos']}; }}; }
importarRolosPdf({files: [{name: 'reserva.pdf'}], value: ''});
setTimeout(function(){ console.log(JSON.stringify(resumoFinal.avisos)); }, 50);''')
    texto = " | ".join(r)
    assert "AVISO: o PDF informa 3 rolos" in texto
    assert "2 linha(s)" in texto and "123 4A5 49,6" in texto


# --- achados da revisao independente da Etapa 6 ------------------------------

def _onload():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    m = re.search(r"\nwindow\.onload = async \(\) => \{(.*?)\n\};", html, flags=re.S)
    assert m
    return m.group(1)


def test_aviso_de_biblioteca_aparece_sem_chave_da_api():
    # Sem chave da API (padrao da fabrica), uma linha anterior quebrava
    # (id "api-box" nao existe) e o aviso nunca aparecia.
    r = _node(r'''
var _els = {};
var document = {getElementById: function(id){
  if (id === 'api-box') return null;
  if (!_els[id]) _els[id] = {style: {display: 'none'}, textContent: ''};
  return _els[id]; }};
var window = {};
function renderTams(){} function renderTol(){} async function carregarDados(){}
function addRef(){} function atualizarCoresAlocacao(){} function verificarUpdate(){}
function setTimeout(){}
async function fetch(url){ return {json: async function(){
  return url === '/config_pub' ? {tem_api_key: false, faltando: ['numpy']} : {versao: 'x'}; }}; }
''' + _js(["_avisoBibliotecas"]) + "\nvar onload = async () => {" + _onload() + r'''
};
onload().then(function(){ var b = _els['libs-banner'];
  console.log(JSON.stringify({display: b.style.display, texto: b.textContent})); });''')
    assert r["display"] == "block" and "numpy" in r["texto"]


def test_aviso_de_biblioteca_fica_no_topo_da_pagina():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    assert html.index('id="libs-banner"') < html.index("<!-- PAR")


def test_limpar_nao_quebra_e_esquece_o_plano():
    r = _node(r'''
var _els = {};
var document = {getElementById: function(id){
  if (id === 'upload-st') return null;          // nao existe no HTML
  if (!_els[id]) _els[id] = {style: {display: 'block'}, textContent: 'x', innerHTML: 'x'};
  return _els[id]; }};
var window = {_resultadoMulti: {grupos: []}, _multiGrupoValidos: [1], _planoObsoleto: true};
var cores = [], cadastroCores = ['AZUL'], refs = [1], pid = 3, resultado = {x: 1};
var _rolosPorCor = {A: [1]}, _rolosImportados = {}, _planoImportado = {p: 1}, _equivPendentes = null;
function renderCoresGrid(){} function addRef(){} function _renderEquivalencias(){} function _renderPlanoAlocacaoInfo(){}
''' + _js(["limpar"]) + r'''
var erro = null;
try { limpar(); } catch(e) { erro = String(e); }
console.log(JSON.stringify({erro: erro, resultado: resultado, multi: window._multiGrupoValidos,
  obsoleto: window._planoObsoleto, importado: _planoImportado}));''')
    assert r["erro"] is None
    assert r["resultado"] is None and r["multi"] is None and r["importado"] is None
    assert r["obsoleto"] is False


def test_alocar_sem_calculo_pede_para_calcular():
    r = _node(r'''
var _els = {};
var document = {getElementById: function(id){
  if (!_els[id]) _els[id] = {style: {display: ''}, textContent: '', value: '1', checked: false};
  return _els[id]; }};
var window = {_planoObsoleto: true};             // digitou a grade, nunca calculou
var _rolosImportados = {}, _rolosPorCor = {AZUL: [50]}, resultado = null;
function _montarPlanoParaAlocacao(){ return null; }
''' + _js(["iniciarAlocacao"]) + r'''
iniciarAlocacao().then(function(){ console.log(JSON.stringify(_els['aloc-st'].textContent)); });''')
    assert r.startswith("Calcule um plano de corte primeiro")


def test_resultado_de_entrada_antiga_fica_desatualizado():
    # Grade editada DURANTE o calculo: o resultado que chega e da grade antiga.
    r = _node(DOM + _js(["_esconderResultadoPlano", "_esconderResultadoAlocacao",
                         "_conferirVersaoCalc"]) + r'''
var window = {};
function _renderPlanoAlocacaoInfo(){}
var v0 = window._versaoEntrada || 0;          // calculo comeca
_esconderResultadoPlano();                     // operador edita a grade
window._planoObsoleto = false;                 // resultado chega (render zera)
document.getElementById('rb').style.display = 'block';
_conferirVersaoCalc(v0);
var depois = window._planoObsoleto;
var v1 = window._versaoEntrada;                // novo calculo, sem edicao
window._planoObsoleto = false;
_conferirVersaoCalc(v1);
console.log(JSON.stringify({editado: depois, limpo: window._planoObsoleto}));''')
    assert r == {"editado": True, "limpo": False}


def test_continuar_recusa_entrada_que_mudou_e_descarta_importado():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    m = re.search(r"async function continuarBusca\(proxN, skipC\)\{(.*?)\n  \}\n", html, flags=re.S)
    assert m
    corpo = m.group(1)
    assert corpo.index("_versaoEntrada") < corpo.index("fetch('/calcular'")
    assert "_planoImportado=null" in corpo.replace(" ", "")
