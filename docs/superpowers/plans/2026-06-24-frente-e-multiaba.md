# Frente E — Multi-aba com Fila — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir abrir várias abas do sistema e calcular sem que o progresso de uma vaze para a outra, com um aviso "na fila" quando um cálculo espera outro — mantendo a confiabilidade (o `_calc_lock` continua serializando os cálculos).

**Architecture:** Progresso por **job** em vez de uma fila global única. Cada aba (page load) gera um `JOB_ID` e o envia em todo POST de cálculo e em todo poll de `/progresso`. O backend guarda `{job_id: [msgs]}`. O `_calc_lock` permanece (serializa = seguro); um `acquire(blocking=False)` falho injeta "na fila" no job antes de bloquear. O refactor do estado global do solver (F-1) NÃO está aqui — fica na Frente F; o lock garante a segurança enquanto isso.

**Tech Stack:** Python 3.10+ stdlib (http.server, threading), HTML/JS vanilla.

**Pré-requisitos / ordem:**
- Branch `frente-e-multiaba` (a partir de `main`, que já tem A+B+C+D).
- Baseline: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/ -q` → **99 passam**.
- **Encoding:** novo código em `interface.html` 100% ASCII.
- Linhas conferidas em 2026-06-24 (pós A-D); reconferir lendo.
- Ordem: E-T1 (backend) → E-T2 (frontend).

---

## File Structure

| Arquivo | Mudança |
|---|---|
| `main.py` | `_progressos = {}` (job→msgs) substitui `_progresso_fila`; helpers `_add_progresso(job_id,msg)`/`_drain_job`/`_reset_job` (+ GC); `/progresso?job=ID`; `_calcular`/`_calcular_grupo` usam job_id, resetam o job, e adquirem o lock non-blocking com aviso "na fila". |
| `tests/test_progresso_job.py` (novo) | isolamento do progresso entre 2 jobs. |
| `interface.html` | `const JOB_ID`; `job_id` em `baseParams` e no `payload` single; 3 polls `/progresso?job=`. |

---

## Task E-T1: Backend — progresso por job + fila

**Files:**
- Modify: `main.py` (globals ~199-210; `/progresso` ~253-257; `_calcular` ~365-387; `_calcular_grupo` ~531-549)
- Test: `tests/test_progresso_job.py` (criar)

- [ ] **Step 1: Write the failing test.** Create `tests/test_progresso_job.py`:

```python
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
    # drenado uma vez, esvazia
    assert main._drain_job("A") == []


def test_drain_job_desconhecido_nao_quebra():
    assert main._drain_job("inexistente-xyz") == []


def test_gc_limita_numero_de_jobs():
    for i in range(main._PROGRESSO_MAX_JOBS + 10):
        main._reset_job(f"job{i}")
    assert len(main._progressos) <= main._PROGRESSO_MAX_JOBS
```

(`import main` runs `_importar()` + builds `_CACHE` at module load — heavy but works since deps are installed; the server is only started in `main()`, not on import.)

- [ ] **Step 2: Run to verify it fails.** `python -m pytest tests/test_progresso_job.py -v` → FAIL (`_reset_job`/`_drain_job`/`_PROGRESSO_MAX_JOBS` don't exist; `_add_progresso` has the old 1-arg signature).

- [ ] **Step 3: Replace the globals + helpers.** In `main.py`, replace lines 198-210 (the `_progresso_fila`/`_add_progresso` block; KEEP the `_calc_lock` block at 202-206 intact):

```python
# Progresso por job: cada aba (page load) tem seu JOB_ID; mensagens nao se misturam.
_progressos = {}                 # job_id -> list[str]
_progresso_lock = threading.Lock()
_PROGRESSO_MAX_JOBS = 50          # teto p/ nao crescer sem limite (GC simples)

# Serializa cálculos: o solver usa estado global compartilhado (mapas históricos
# injetados + atributos de retomada na função resolver). ThreadingHTTPServer atende
# requisições concorrentes, então sem este lock dois cálculos simultâneos corromperiam
# o estado um do outro. Mantido durante todo o cálculo (single-user desktop).
_calc_lock = threading.Lock()

def _reset_job(job_id):
    with _progresso_lock:
        _progressos[job_id] = []
        if len(_progressos) > _PROGRESSO_MAX_JOBS:
            for k in list(_progressos.keys())[:-_PROGRESSO_MAX_JOBS]:
                _progressos.pop(k, None)

def _add_progresso(job_id, msg):
    with _progresso_lock:
        _progressos.setdefault(job_id, []).append(msg)

def _drain_job(job_id):
    with _progresso_lock:
        msgs = _progressos.get(job_id, [])
        _progressos[job_id] = []
        return msgs
```

- [ ] **Step 4: `/progresso?job=ID` route.** Replace the `/progresso` branch (lines ~253-257):

```python
        elif path == "/progresso":
            from urllib.parse import parse_qs
            job = (parse_qs(urlparse(self.path).query).get("job") or [""])[0]
            self._send(200, {"msgs": _drain_job(job) if job else []})
```

- [ ] **Step 5: `_calcular` — use job_id, reset, non-blocking lock.**
  - Near the start of `_calcular` (after `referencia`/`timeout`/`skip_combos` are read, e.g. right after `min_n_mapas`/`skip_combos`), add: `job_id = p.get("job_id", "default")`.
  - Replace the global clear (lines ~365-366):
    ```python
        with _progresso_lock:
            _progresso_fila.clear()
    ```
    with:
    ```python
        _reset_job(job_id)
    ```
  - Update `cb` (lines ~369-371):
    ```python
        def cb(msg):
            logs.append(msg)
            _add_progresso(job_id, msg)
    ```
  - Replace the `with _calc_lock:` block (lines ~376-386) with a non-blocking acquire + try/finally (preserving the inner historicos try/finally and the attr reads):
    ```python
        if not _calc_lock.acquire(blocking=False):
            _add_progresso(job_id, "Aguardando outro calculo terminar (na fila)...")
            _calc_lock.acquire()
        try:
            _mapas_mod._mapas_historicos_injetar = historicos
            try:
                solucoes = resolver(grade, tamanhos, limites, cfg,
                                    callback_progresso=cb, timeout_s=timeout,
                                    min_n_mapas=min_n_mapas, skip_combos=skip_combos)
            finally:
                _mapas_mod._mapas_historicos_injetar = []  # sempre limpar após uso
            r_niveis = getattr(resolver, '_niveis_esgotados', [])
            r_prox   = getattr(resolver, '_proximo_n', 1)
            r_skip   = getattr(resolver, '_skip_combos', 0)
        finally:
            _calc_lock.release()
    ```

- [ ] **Step 6: `_calcular_grupo` — same pattern.**
  - Add `job_id = p.get("job_id", "default")` near the start (after `referencia`/`regras` are read).
  - Replace the clear (lines ~531-532) with `_reset_job(job_id)`.
  - Update `cb` (lines ~535-537): `_add_progresso(job_id, msg)`.
  - Replace the `with _calc_lock:` block (lines ~542-548) with:
    ```python
        if not _calc_lock.acquire(blocking=False):
            _add_progresso(job_id, "Aguardando outro calculo terminar (na fila)...")
            _calc_lock.acquire()
        try:
            solucoes = resolver_multiref(refs_data, tamanhos, cfg,
                                         callback=cb, timeout_s=timeout,
                                         n_mapas_max=n_mapas_max)
            _convergiu = getattr(resolver_multiref, '_convergiu', True)
        finally:
            _calc_lock.release()
    ```

- [ ] **Step 7: Run tests + full suite.** `python -m pytest tests/test_progresso_job.py -v` → 3 PASS. `python -m pytest tests/ -q` → 102 passed (99 + 3). Confirm `grep -n "_progresso_fila" main.py` → ZERO.

- [ ] **Step 8: Commit.**
```bash
git add main.py tests/test_progresso_job.py
git commit -m "feat(server): progresso por job + aviso 'na fila' (multi-aba seguro)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task E-T2: Frontend — JOB_ID por aba

**Files:**
- Modify: `interface.html` (`const JOB_ID`; `baseParams` ~987; `payload` single ~1175; 3 polls `/progresso` em ~881, ~1145, ~1201)

Sem teste JS — verificação manual + revisão. ASCII.

- [ ] **Step 1: Add the per-tab JOB_ID.** Immediately BEFORE `async function _drainProgresso()` (~line 880), insert:

```javascript
// E1: id unico por aba (page load) -> progresso por job, sem misturar entre abas.
var JOB_ID = (function(){
  try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g,'').slice(0,12); } catch(e){}
  return 'j' + Date.now().toString(36) + Math.floor(Math.random()*1e6).toString(36);
})();
```

- [ ] **Step 2: Thread JOB_ID into the calc payloads.**
  - `baseParams` (~line 987) — append `job_id:JOB_ID` to the object (it is spread into both `/calcular` and `/calcular_grupo` multi-ref payloads, lines ~1023 and ~1077, so this one edit covers both):
    ```javascript
    const baseParams={mesa,max_folhas,num_opcoes,tol_abs,tol_pct,criterio,timeout,tamanhos,regras_especiais:regras,job_id:JOB_ID};
    ```
    (Read the actual line — after D-T2 it no longer has `peso_enc,peso_op`; just add `job_id:JOB_ID` before the closing `}`.)
  - Single `payload` (~line 1175) — append `job_id:JOB_ID` to the object:
    ```javascript
    const payload={referencia,consumo,mesa,max_folhas,num_opcoes,tol_abs,tol_pct,criterio,timeout,tamanhos,grade,regras_especiais:regras,min_n_mapas:1,skip_combos:0,job_id:JOB_ID};
    ```
    (Read the actual line and add `job_id:JOB_ID` before the closing `}`. `continuarBusca` reuses this `payload`, so it inherits job_id.)

- [ ] **Step 3: Thread JOB_ID into the 3 `/progresso` polls.** Change each `fetch('/progresso')` to `fetch('/progresso?job='+JOB_ID)`:
  - In `_drainProgresso` (~line 881): `const d=await(await fetch('/progresso?job='+JOB_ID)).json();`
  - In the `continuarBusca` setInterval (~line 1145): `const d=await(await fetch('/progresso?job='+JOB_ID)).json();`
  - In the main-calc setInterval (~line 1201): `const d=await(await fetch('/progresso?job='+JOB_ID)).json();`
  (Use grep `fetch('/progresso')` to find all occurrences and update every one.)

- [ ] **Step 4: Verify.**
  - `grep -n "fetch('/progresso')" interface.html` → ZERO (all now have `?job=`).
  - New code 100% ASCII; JS braces/parens balanced.
  - `python -m pytest tests/ -q` → 102 passed (Python unaffected).
  - Manual (maintainer): open the app in TWO tabs. Start a calc in tab 1; while it runs, start a calc in tab 2 → tab 2 shows "Aguardando outro calculo terminar (na fila)..." and then its own progress when tab 1 finishes; the two progress logs do NOT mix.

- [ ] **Step 5: Commit.**
```bash
git add interface.html
git commit -m "feat(ui): JOB_ID por aba (progresso isolado entre abas)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente E
- [ ] `python -m pytest tests/ -q` → 102 passed.
- [ ] Manual: 2 abas — progresso isolado + "na fila"; cálculo continua serializado (confiável).
- [ ] Merge `frente-e-multiaba` → `main` (ff) + remover branch.

## Self-Review (autor do plano)
- **Cobertura do spec (Frente E):** E1 progresso por job + fila ✓. F-1 (estado global) explicitamente fora — vai na Frente F (o lock cobre a segurança nesse meio-tempo).
- **Sem placeholders:** código completo; old/new exatos (reconferir linhas em interface.html, que drift com A/B/C/D).
- **Consistência:** `JOB_ID` (E-T2) casa com `job_id` lido em `_calcular`/`_calcular_grupo` (E-T1) e com `/progresso?job=` ↔ `_drain_job`. `baseParams` cobre os 2 fetches multi-ref; `payload` cobre single+continuar. `_add_progresso` muda de 1 para 2 args — só os 2 `cb` e a rota usam (cobertos).
- **Risco:** baixo — o `_calc_lock` permanece (serialização/segurança intactas); a mudança é de roteamento de progresso. O `acquire(blocking=False)+try/finally` substitui o `with _calc_lock` preservando o try/finally interno dos históricos.
