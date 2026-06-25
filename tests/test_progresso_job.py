"""E1: progresso por job — mensagens de jobs distintos nao se misturam, e
o drain esvazia apenas o job pedido."""
import importlib
main = importlib.import_module("main")


def test_progresso_isolado_por_job():
    main._reset_job("A")
    main._reset_job("B")
    main._add_progresso("A", "msg-a1")
    main._add_progresso("B", "msg-b1")
    main._add_progresso("A", "msg-a2")
    assert main._drain_job("A") == ["msg-a1", "msg-a2"]
    assert main._drain_job("B") == ["msg-b1"]
    assert main._drain_job("A") == []


def test_drain_job_desconhecido_nao_quebra():
    assert main._drain_job("inexistente-xyz") == []


def test_gc_limita_numero_de_jobs():
    for i in range(main._PROGRESSO_MAX_JOBS + 10):
        main._reset_job(f"job{i}")
    assert len(main._progressos) <= main._PROGRESSO_MAX_JOBS
