"""
Testes do modulo engine/cache_planos.py

Cache persistente de resultados de calculo + aprendizado de tempos de solve.
Objetivo: recalculo identico instantaneo e ETA realista que melhora com o uso.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.cache_planos import assinatura, CachePlanos


# ---------------------------------------------------------------------------
# assinatura(payload) -- hash estavel e independente de ordem de chaves
# ---------------------------------------------------------------------------

def test_assinatura_independente_de_ordem_de_chaves():
    a = assinatura({"grade": {"BLUES": {"PP": 1, "P": 2}}, "consumo": 1.0645, "mesa": 10.0})
    b = assinatura({"mesa": 10.0, "consumo": 1.0645, "grade": {"BLUES": {"P": 2, "PP": 1}}})
    assert a == b


def test_assinatura_muda_com_grade_diferente():
    a = assinatura({"grade": {"BLUES": {"PP": 1}}, "consumo": 1.0645})
    b = assinatura({"grade": {"BLUES": {"PP": 2}}, "consumo": 1.0645})
    assert a != b


def test_assinatura_muda_com_consumo_diferente():
    a = assinatura({"grade": {"BLUES": {"PP": 1}}, "consumo": 1.0645})
    b = assinatura({"grade": {"BLUES": {"PP": 1}}, "consumo": 1.10})
    assert a != b


def test_assinatura_e_string_nao_vazia():
    a = assinatura({"grade": {"X": {"PP": 1}}})
    assert isinstance(a, str) and len(a) > 0


# ---------------------------------------------------------------------------
# Cache de resultados -- guardar / obter / persistencia
# ---------------------------------------------------------------------------

def _cache(tmp_path):
    return CachePlanos(
        caminho_cache=str(tmp_path / "cache.json"),
        caminho_tempos=str(tmp_path / "tempos.json"),
    )


def test_obter_miss_retorna_none(tmp_path):
    c = _cache(tmp_path)
    assert c.obter("inexistente") is None


def test_guardar_e_obter(tmp_path):
    c = _cache(tmp_path)
    resultado = {"solucoes": [{"resumo": {"n_mapas": 3}}]}
    c.guardar("sig1", resultado, tempo_s=12.5)
    assert c.obter("sig1") == resultado


def test_persiste_entre_instancias(tmp_path):
    c1 = _cache(tmp_path)
    c1.guardar("sig1", {"ok": True}, tempo_s=3.0)
    # Nova instancia le do disco
    c2 = _cache(tmp_path)
    assert c2.obter("sig1") == {"ok": True}


# ---------------------------------------------------------------------------
# Aprendizado de tempos -- ETA que melhora com o uso
# ---------------------------------------------------------------------------

def test_estimar_tempo_sem_dados_retorna_none(tmp_path):
    c = _cache(tmp_path)
    assert c.estimar_tempo("grupo:2refs:5cores") is None


def test_estimar_tempo_usa_mediana(tmp_path):
    c = _cache(tmp_path)
    for t in [10.0, 20.0, 30.0]:
        c.registrar_tempo("k", t)
    assert c.estimar_tempo("k") == 20.0


def test_registrar_tempo_persiste_entre_instancias(tmp_path):
    c1 = _cache(tmp_path)
    c1.registrar_tempo("k", 7.0)
    c2 = _cache(tmp_path)
    assert c2.estimar_tempo("k") == 7.0


def test_registrar_tempo_janela_rolante(tmp_path):
    # Mantem apenas as ultimas N medicoes (evita arquivo crescer infinito
    # e faz a estimativa refletir o comportamento recente da maquina).
    c = CachePlanos(
        caminho_cache=str(tmp_path / "cache.json"),
        caminho_tempos=str(tmp_path / "tempos.json"),
        max_tempos=3,
    )
    for t in [100.0, 100.0, 100.0, 1.0, 1.0, 1.0]:
        c.registrar_tempo("k", t)
    # So as ultimas 3 (todas 1.0) devem contar
    assert c.estimar_tempo("k") == 1.0


def test_chaves_de_tempo_sao_independentes(tmp_path):
    c = _cache(tmp_path)
    c.registrar_tempo("grupo:2", 50.0)
    c.registrar_tempo("indiv", 5.0)
    assert c.estimar_tempo("grupo:2") == 50.0
    assert c.estimar_tempo("indiv") == 5.0


def test_estimativas_retorna_medianas_de_todas_as_chaves(tmp_path):
    c = _cache(tmp_path)
    c.registrar_tempo("grupo:2", 10.0)
    c.registrar_tempo("grupo:2", 30.0)   # mediana 20.0
    c.registrar_tempo("indiv", 4.0)
    assert c.estimativas() == {"grupo:2": 20.0, "indiv": 4.0}


def test_estimativas_vazio_sem_dados(tmp_path):
    c = _cache(tmp_path)
    assert c.estimativas() == {}
