"""F: escrita atomica + validacao de entrada."""
import json, os, importlib
main = importlib.import_module("main")


def test_salvar_json_atomico_grava_e_le(tmp_path):
    alvo = os.path.join(tmp_path, "x.json")
    main._salvar_json_atomico(alvo, {"a": 1, "b": [2, 3]})
    with open(alvo, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1, "b": [2, 3]}
    assert not os.path.exists(alvo + ".tmp")


def test_num_coercao_com_default():
    assert main._num({"a": "5"}, "a", 1, int) == 5
    assert main._num({"a": "x"}, "a", 7, int) == 7
    assert main._num({}, "a", 9, int) == 9
    assert main._num({"a": "2.5"}, "a", 1.0, float) == 2.5


def test_update_rejeita_url_nao_https():
    import importlib
    upd = importlib.import_module("updater")
    ok, msg = upd.baixar_e_aplicar("http://exemplo.com/app.zip", "9.9.9")
    assert ok is False
    assert "https" in msg.lower()
