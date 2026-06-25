"""Frente G: estoque persistente de pontas entre OPs."""
import importlib
main = importlib.import_module("main")


def _result(ponta, classe):
    return {"por_cor": {"AZUL": {"sobras_por_rolo": [
        {"rolo_indice": 1, "ponta_m": ponta, "ponta_classe": classe}
    ]}}}


def test_adicionar_so_pega_pontas_estoque():
    est, n = main._estoque_adicionar({}, _result(5.6, "estoque"), origem="OP1", agora="2026-06-25")
    assert n == 1
    assert "AZUL" in est and len(est["AZUL"]) == 1
    e = est["AZUL"][0]
    assert e["comprimento_m"] == 5.6 and e["origem"] == "OP1" and "id" in e


def test_adicionar_ignora_refugo():
    est, n = main._estoque_adicionar({}, _result(0.2, "refugo"), origem="OP1", agora="x")
    assert n == 0 and est == {}


def test_adicionar_acumula_sem_mutar_entrada():
    base = {"AZUL": [{"id": "a", "comprimento_m": 3.0, "origem": "old", "data": "d"}]}
    est, n = main._estoque_adicionar(base, _result(5.6, "estoque"), origem="OP2", agora="y")
    assert n == 1 and len(est["AZUL"]) == 2
    assert len(base["AZUL"]) == 1


def test_remover_por_id():
    est = {"AZUL": [{"id": "a", "comprimento_m": 3.0}, {"id": "b", "comprimento_m": 4.0}]}
    novo = main._estoque_remover(est, "AZUL", "a")
    assert [e["id"] for e in novo["AZUL"]] == ["b"]


def test_carregar_inexistente_retorna_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ESTOQUE_PONTAS_FILE", str(tmp_path / "nao_existe.json"))
    assert main.carregar_estoque_pontas() == {}
