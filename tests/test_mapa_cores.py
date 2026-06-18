"""
Testes do modulo engine/import_rolos/mapa_cores.py
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.import_rolos.mapa_cores import (
    resolver_cor,
    adicionar_mapeamento,
    aplicar_mapa,
    carregar_mapa,
    salvar_mapa,
)


@pytest.fixture
def mapa_tmp(tmp_path):
    """Arquivo temporario de mapa_cores.json com entradas iniciais."""
    caminho = str(tmp_path / "mapa_cores.json")
    dados = {
        "PRETO": {"fornecedores": ["BLACK", "PRETO TOTAL", "black-001"]},
        "OFFWHITE": {"fornecedores": ["27339A SILVER BIRCH", "BRANCO NEVE 23A"]},
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    return caminho


# ---------------------------------------------------------------------------
# 1. Resolucao de cor existente
# ---------------------------------------------------------------------------

def test_resolver_cor_exata(mapa_tmp):
    assert resolver_cor("BLACK", mapa_tmp) == "PRETO"


def test_resolver_cor_case_insensitive(mapa_tmp):
    """Busca deve ser case-insensitive."""
    assert resolver_cor("black", mapa_tmp) == "PRETO"
    assert resolver_cor("Black", mapa_tmp) == "PRETO"
    assert resolver_cor("27339a silver birch", mapa_tmp) == "OFFWHITE"


def test_resolver_cor_espacos_extras(mapa_tmp):
    """Espacos extras devem ser normalizados."""
    assert resolver_cor("  BLACK  ", mapa_tmp) == "PRETO"


def test_resolver_cor_nao_encontrada(mapa_tmp):
    assert resolver_cor("VERDE BANDEIRA", mapa_tmp) is None


# ---------------------------------------------------------------------------
# 2. Cadastro de novo mapeamento
# ---------------------------------------------------------------------------

def test_adicionar_mapeamento_novo(mapa_tmp):
    """Deve gravar o novo mapeamento e retornar True."""
    result = adicionar_mapeamento("AZUL ROYAL 07", "AZUL", mapa_tmp)
    assert result is True

    # Verifica persistencia
    mapa = carregar_mapa(mapa_tmp)
    assert "AZUL" in mapa
    assert "AZUL ROYAL 07" in mapa["AZUL"]["fornecedores"]


def test_adicionar_mapeamento_existente_identico(mapa_tmp):
    """Se mapeamento identico ja existe, retorna False (sem erro)."""
    result = adicionar_mapeamento("BLACK", "PRETO", mapa_tmp)
    assert result is False


def test_adicionar_mapeamento_nao_sobrescreve(mapa_tmp):
    """Se fornecedor ja mapeado para outro comercial, levanta ValueError."""
    with pytest.raises(ValueError, match="ja esta mapeada"):
        adicionar_mapeamento("BLACK", "CINZA", mapa_tmp)


def test_adicionar_mapeamento_cria_arquivo(tmp_path):
    """Se o arquivo nao existir, deve ser criado."""
    caminho = str(tmp_path / "novo_mapa.json")
    assert not os.path.exists(caminho)
    adicionar_mapeamento("VERMELHO TOMATE", "VERMELHO", caminho)
    assert os.path.exists(caminho)
    mapa = carregar_mapa(caminho)
    assert "VERMELHO" in mapa


# ---------------------------------------------------------------------------
# 3. Aplicacao do mapa a uma lista de registros
# ---------------------------------------------------------------------------

def test_aplicar_mapa_todos_reconhecidos(mapa_tmp):
    registros = [
        {"cor_fornecedor": "BLACK",               "comprimento_m": 50.0},
        {"cor_fornecedor": "27339A SILVER BIRCH", "comprimento_m": 30.0},
        {"cor_fornecedor": "PRETO TOTAL",         "comprimento_m": 45.0},
    ]
    rolos_por_cor, nao_rec = aplicar_mapa(registros, mapa_tmp)
    assert nao_rec == []
    assert set(rolos_por_cor.keys()) == {"PRETO", "OFFWHITE"}
    assert sorted(rolos_por_cor["PRETO"]) == sorted([50.0, 45.0])
    assert rolos_por_cor["OFFWHITE"] == [30.0]


def test_aplicar_mapa_cores_nao_reconhecidas(mapa_tmp):
    registros = [
        {"cor_fornecedor": "BLACK",      "comprimento_m": 50.0},
        {"cor_fornecedor": "VERDE LIMAO","comprimento_m": 20.0},
    ]
    rolos_por_cor, nao_rec = aplicar_mapa(registros, mapa_tmp)
    assert "VERDE LIMAO" in nao_rec
    assert "PRETO" in rolos_por_cor
    assert "VERDE LIMAO" not in rolos_por_cor


def test_aplicar_mapa_vazio(mapa_tmp):
    rolos_por_cor, nao_rec = aplicar_mapa([], mapa_tmp)
    assert rolos_por_cor == {}
    assert nao_rec == []


# ---------------------------------------------------------------------------
# 4. Persistencia: carregar/salvar
# ---------------------------------------------------------------------------

def test_persistencia_roundtrip(tmp_path):
    caminho = str(tmp_path / "mapa.json")
    mapa = {"AZUL": {"fornecedores": ["BLUE SKY", "AZUL ROYAL"]}}
    salvar_mapa(mapa, caminho)
    carregado = carregar_mapa(caminho)
    assert carregado == mapa


def test_carregar_arquivo_inexistente(tmp_path):
    caminho = str(tmp_path / "nao_existe.json")
    assert carregar_mapa(caminho) == {}
