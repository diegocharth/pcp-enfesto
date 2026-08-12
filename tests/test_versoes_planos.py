"""
Testes do sistema de versoes/restauracao (versoes.py) e do plano de corte
portatil (engine/planos.py). Tudo roda em diretorios temporarios -- nunca toca
o codigo nem os dados reais.
"""
import sys, os, json, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import versoes
from engine import planos


# ---------------------------------------------------------------------------
# versoes.py
# ---------------------------------------------------------------------------

def _base_fake(tmp_path, versao="1.0.0"):
    base = str(tmp_path)
    os.makedirs(os.path.join(base, "engine"), exist_ok=True)
    with open(os.path.join(base, "VERSION"), "w") as f:
        f.write(versao)
    with open(os.path.join(base, "main.py"), "w") as f:
        f.write(f"# codigo {versao}")
    with open(os.path.join(base, "engine", "solver.py"), "w") as f:
        f.write("# solver")
    with open(os.path.join(base, "config.json"), "w") as f:
        json.dump({"auto_update": True, "github_repo": "x/y"}, f)
    os.makedirs(os.path.join(base, "dados"), exist_ok=True)
    with open(os.path.join(base, "dados", "cores_salvas.json"), "w") as f:
        json.dump(["AZUL"], f)
    return base


def test_snapshot_cria_e_e_idempotente(tmp_path):
    base = _base_fake(tmp_path)
    criado, cam = versoes.criar_snapshot("teste", base_dir=base)
    assert criado and os.path.exists(cam)
    criado2, cam2 = versoes.criar_snapshot("de novo", base_dir=base)
    assert not criado2 and cam2 == cam


def test_snapshot_exclui_dados_e_pycache(tmp_path):
    base = _base_fake(tmp_path)
    os.makedirs(os.path.join(base, "__pycache__"))
    with open(os.path.join(base, "__pycache__", "x.pyc"), "w") as f:
        f.write("x")
    _, cam = versoes.criar_snapshot(base_dir=base)
    with zipfile.ZipFile(cam) as zf:
        nomes = zf.namelist()
    assert not any(n.startswith("dados") for n in nomes)
    assert not any("__pycache__" in n for n in nomes)
    assert "main.py" in nomes and "VERSION" in nomes


def test_listar_versoes_ordenado(tmp_path):
    base = _base_fake(tmp_path, "1.0.0")
    versoes.criar_snapshot(base_dir=base)
    with open(os.path.join(base, "VERSION"), "w") as f:
        f.write("1.2.0")
    versoes.criar_snapshot(base_dir=base)
    with open(os.path.join(base, "VERSION"), "w") as f:
        f.write("1.10.0")
    versoes.criar_snapshot(base_dir=base)
    lst = versoes.listar_versoes(base_dir=base)
    assert [v["versao"] for v in lst] == ["1.10.0", "1.2.0", "1.0.0"]
    assert lst[0]["atual"] is True


def test_restauracao_ciclo_completo(tmp_path):
    base = _base_fake(tmp_path, "1.0.0")
    versoes.criar_snapshot(base_dir=base)

    # evolui para 2.0.0 com codigo e dados novos
    with open(os.path.join(base, "VERSION"), "w") as f:
        f.write("2.0.0")
    with open(os.path.join(base, "main.py"), "w") as f:
        f.write("# codigo 2.0.0")
    with open(os.path.join(base, "dados", "cores_salvas.json"), "w") as f:
        json.dump(["AZUL", "ROSA"], f)

    versoes.sinalizar_restauracao("1.0.0", base_dir=base)
    assert versoes.restauracao_pendente(base_dir=base)["versao"] == "1.0.0"

    ok, msg = versoes.aplicar_restauracao_pendente(base_dir=base)
    assert ok, msg
    # codigo voltou
    assert open(os.path.join(base, "main.py")).read() == "# codigo 1.0.0"
    assert open(os.path.join(base, "VERSION")).read().strip() == "1.0.0"
    # dados do usuario NAO voltaram (preservados)
    assert json.load(open(os.path.join(base, "dados", "cores_salvas.json"))) == ["AZUL", "ROSA"]
    # config preservado, mas auto_update desligado (senao a proxima abertura
    # desfaria a restauracao)
    cfg = json.load(open(os.path.join(base, "config.json")))
    assert cfg["auto_update"] is False
    assert cfg["github_repo"] == "x/y"
    assert versoes.update_pausado(base_dir=base) is not None
    # a versao 2.0.0 tambem ganhou snapshot antes de sair (da para ir e voltar)
    assert "2.0.0" in [v["versao"] for v in versoes.listar_versoes(base_dir=base)]
    # pendencia limpa
    assert versoes.restauracao_pendente(base_dir=base) is None


def test_reativar_auto_update(tmp_path):
    base = _base_fake(tmp_path, "1.0.0")
    versoes._pausar_auto_update("1.0.0", base_dir=base)
    assert versoes.update_pausado(base_dir=base) is not None
    versoes.reativar_auto_update(base_dir=base)
    assert versoes.update_pausado(base_dir=base) is None
    assert json.load(open(os.path.join(base, "config.json")))["auto_update"] is True


def test_sinalizar_restauracao_versao_inexistente(tmp_path):
    base = _base_fake(tmp_path)
    with pytest.raises(ValueError):
        versoes.sinalizar_restauracao("9.9.9", base_dir=base)


# ---------------------------------------------------------------------------
# engine/planos.py
# ---------------------------------------------------------------------------

PLANO_OK = {
    "mapas": [{"id": 1, "composicao": {"P": 2}, "n_pecas": 2, "comp_camada_m": 2.13}],
    "camadas": {"AZUL": {"1": 10}},
    "consumo_peca": 1.06,
}


def test_plano_salvar_listar_carregar(tmp_path):
    pasta = str(tmp_path)
    cam = planos.salvar_plano(PLANO_OK, "VESTIDO X", pasta, versao_app="2.13.0",
                              origem="single")
    assert cam.endswith(".plano.json")
    lst = planos.listar_planos(pasta)
    assert len(lst) == 1
    assert lst[0]["referencia"] == "VESTIDO X"
    assert lst[0]["cores"] == ["AZUL"]
    doc = planos.carregar_plano(pasta, lst[0]["nome"])
    assert doc["plano"]["camadas"] == {"AZUL": {1: 10}}
    assert doc["plano"]["consumo_peca"] == 1.06
    assert doc["formato"] == planos.FORMATO


def test_plano_validacao_rejeita_invalidos():
    with pytest.raises(ValueError):
        planos.validar_plano({})
    with pytest.raises(ValueError):
        planos.validar_plano({"mapas": [], "camadas": {"A": {"1": 1}}, "consumo_peca": 1})
    with pytest.raises(ValueError):
        planos.validar_plano({**PLANO_OK, "consumo_peca": 0})
    with pytest.raises(ValueError):
        # camada referencia mapa inexistente
        planos.validar_plano({**PLANO_OK, "camadas": {"AZUL": {"7": 5}}})


def test_plano_path_traversal_bloqueado(tmp_path):
    with pytest.raises(ValueError):
        planos.carregar_plano(str(tmp_path), "../../x.plano.json")
    with pytest.raises(ValueError):
        planos.carregar_plano(str(tmp_path), "arquivo.txt")


def test_plano_formato_desconhecido_rejeitado():
    with pytest.raises(ValueError):
        planos.parsear_plano_json(json.dumps({"formato": "outro", "plano": PLANO_OK}))
    with pytest.raises(ValueError):
        planos.parsear_plano_json("nao e json {")


def test_snapshot_exclui_config_json(tmp_path):
    """config.json tem segredo (api key) e nao pode entrar no snapshot."""
    base = _base_fake(tmp_path)
    _, cam = versoes.criar_snapshot(base_dir=base)
    with zipfile.ZipFile(cam) as zf:
        assert "config.json" not in zf.namelist()


def test_sinalizar_restauracao_rejeita_traversal(tmp_path):
    base = _base_fake(tmp_path)
    for ruim in ("../../evil", "..\evil", "a/b", ""):
        with pytest.raises(ValueError):
            versoes.sinalizar_restauracao(ruim, base_dir=base)


def test_restauracao_invalida_update_pendente(tmp_path):
    """Um update agendado ANTES da restauracao nao pode desfaze-la depois."""
    base = _base_fake(tmp_path, "1.0.0")
    versoes.criar_snapshot(base_dir=base)
    with open(os.path.join(base, "VERSION"), "w") as f:
        f.write("2.0.0")
    # update pendente obsoleto
    pend = os.path.join(base, "dados", "_update_pendente")
    os.makedirs(pend)
    with open(os.path.join(pend, "info.json"), "w") as f:
        json.dump({"asset_url": "https://x/y.zip", "versao_nova": "3.0.0"}, f)
    versoes.sinalizar_restauracao("1.0.0", base_dir=base)
    ok, _ = versoes.aplicar_restauracao_pendente(base_dir=base)
    assert ok
    assert not os.path.exists(pend)


def test_falha_na_extracao_cancela_pendente(tmp_path):
    """Snapshot corrompido: nada muda e a pendencia e limpa (nao repete a cada boot)."""
    base = _base_fake(tmp_path, "1.0.0")
    versoes.criar_snapshot(base_dir=base)
    with open(os.path.join(base, "VERSION"), "w") as f:
        f.write("2.0.0")
    versoes.sinalizar_restauracao("1.0.0", base_dir=base)
    # corrompe o zip DEPOIS de sinalizar
    with open(versoes._caminho_snapshot("1.0.0", base), "wb") as f:
        f.write(b"nao e zip")
    ok, msg = versoes.aplicar_restauracao_pendente(base_dir=base)
    assert not ok
    assert versoes.restauracao_pendente(base_dir=base) is None
    assert open(os.path.join(base, "VERSION")).read().strip() == "2.0.0"
