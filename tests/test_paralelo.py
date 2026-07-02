"""
Testes do pool de processos (engine/paralelo.py) — v2.12.

O pool existe porque o GIL impede threads de paralelizar calculo: cada solve
roda num processo worker. Aqui garantimos que (a) um solve single e um
multiref atravessam o pool com progresso e resultado integros e (b) dois
solves simultaneos de fato rodam em paralelo.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import paralelo
from engine.tolerancia import calcular_limites_grade

CFG = {
    "consumo_peca_m": 1.0645,
    "mesa_comprimento_m": 10.0,
    "limite_folhas_padrao": 70,
    "num_opcoes_saida": 2,
    "desvio_absoluto_padrao": 4,
    "desvio_percentual_padrao": 20,
    "criterio_combinacao": "MIN",
}
TAMS = ["PP", "P", "M", "G"]
GRADE = {"AZUL": {"PP": 10, "P": 12, "M": 6, "G": 2}}


def _kwargs_single():
    return dict(grade=GRADE, tamanhos=TAMS,
                limites=calcular_limites_grade(GRADE, TAMS, CFG, {}),
                config=CFG, timeout_s=30)


def test_solve_single_pelo_pool():
    msgs = []
    sols, resume = paralelo.executar_solve("single", _kwargs_single(), msgs.append)
    assert sols, "solve pelo pool deveria achar solucao"
    assert sols[0]["resumo"]["n_mapas"] >= 1
    assert msgs, "progresso deveria atravessar o pool"
    # resume pode vir vazio quando a busca retorna cedo (main.py usa defaults)
    assert isinstance(resume, dict)


def test_solve_multiref_pelo_pool():
    refs = [
        {"nome": "A", "grade": GRADE, "consumo": 1.0645,
         "limites": calcular_limites_grade(GRADE, TAMS, CFG, {})},
        {"nome": "B", "grade": {"AZUL": {"PP": 8, "P": 10, "M": 5, "G": 2}},
         "consumo": 1.2,
         "limites": calcular_limites_grade(
             {"AZUL": {"PP": 8, "P": 10, "M": 5, "G": 2}}, TAMS, CFG, {})},
    ]
    msgs = []
    sols, resume = paralelo.executar_solve(
        "multiref",
        dict(refs_data=refs, tamanhos=TAMS, config=CFG, timeout_s=30, n_mapas_max=3),
        msgs.append)
    assert "convergiu" in resume
    assert msgs


def test_dois_solves_em_paralelo_de_verdade():
    """Dois solves simultaneos devem levar ~o tempo de UM (nao a soma)."""
    # aquece o pool (spawn dos workers nao deve contar como tempo de solve)
    paralelo.executar_solve("single", _kwargs_single(), lambda m: None)

    tempos = {}

    def um(nome):
        t0 = time.time()
        paralelo.executar_solve("single", _kwargs_single(), lambda m: None)
        tempos[nome] = time.time() - t0

    t0 = time.time()
    ths = [threading.Thread(target=um, args=(f"t{i}",)) for i in range(2)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    wall = time.time() - t0
    soma = sum(tempos.values())
    # paralelo de verdade: parede < 80% da soma (com folga p/ overhead)
    assert wall < max(1.0, 0.8 * soma), f"wall={wall:.1f}s soma={soma:.1f}s"
