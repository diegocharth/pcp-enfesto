"""D2: desempate por desvio relativo NUNCA piora (n_mapas, desvio_total); e o
baseline Blazer Isadora permanece. Tambem: solucoes carregam desvio_relativo."""
import json, os
from engine.solver import resolver
from engine.tolerancia import calcular_limites_grade

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRADE = {
    'BLUES':   {'PP':41,'P':45,'M':25,'G':10},
    'BOSSA':   {'PP':19,'P':20,'M':13,'G':2},
    'JAZZ':    {'PP':44,'P':55,'M':30,'G':11},
    'PRETO':   {'PP':47,'P':54,'M':31,'G':12},
    'SAMBA':   {'PP':39,'P':37,'M':18,'G':5},
    'VALSA':   {'PP':45,'P':50,'M':23,'G':5},
    'VANILLA': {'PP':49,'P':51,'M':27,'G':9},
}
TAMS = ['PP','P','M','G']


def _cfg():
    cfg = json.load(open(os.path.join(BASE, 'config.json'), encoding='utf-8'))
    cfg.update({'consumo_peca_m':1.0645,'mesa_comprimento_m':10.0,'limite_folhas_padrao':70})
    return cfg


def test_baseline_blazer_isadora_nao_piora():
    cfg = _cfg()
    lim = calcular_limites_grade(GRADE, TAMS, cfg, {})
    sols = resolver(GRADE, TAMS, lim, cfg, lambda m: None, timeout_s=60)
    assert len(sols) >= 2
    assert sols[0]['resumo']['n_mapas'] == 2 and sols[0]['resumo']['desvio_total'] <= 39
    assert sols[1]['resumo']['n_mapas'] == 3 and sols[1]['resumo']['desvio_total'] <= 13


def test_solucoes_tem_desvio_relativo():
    cfg = _cfg()
    lim = calcular_limites_grade(GRADE, TAMS, cfg, {})
    sols = resolver(GRADE, TAMS, lim, cfg, lambda m: None, timeout_s=60)
    for s in sols:
        assert 'desvio_relativo' in s['resumo']
        assert s['resumo']['desvio_relativo'] >= 0
