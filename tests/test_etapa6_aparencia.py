"""Etapa 6, grupo D (aparencia e textos):
- D9: nenhum texto corrompido (UTF-8 gravado duas vezes, ex.: "â¹ Encerrar");
- D10: enfesto combinado nao mostra bloco vazio da referencia sem pecas nele;
- D11a: comparacao de opcoes diz que a Opcao 1 e melhor quando ela ganha nas
  duas medidas (antes so listava os numeros);
- D11b: "Padrao + 1 alternativa extra" entrega de fato 1 opcao a mais."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
HTML = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
tem_node = pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")


def _js(nome):
    m = re.search(r"\n((?:async )?function %s\(.*?\n})\r?\n" % re.escape(nome), HTML, flags=re.S)
    assert m, nome
    return m.group(1)


def _node(codigo):
    out = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_d9_sem_texto_corrompido():
    ruins = [(HTML.count("\n", 0, m.start()) + 1, m.group(0))
             for m in re.finditer(r"[ÃÂâ][\u0080-¿]", HTML)]
    assert ruins == [], ruins


@tem_node
def test_d10_enfesto_combinado_sem_bloco_vazio():
    sol = {"resumo": {"n_mapas": 1, "total_folhas": 10, "desvio_total": 0, "comprimento_total": 5},
           "comprimentos": [5.0],
           "refs_sol": [
               {"nome": "REF A", "consumo": 1, "grade": {"AZUL": {"P": 10}},
                "mapas": [{"P": 5}], "folhas": {"AZUL": [2]}},
               {"nome": "REF B", "consumo": 1, "grade": {"AZUL": {"P": 0}},
                "mapas": [{}], "folhas": {"AZUL": [2]}}]}
    r = _node(_js("renderOpMultiref") + "\nconsole.log(JSON.stringify(renderOpMultiref(%s, ['P'], 1)));"
              % json.dumps(sol))
    bloco = r.split("Enfesto Combinado 1")[1].split("Totalizador")[0]
    assert "REF A - Mapa: 5P" in bloco
    assert "REF B - Mapa" not in bloco


def _sol(n, dev, ppm):
    return {"resumo": {"n_mapas": n, "desvio_total": dev, "media_pecas_mapa": ppm},
            "mapas": [{"P": 1}], "folhas": {"AZUL": [1]}}


@tem_node
def test_d11a_tela_recomenda_opcao_1_quando_ela_domina():
    sols = [_sol(2, 5, 6), _sol(2, 9, 5)]
    r = _node(_js("renderCmp") + "\nconsole.log(JSON.stringify(renderCmp(%s, ['P'], {AZUL: {P: 1}}, {})));"
              % json.dumps(sols))
    assert "Recomenda-se Op" in r and "1." in r.split("Recomenda-se Op")[1][:20]


def test_d11a_excel_recomenda_opcao_1_quando_ela_domina():
    from exportar.export_xlsx import _calcular_tradeoff
    t = _calcular_tradeoff([_sol(2, 5, 6), _sol(2, 9, 5)], {}, [])
    assert "Recomenda-se Opção 1" in t["msg"]
    t2 = _calcular_tradeoff([_sol(2, 5, 6), _sol(2, 5, 6)], {}, [])   # empate: nao recomenda
    assert "Recomenda-se" not in t2["msg"]


def test_d11b_mais_uma_alternativa_entrega_uma_opcao_a_mais():
    from engine.solver_exato import resolver_exato
    from engine.tolerancia import calcular_limites_grade
    # grade sintetica em que os 3 papeis existem (com "2" ja vem 3 opcoes) e
    # ainda ha outros planos validos com o minimo de enfestos
    grade = {"AZUL": {"PP": 12, "P": 6, "M": 11, "G": 15}, "ROSA": {"PP": 1, "P": 13, "M": 12, "G": 31}}
    tams = ["PP", "P", "M", "G"]
    cfg = {"mesa_comprimento_m": 10.0, "consumo_peca_m": 1.93, "limite_folhas_padrao": 70,
           "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20, "criterio_combinacao": "MIN"}
    lim = calcular_limites_grade(grade, tams, dict(cfg), {"G": {"hi": 0}})
    s2 = resolver_exato(grade, tams, lim, dict(cfg, num_opcoes_saida=2), None, timeout_s=30)
    s3 = resolver_exato(grade, tams, lim, dict(cfg, num_opcoes_saida=3), None, timeout_s=30)
    papeis2 = [s["resumo"]["papel"] for s in s2]
    papeis3 = [s["resumo"]["papel"] for s in s3]
    assert len(s3) == len(s2) + 1, (papeis2, papeis3)
    assert papeis3[:len(papeis2)] == papeis2 and papeis3[-1] == "alternativa"
