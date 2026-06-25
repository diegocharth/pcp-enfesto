# Frente F — Confiabilidade & Robustez — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Endurecer o sistema para uso de fábrica: logs persistentes, escrita atômica dos dados, validação de entrada com erro amigável (sem stacktrace cru), e integridade no auto-update.

**Architecture:** Mudanças aditivas e localizadas, sem tocar o solver nem a alocação. Escopo: `main.py` (logging, escrita atômica, validação, esconder trace) e `updater.py` (integridade do download).

**Escopo / decisão sobre F-1:** O item **F-1 (refatorar o estado global do solver)** da auditoria está **fora desta frente** (recomendado adiar): o `_calc_lock` já serializa e protege esse estado (a Frente E manteve o lock), então F-1 é limpeza interna de alto risco (mexe no mecanismo de retomada "Continuar") e baixo benefício. Deve ser feito como tarefa focada própria, com a suíte de baseline do solver, não no fim de uma sessão longa.

**Tech Stack:** Python 3.10+ stdlib (logging, os.replace, hashlib opcional).

**Pré-requisitos / ordem:**
- Branch `frente-f-confiabilidade` (a partir de `main`, que já tem A+B+C+D+E).
- Baseline: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/ -q` → **102 passam**.
- Linhas conferidas em 2026-06-24 (pós A-E); reconferir lendo.
- Ordem: F-T1 (logs) → F-T2 (escrita atômica) → F-T3 (validação + esconder trace) → F-T4 (integridade do update).

---

## File Structure

| Arquivo | Mudança |
|---|---|
| `main.py` | F-T1 logger rotativo em `dados/logs/pcp.log`; F-T2 `_salvar_json_atomico` reusado por salvar_cores/params/historico; F-T3 helpers `_num`/coerção segura + `do_POST` loga trace e responde amigável. |
| `updater.py` | F-T4 exigir `https://` no `asset_url` antes de baixar (+ manter `is_zipfile`). |
| `tests/test_confiabilidade.py` (novo) | escrita atômica; coerção de entrada; rejeição de URL não-https. |

---

## Task F-T1: Logs persistentes

**Files:**
- Modify: `main.py` (perto dos imports/constantes do topo; usar nos pontos de erro)

Sem teste dedicado (efeito é I/O em arquivo de log) — verificação: o arquivo de log é criado e recebe entradas; suíte intacta.

- [ ] **Step 1: Add a rotating logger.** In `main.py`, after the existing imports and `BASE_DIR`/file constants (near the top, after the `*_FILE` constants ~line 53), add:

```python
import logging
from logging.handlers import RotatingFileHandler

def _setup_logger():
    log_dir = os.path.join(BASE_DIR, "dados", "logs")
    os.makedirs(log_dir, exist_ok=True)
    lg = logging.getLogger("pcp")
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    h = RotatingFileHandler(os.path.join(log_dir, "pcp.log"),
                            maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    lg.addHandler(h)
    return lg

_log = _setup_logger()
```

- [ ] **Step 2: Log calc start/end and the version on boot.** In `main()` (where it prints `PCP Enfestos v{VERSION}...`), add `_log.info("Servidor iniciado v%s porta %s", VERSION, porta)` near the print. In `_calcular`, after `job_id` is set, add `_log.info("calcular ref=%s job=%s", referencia, job_id)`; at the end (before the final `self._send`), add `_log.info("calcular OK ref=%s tempo=%.1fs", referencia, _elapsed)`. (Keep it light — a couple of info lines.)

- [ ] **Step 3: Verify + commit.**
  - `python -m pytest tests/ -q` → 102 passed (logger import must not break anything).
  - `python -c "import main; main._log.info('teste'); import os; print(os.path.exists(os.path.join(main.BASE_DIR,'dados','logs','pcp.log')))"` → prints `True`.
```
git add main.py
git commit -m "feat(server): logs persistentes rotativos em dados/logs/pcp.log

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task F-T2: Escrita atômica dos dados

**Files:**
- Modify: `main.py` (`salvar_cores_arquivo` ~116-120, `salvar_params` ~128-131, `salvar_historico` — busque a função; escreve direto hoje)
- Test: `tests/test_confiabilidade.py` (criar)

- [ ] **Step 1: Write the failing test.** Create `tests/test_confiabilidade.py`:

```python
"""F: escrita atomica + validacao + integridade do update."""
import json, os, importlib
main = importlib.import_module("main")


def test_salvar_json_atomico_grava_e_le(tmp_path):
    alvo = os.path.join(tmp_path, "x.json")
    main._salvar_json_atomico(alvo, {"a": 1, "b": [2, 3]})
    with open(alvo, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1, "b": [2, 3]}
    # nao deixou .tmp para tras
    assert not os.path.exists(alvo + ".tmp")
```

- [ ] **Step 2: Run → FAIL** (`_salvar_json_atomico` doesn't exist). `python -m pytest tests/test_confiabilidade.py -v`.

- [ ] **Step 3: Add the helper + use it.** In `main.py`, add near the other save helpers (~before `salvar_cores_arquivo`):

```python
def _salvar_json_atomico(caminho, data):
    """Escreve JSON de forma atomica (.tmp + os.replace) para evitar corrupcao
    se o processo morrer no meio da escrita."""
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
```

Then refactor the three savers to use it:
- `salvar_cores_arquivo` (~116-120):
```python
def salvar_cores_arquivo(cores):
    _ensure_dados()
    _salvar_json_atomico(CORES_FILE, sorted(set(c.upper() for c in cores if c)))
```
- `salvar_params` (~128-131):
```python
def salvar_params(params):
    _ensure_dados()
    _salvar_json_atomico(PARAMS_FILE, params)
```
- `salvar_historico` (find it — it does `with open(HISTORICO_FILE, "w"...) json.dump(historico...)`): replace that final write with `_salvar_json_atomico(HISTORICO_FILE, historico)`.

- [ ] **Step 4: Run → PASS + full suite.** `python -m pytest tests/ -q` → 103 passed.

- [ ] **Step 5: Commit.**
```
git add main.py tests/test_confiabilidade.py
git commit -m "feat(server): escrita atomica de cores/params/historico (.tmp + os.replace)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task F-T3: Validação de entrada + esconder stacktrace

**Files:**
- Modify: `main.py` (`do_POST` except ~308-310; `_calcular`/`_calcular_grupo` numeric parsing)
- Test: `tests/test_confiabilidade.py` (adicionar)

- [ ] **Step 1: Write the failing test.** Add to `tests/test_confiabilidade.py`:

```python
def test_num_coercao_com_default():
    assert main._num({"a": "5"}, "a", 1, int) == 5
    assert main._num({"a": "x"}, "a", 7, int) == 7      # invalido -> default
    assert main._num({}, "a", 9, int) == 9               # ausente -> default
    assert main._num({"a": "2.5"}, "a", 1.0, float) == 2.5
```

- [ ] **Step 2: Run → FAIL** (`_num` missing).

- [ ] **Step 3: Add `_num` + use it; hide the trace.** In `main.py`, add near the top helpers:

```python
def _num(p, key, default, tipo=float):
    """Coerce p[key] para tipo; em entrada invalida/ausente, devolve default
    (evita 500 cru por texto no campo)."""
    try:
        return tipo(p.get(key, default))
    except (TypeError, ValueError):
        return default
```

Use it for the numeric reads in `_calcular` and `_calcular_grupo` (the `int(p.get("max_folhas", 70))`, `float(p.get("consumo", 1.0645))`, `int(p.get("tol_abs", 4))`, etc.). Replace each `int(p.get("X", D))` with `_num(p, "X", D, int)` and `float(p.get("X", D))` with `_num(p, "X", D, float)`. (Read the param block in each handler and convert the numeric ones; leave string params like `criterio` and dict params like `grade`/`refs` as they are.)

Then change `do_POST`'s except (~308-310) to LOG the trace and return a friendly message (no raw trace):
```python
        except Exception as e:
            import traceback
            _log.error("Erro em %s: %s\n%s", path, e, traceback.format_exc())
            self._send(500, {"erro": "Erro interno no servidor. Detalhes no log (dados/logs/pcp.log)."})
```

- [ ] **Step 4: Run → PASS + full suite.** `python -m pytest tests/ -q` → 104 passed.

- [ ] **Step 5: Commit.**
```
git add main.py tests/test_confiabilidade.py
git commit -m "feat(server): validacao de entrada (coercao segura) + esconde stacktrace do 500

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task F-T4: Integridade do auto-update (exigir HTTPS)

**Files:**
- Modify: `updater.py` (`baixar_e_aplicar` ~169-196, antes do `urlretrieve`)
- Test: `tests/test_confiabilidade.py` (adicionar)

- [ ] **Step 1: Write the failing test.** Add to `tests/test_confiabilidade.py`:

```python
def test_update_rejeita_url_nao_https():
    import importlib
    upd = importlib.import_module("updater")
    ok, msg = upd.baixar_e_aplicar("http://exemplo.com/app.zip", "9.9.9")
    assert ok is False
    assert "https" in msg.lower()
```

- [ ] **Step 2: Run → FAIL** (currently it would try to download the http URL).

- [ ] **Step 3: Guard the URL.** In `updater.py::baixar_e_aplicar`, at the very start of the function body (before the download/`urlretrieve` ~line 189-191), add:

```python
    if not isinstance(asset_url, str) or not asset_url.lower().startswith("https://"):
        return False, "URL de update invalida: exige https:// (recusado por seguranca)."
```
(Confirm the function returns `(ok: bool, msg: str)` — the test and `aplicar_update_pendente` at ~332 expect that shape; match the actual return convention by reading the function.)

- [ ] **Step 4: Run → PASS + full suite.** `python -m pytest tests/ -q` → 105 passed.

- [ ] **Step 5: Commit.**
```
git add updater.py tests/test_confiabilidade.py
git commit -m "feat(updater): exige https no asset_url do auto-update (integridade)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente F
- [ ] `python -m pytest tests/ -q` → 105 passed (102 + 3 novos).
- [ ] `dados/logs/pcp.log` criado e com entradas.
- [ ] Merge `frente-f-confiabilidade` → `main` (ff) + remover branch.

## Self-Review (autor do plano)
- **Cobertura:** F-2 logs (F-T1), F-3 escrita atômica (F-T2), F-4 validação + esconder trace (F-T3), F-5 integridade do update via HTTPS (F-T4). **F-1 (estado global) deliberadamente fora** — recomendado adiar (lock já protege; risco > benefício).
- **Sem placeholders:** código completo; reconferir linhas nos saves/handlers/updater.
- **Risco:** baixo — tudo aditivo/localizado, não toca solver/alocação. `_salvar_json_atomico` reusa o padrão já validado em `cache_planos.py`. `_num` só troca coerção crua por coerção-com-default. O guard de https é um early-return.
- **Nota honesta sobre F-T4:** o download já é HTTPS (TLS protege MITM); um SHA-256 "ingênuo" contra um hash fornecido pela própria release seria teatro de segurança (atacante que controla a release controla o hash). O guard de exigir `https://` é a proteção simples e real; um hash pinado exigiria mudar o processo de release (fora de escopo).
