"""Etapa 6, grupo C (robustez):
- C8a: dois calculos que encontram o pool quebrado ao mesmo tempo -- o segundo
  nao pode derrubar o pool novo (saudavel) que o primeiro acabou de criar;
- C8b: "Continuar" (so aparece sem solucao) nao pode pular um nivel de 2-3
  enfestos que ficou varrido so em parte."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import paralelo
from engine import solver_exato as SE
from engine.tolerancia import calcular_limites_grade


class _PoolFalso:
    def __init__(self, quebrado):
        self._broken = quebrado
        self.desligado = False

    def shutdown(self, **k):
        self.desligado = True


def test_c8a_reset_nao_derruba_pool_saudavel(monkeypatch):
    saudavel = _PoolFalso(False)
    monkeypatch.setattr(paralelo, "_pool", saudavel)
    paralelo._reset_pool()                       # outra thread ja recriou o pool
    assert paralelo._pool is saudavel and not saudavel.desligado
    quebrado = _PoolFalso("um processo do pool morreu")
    monkeypatch.setattr(paralelo, "_pool", quebrado)
    paralelo._reset_pool()
    assert paralelo._pool is None and quebrado.desligado


GRADE = {"AZUL": {"P": 30, "M": 30, "G": 30}}
TAMS = ["P", "M", "G"]
CFG = {"mesa_comprimento_m": 10.0, "consumo_peca_m": 1.0, "limite_folhas_padrao": 70,
       "desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN", "num_opcoes_saida": 1}


def _fingir_varredura(monkeypatch, prazos):
    """Niveis 2-3: varredura parcial sem solucao, que para no proprio orcamento
    (nao no prazo total). Niveis 4+: so terminam no prazo total (cortados)."""
    def falso(ctx, n, K, K_ja, top, *a, **k):
        prazos.append((n, K_ja, ctx.prazo))
        if n == 1:
            return True           # 1 enfesto: varredura completa, sem solucao
        if n >= 4:
            while time.time() < ctx.prazo:
                time.sleep(0.01)
            return False
        return K_ja == 0          # pool "completo", varredura total parcial
    monkeypatch.setattr(SE, "_varrer", falso)


def test_c8b_continuar_volta_ao_nivel_parcial(monkeypatch):
    prazos = []
    _fingir_varredura(monkeypatch, prazos)
    lim = calcular_limites_grade(GRADE, TAMS, dict(CFG), {})
    res = {}
    sols = SE.resolver_exato(GRADE, TAMS, lim, dict(CFG), None, timeout_s=1.0, resume_out=res)
    assert sols == []
    assert res["proximo_n"] == 2              # antes: pulava para o nivel cortado (4)


def test_c8b_retomada_da_o_tempo_inteiro_e_nao_trava(monkeypatch):
    prazos = []
    _fingir_varredura(monkeypatch, prazos)
    lim = calcular_limites_grade(GRADE, TAMS, dict(CFG), {})
    res, logs = {}, []
    t0 = time.time()
    SE.resolver_exato(GRADE, TAMS, lim, dict(CFG), logs.append, timeout_s=1.0,
                      min_n_mapas=2, resume_out=res)
    # nivel retomado: a varredura total recebe o prazo inteiro (sem reservar 40%)
    total_n2 = [p for n, kja, p in prazos if n == 2 and kja > 0]
    assert total_n2 and total_n2[0] >= t0 + 0.95
    # continua parcial mesmo assim: segue adiante (sem laco infinito) e avisa
    assert res["proximo_n"] > 2
    assert any("aumente o timeout" in m for m in logs)
