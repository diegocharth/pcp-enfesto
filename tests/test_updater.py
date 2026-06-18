"""
Testes do modulo updater.py
"""
import sys, os, json, zipfile, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from updater import _comparar_versoes, _e_caminho_preservado, rollback


# ---------------------------------------------------------------------------
# 1. Comparacao semantica de versoes
# ---------------------------------------------------------------------------

def test_versao_patch_maior():
    assert _comparar_versoes("2.8.0", "2.8.1") is True


def test_versao_minor_maior():
    assert _comparar_versoes("2.8.0", "2.9.0") is True


def test_versao_major_maior():
    assert _comparar_versoes("2.8.0", "3.0.0") is True


def test_versao_com_prefixo_v():
    assert _comparar_versoes("2.8.0", "v2.8.1") is True


def test_versao_igual():
    assert _comparar_versoes("2.8.0", "2.8.0") is False


def test_versao_menor():
    assert _comparar_versoes("2.9.0", "2.8.5") is False


def test_versao_minor_dois_digitos():
    """2.9.0 < 2.10.0 (nao e comparacao lexicografica)."""
    assert _comparar_versoes("2.9.0", "2.10.0") is True


def test_versao_patch_dois_digitos():
    assert _comparar_versoes("2.8.9", "2.8.10") is True


# ---------------------------------------------------------------------------
# 2. Caminhos preservados
# ---------------------------------------------------------------------------

def test_preservar_config():
    assert _e_caminho_preservado("config.json") is True


def test_preservar_dados_dir():
    assert _e_caminho_preservado("dados/alguma_coisa.json") is True


def test_preservar_mapa_cores():
    assert _e_caminho_preservado("dados/mapa_cores.json") is True


def test_nao_preservar_main():
    assert _e_caminho_preservado("main.py") is False


def test_nao_preservar_engine():
    assert _e_caminho_preservado("engine/solver.py") is False


# ---------------------------------------------------------------------------
# 3. Preservacao de config/dados na aplicacao simulada
# ---------------------------------------------------------------------------

def test_preservacao_config_e_dados(tmp_path, monkeypatch):
    """
    Simula um update: cria um zip com novos arquivos + config alterado.
    Verifica que config.json e dados/ originais sao preservados.
    """
    import updater

    # Cria estrutura simulada do app
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    dados_dir = app_dir / "dados"
    dados_dir.mkdir()

    # Arquivo VERSION e config originais
    (app_dir / "VERSION").write_text("2.8.0\n")
    config_original = {"mesa_comprimento_m": 12.5, "chave_secreta": "meu_valor"}
    (app_dir / "config.json").write_text(
        json.dumps(config_original), encoding="utf-8"
    )
    (dados_dir / "mapa_cores.json").write_text('{"PRETO": {"fornecedores": ["BLACK"]}}')
    (dados_dir / "cores_salvas.json").write_text('["PRETO", "BRANCO"]')

    # Cria zip de update com versoes alteradas
    zip_path = tmp_path / "update_2.8.1.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Mesmo prefixo que GitHub usa
        zf.writestr("pcp_enfestos-2.8.1/main.py", "# novo main.py v2.8.1")
        zf.writestr("pcp_enfestos-2.8.1/VERSION", "2.8.1\n")
        # Config no zip (deve ser IGNORADO -- preservar o original)
        zf.writestr("pcp_enfestos-2.8.1/config.json", '{"mesa_comprimento_m": 999}')
        # dados/mapa_cores.json no zip (deve ser IGNORADO)
        zf.writestr("pcp_enfestos-2.8.1/dados/mapa_cores.json", '{}')

    # Monkeypatcha BASE_DIR para apontar para app_dir
    monkeypatch.setattr(updater, "BASE_DIR", str(app_dir))
    monkeypatch.setattr(updater, "VERSION_FILE", str(app_dir / "VERSION"))
    monkeypatch.setattr(updater, "DADOS_DIR", str(dados_dir))
    monkeypatch.setattr(updater, "BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setattr(updater, "PENDENTE_DIR", str(tmp_path / "pendente"))

    # Aplica o update via baixar_e_aplicar usando o zip local (sem download)
    # Usa um asset_url ficticio mas intercepta o download
    def fake_retrieve(url, destino):
        shutil.copy(str(zip_path), destino)

    monkeypatch.setattr(updater.urllib.request, "urlretrieve", fake_retrieve)

    ok, msg = updater.baixar_e_aplicar(
        asset_url="https://fake/update.zip",
        versao_nova="2.8.1",
    )
    assert ok is True, f"Update falhou: {msg}"

    # VERSION deve ter sido atualizado
    versao_final = (app_dir / "VERSION").read_text().strip()
    assert versao_final == "2.8.1"

    # config.json DEVE ser o original (nao sobrescrito)
    config_final = json.loads((app_dir / "config.json").read_text(encoding="utf-8"))
    assert config_final["mesa_comprimento_m"] == 12.5, "config.json foi sobrescrito!"
    assert config_final.get("chave_secreta") == "meu_valor"

    # dados/mapa_cores.json DEVE ser o original
    mapa_final = json.loads((dados_dir / "mapa_cores.json").read_text())
    assert "PRETO" in mapa_final, "mapa_cores.json foi sobrescrito!"

    # main.py deve ter sido atualizado
    main_final = (app_dir / "main.py").read_text()
    assert "v2.8.1" in main_final


# ---------------------------------------------------------------------------
# 4. Rollback quando backup disponivel
# ---------------------------------------------------------------------------

def test_rollback_sem_backup(tmp_path, monkeypatch):
    import updater
    monkeypatch.setattr(updater, "BACKUP_DIR", str(tmp_path / "backup_inexistente"))
    ok, msg = rollback()
    assert ok is False
    assert "Sem backup" in msg
