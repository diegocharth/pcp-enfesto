"""Etapa 2: a planilha mostra o papel de cada opcao (menos enfestos, 1 enfesto
a mais, mapas mais cheios), a comparacao com a Opcao 1 e o selo de prova -- e
continua exportando os planos do motor classico, que nao tem esses campos."""
import openpyxl

from engine.solver import resolver as resolver_classico
from engine.solver_exato import resolver_exato
from engine.tolerancia import calcular_limites_grade
from exportar.export_xlsx import exportar

CFG = {"consumo_peca_m": 1.87, "mesa_comprimento_m": 10.0, "limite_folhas_padrao": 70,
       "num_opcoes_saida": 2, "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN"}
TAMS = ["PP", "P", "M", "G"]
GRADE = {"UNICA": {"PP": 82, "P": 104, "M": 62, "G": 17}}
REGRAS = {"G": {"hi": 0}}


def _textos(caminho):
    wb = openpyxl.load_workbook(caminho)
    return wb, {ws.title: " | ".join(str(c.value) for linha in ws.iter_rows() for c in linha
                                     if c.value is not None) for ws in wb.worksheets}


def test_planilha_mostra_papel_comparacao_e_prova(tmp_path):
    lim = calcular_limites_grade(GRADE, TAMS, CFG, REGRAS)
    sols = resolver_exato(GRADE, TAMS, lim, CFG, None, timeout_s=60)
    papeis = [s["resumo"]["papel"] for s in sols]
    assert papeis[:2] == ["minimo_enfestos", "menor_desvio"]     # premissa do teste
    wb, txt = _textos(exportar(sols, GRADE, TAMS, lim, dict(CFG), "TESTE", str(tmp_path)))
    resumo = txt["Resumo"]
    assert "Opção 1 — Menos enfestos" in resumo
    assert "Opção 2 — Menor desvio (+1 enfesto)" in resumo
    assert "Ótimo provado" in resumo                              # selo de prova
    assert sols[1]["resumo"]["comparacao"] in resumo              # "+1 enfesto, -N peças..."
    # o texto de trade-off nao pode recomendar a Opcao 2 sem dizer que ela usa mais enfestos
    assert "Recomenda-se Opção 2" not in resumo
    assert "menos enfestos" in resumo.lower()
    assert "MENOS ENFESTOS" in txt["Op1_Plano"] and "Ótimo provado" in txt["Op1_Plano"]
    assert "MENOR DESVIO" in txt["Op2_Plano"]


def test_planilha_do_motor_classico_continua_igual(tmp_path):
    lim = calcular_limites_grade(GRADE, TAMS, CFG, REGRAS)
    sols = resolver_classico(GRADE, TAMS, lim, CFG, None, timeout_s=30)
    assert sols and "papel" not in sols[0]["resumo"]
    wb, txt = _textos(exportar(sols, GRADE, TAMS, lim, dict(CFG), "TESTE", str(tmp_path)))
    assert "Opção 1" in txt["Resumo"] and "Menos enfestos" not in txt["Resumo"]
    assert "provado" not in txt["Resumo"].lower()
