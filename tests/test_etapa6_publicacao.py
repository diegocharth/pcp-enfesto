"""Etapa 6, grupo B (seguranca da publicacao):
- B4: o release so publica com a suite de testes verde;
- B5: biblioteca faltando na maquina (numpy, pdfplumber, openpyxl) vira aviso
  na tela em vez de o sistema perder recurso em silencio."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)


def _yml(nome):
    return open(os.path.join(RAIZ, ".github", "workflows", nome), encoding="utf-8").read()


def test_b4_release_roda_os_testes_antes_de_publicar():
    y = _yml("release.yml")
    i_teste = y.find("pytest")
    i_zip = y.find("make_release_zip.py")
    i_rel = y.find("gh release create")
    assert i_teste > 0, "release.yml nao roda os testes"
    assert i_teste < i_zip < i_rel, "os testes precisam vir antes do zip e da release"
    assert "requirements.txt" in y


def test_b4_testes_rodam_em_todo_ramo_enviado():
    y = _yml("testes.yml")
    assert "push" in y and "pytest" in y and "requirements.txt" in y


def test_b5_servidor_lista_bibliotecas_faltando(monkeypatch):
    import importlib.util
    import main
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda n, *a, **k: None if n == "numpy" else real(n, *a, **k))
    assert main._libs_faltando() == ["numpy"]
    monkeypatch.setattr(importlib.util, "find_spec", real)
    assert main._libs_faltando() == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_b5_tela_explica_o_que_falta_e_como_instalar():
    html = open(os.path.join(RAIZ, "interface.html"), encoding="utf-8").read()
    m = re.search(r"\n(function _avisoBibliotecas\(.*?\n})\r?\n", html, flags=re.S)
    assert m, "funcao _avisoBibliotecas nao encontrada"
    assert all(ord(c) < 128 for c in m.group(1))
    cod = m.group(1) + r'''
console.log(JSON.stringify({um: _avisoBibliotecas(['numpy']), nada: _avisoBibliotecas([])}));'''
    out = subprocess.run(["node", "-e", cod], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert "numpy" in r["um"] and "INSTALAR.bat" in r["um"] and "multi-ref" in r["um"]
    assert r["nada"] == ""
    assert "_avisoBibliotecas(" in html.split("window.onload")[1][:1500]


def test_versao_do_main_igual_ao_arquivo_version():
    import main
    versao = open(os.path.join(RAIZ, "VERSION"), encoding="utf-8").read().strip()
    assert main.VERSION == versao


def test_release_so_publica_da_main_e_zip_sem_cache_do_pytest():
    y = _yml("release.yml")
    assert "refs/heads/main" in y
    assert "no:cacheprovider" in y and "no:cacheprovider" in _yml("testes.yml")
    z = open(os.path.join(RAIZ, "tools", "make_release_zip.py"), encoding="utf-8").read()
    assert ".pytest_cache" in z
