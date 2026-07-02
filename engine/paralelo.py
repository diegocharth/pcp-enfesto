"""
PCP Enfestos — Pool de processos para os solves
===============================================

Os solves sao CPU-bound e o GIL do Python impede que threads rodem calculo em
paralelo de verdade. Este modulo mantem um ProcessPoolExecutor compartilhado:
cada /calcular ou /calcular_grupo roda num PROCESSO worker separado, entao o
multi-ref consegue calcular varias referencias/grupos AO MESMO TEMPO (antes
era um por vez, serializado pelo _calc_lock).

Prioridade de CPU: cada worker se marca com prioridade ACIMA DO NORMAL no
Windows (HIGH se config "prioridade_cpu": "alta"), como o Diego pediu — o
calculo ganha a CPU de outras atividades da maquina, sem travar a interface
(o servidor HTTP continua com prioridade normal e sempre sobra 1 nucleo).

Progresso: o callback nao atravessa processos; o worker publica as mensagens
numa fila do Manager e uma thread do servidor as drena para o progresso do
job (mesma UX de antes, agora com varios jobs simultaneos).
"""

import os
import queue
import threading
import multiprocessing as _mp
from concurrent.futures import ProcessPoolExecutor

_pool = None
_manager = None
_lock = threading.Lock()
_cfg = {"prioridade": "acima_normal", "max_workers": None}


def configurar(prioridade=None, max_workers=None):
    """Chamado 1x pelo main.py antes do primeiro solve (opcional)."""
    if prioridade:
        _cfg["prioridade"] = str(prioridade).lower()
    if max_workers:
        _cfg["max_workers"] = int(max_workers)


def n_workers():
    if _cfg["max_workers"]:
        return max(1, _cfg["max_workers"])
    cpu = os.cpu_count() or 4
    # deixa 1 nucleo para o servidor/S.O.; teto de 12 (41 jobs tipicos nao
    # precisam de mais e cada worker carrega numpy na memoria)
    return max(1, min(cpu - 1, 12))


def _aplicar_prioridade(alta=False):
    """Prioridade de processo no Windows; silencioso em outros S.O./falhas."""
    try:
        import ctypes
        ABOVE_NORMAL = 0x00008000
        HIGH = 0x00000080
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(h, HIGH if alta else ABOVE_NORMAL)
    except Exception:
        pass


def _init_worker(prioridade):
    _aplicar_prioridade(alta=(prioridade == "alta"))


def get_pool():
    global _pool
    with _lock:
        if _pool is None:
            ctx = _mp.get_context("spawn")
            _pool = ProcessPoolExecutor(
                max_workers=n_workers(), mp_context=ctx,
                initializer=_init_worker, initargs=(_cfg["prioridade"],))
        return _pool


def _get_manager():
    global _manager
    with _lock:
        if _manager is None:
            _manager = _mp.Manager()
        return _manager


def encerrar():
    """Best-effort no shutdown do servidor: cancela a fila e MATA os workers
    (senao um solve em andamento viraria processo orfao rodando por minutos)."""
    global _pool, _manager
    try:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
            for p in list(getattr(_pool, "_processes", {}).values()):
                try:
                    p.terminate()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        if _manager is not None:
            _manager.shutdown()
    except Exception:
        pass
    _pool = None
    _manager = None


def _reset_pool():
    """Descarta um pool quebrado (worker morto) para recriar no proximo uso."""
    global _pool
    with _lock:
        try:
            if _pool is not None:
                _pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        _pool = None


# ── Entrada executada DENTRO do worker (top-level: exigencia do spawn) ───────

def _solve_entry(tipo, kwargs, fila):
    def cb(msg):
        try:
            fila.put(msg)
        except Exception:
            pass
    resume = {}
    if tipo == "single":
        from engine.solver import resolver
        sols = resolver(callback_progresso=cb, resume_out=resume, **kwargs)
    else:
        from engine.solver_multiref import resolver_multiref
        sols = resolver_multiref(callback=cb, resume_out=resume, **kwargs)
    return sols, resume


def _executar_uma_vez(tipo, kwargs, progress_cb):
    pool = get_pool()
    fila = _get_manager().Queue()
    fut = pool.submit(_solve_entry, tipo, kwargs, fila)
    while True:
        try:
            msg = fila.get(timeout=0.25)
            progress_cb(msg)
        except queue.Empty:
            if fut.done():
                break
        except (EOFError, BrokenPipeError):
            break
    while True:
        try:
            progress_cb(fila.get_nowait())
        except Exception:
            break
    return fut.result()


def executar_solve(tipo, kwargs, progress_cb):
    """Roda um solve num worker, drenando o progresso em tempo real.

    tipo: "single" (engine.solver.resolver) ou "multiref"
    kwargs: argumentos nomeados do solver (sem callback/resume_out)
    progress_cb: recebe cada mensagem de progresso na thread chamadora
    Retorna (solucoes, resume_info). Excecoes do worker sobem para o chamador.

    Se o pool quebrou (worker morto, ex.: kill externo), recria o pool e tenta
    UMA vez de novo — senao todo calculo futuro morreria ate reiniciar o app.
    """
    from concurrent.futures.process import BrokenProcessPool
    try:
        return _executar_uma_vez(tipo, kwargs, progress_cb)
    except BrokenProcessPool:
        progress_cb("Pool de calculo quebrou (worker morto) — recriando e tentando de novo...")
        _reset_pool()
        return _executar_uma_vez(tipo, kwargs, progress_cb)
