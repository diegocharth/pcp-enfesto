# Frente F-1 — Refatorar Estado Global do Solver — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Remover o estado global do solver (o global mutável `_mapas_historicos_injetar` e os atributos de função `resolver._*` / `resolver_multiref._convergiu`), passando-os por parâmetros opcionais — sem mudar o tipo de retorno e mantendo o `_calc_lock`.

**Architecture (design seguro):** Adicionar params **opcionais** `historicos=None` (passa os mapas históricos) e `resume_out=None` (dict que o solver preenche com o estado de retomada) a `resolver`; `resume_out=None` a `resolver_multiref`; `historicos=None` a `priorizar_mapas`. Como são opcionais com default, **callers existentes que não os passam continuam funcionando** (zero ripple para `test_solver_regressao` e o exemplo do CLAUDE.md). O `return` continua sendo a lista de soluções. O `_calc_lock` permanece — após F-1 ele serializa por **política** (CPU single-machine), não mais por necessidade de correção.

**Tech Stack:** Python stdlib, pytest.

**Pré-requisitos:**
- Branch `frente-f1-estado-global` (de `main`, que tem A–F).
- Baseline: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/ -q` → **105 passam**.
- **TRAVA ANTI-REGRESSÃO (hard gate):** o teste `tests/test_solver_regressao.py::test_baseline_blazer_isadora_nao_piora` (SOL1 2 mapas/desvio≤39, SOL2 3 mapas/desvio≤13) DEVE continuar passando. Se quebrar → **reverter F-1** (o lock já mantinha tudo seguro) e reportar.
- Linhas conferidas 2026-06-24.

---

## Task F1-T1: Refatorar (param opcionais) — único passo

**Files:** `engine/mapas.py`, `engine/solver.py`, `engine/solver_multiref.py`, `main.py`, `tests/test_solver_multiref.py`.

- [ ] **Step 1: `engine/mapas.py` — historicos vira parâmetro.**
  - Remover o global `_mapas_historicos_injetar: list = []` (linha 13) e ajustar o comentário acima (11-12) que o descreve.
  - Assinatura: `def priorizar_mapas(mapas: list, grade_total: dict, tamanhos: list, top_n: int = 300, historicos: list = None) -> list:`.
  - No bloco "Mapas históricos no início" (175-185), trocar o uso do global pelo parâmetro:
    ```python
    # 5. Mapas históricos no início (passados pelo chamador)
    if historicos:
        mapas_set = {tuple(sorted(m.items())) for m in mapas}
        hist_valid = [m for m in historicos
                      if tuple(sorted(m.items())) in mapas_set]
        if hist_valid:
            hist_keys = {tuple(sorted(m.items())) for m in hist_valid}
            resto = [m for m in result if tuple(sorted(m.items())) not in hist_keys]
            result = hist_valid + resto
    ```
    (remover a linha `global _mapas_historicos_injetar`.)

- [ ] **Step 2: `engine/solver.py` — historicos + resume_out.**
  - Assinatura `def resolver(...)` (linha 182): adicionar 2 params opcionais ao final: `..., min_n_mapas=1, skip_combos=0, historicos=None, resume_out=None):`.
  - Linha 183: `prior = priorizar_mapas(rel, grade_total, tamanhos, top_n=400, historicos=historicos)`.
  - Substituir os 4 atributos de função (394-397):
    ```python
    resolver._niveis_esgotados   = niveis_esgotados
    resolver._ultimo_n_explorado = n_mapas if 'n_mapas' in dir() else min_n_mapas
    resolver._proximo_n          = proximo_n
    resolver._skip_combos        = skip_proximo
    ```
    por:
    ```python
    if resume_out is not None:
        resume_out["niveis_esgotados"]   = niveis_esgotados
        resume_out["ultimo_n_explorado"] = n_mapas if 'n_mapas' in dir() else min_n_mapas
        resume_out["proximo_n"]          = proximo_n
        resume_out["skip_combos"]        = skip_proximo
    ```
    (manter o `return result[:num_opcoes]` logo abaixo.)

- [ ] **Step 3: `engine/solver_multiref.py` — resume_out.**
  - Assinatura (linha 14): `def resolver_multiref(refs_data, tamanhos, config, callback=None, timeout_s=120, n_mapas_max=7, resume_out=None):`.
  - Linha 40 (`resolver_multiref._convergiu = True`) → trocar por: `if resume_out is not None: resume_out["convergiu"] = True`.
  - Linha 252 (`resolver_multiref._convergiu = not cortado_timeout`) → trocar por: `if resume_out is not None: resume_out["convergiu"] = not cortado_timeout`.
  - (Os dois cobrem todos os caminhos de retorno: linha 40 cobre o early-return `n_teto<1`; linha 252 cobre os demais.)

- [ ] **Step 4: `main.py` `_calcular` — usar os params, remover injeção/atributos.**
  - Remover a linha `from engine import mapas as _mapas_mod` (~362; era só para a injeção).
  - No bloco sob o lock (após a aquisição non-blocking), substituir:
    ```python
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
    por:
    ```python
        try:
            _resume = {}
            solucoes = resolver(grade, tamanhos, limites, cfg,
                                callback_progresso=cb, timeout_s=timeout,
                                min_n_mapas=min_n_mapas, skip_combos=skip_combos,
                                historicos=historicos, resume_out=_resume)
            r_niveis = _resume.get('niveis_esgotados', [])
            r_prox   = _resume.get('proximo_n', 1)
            r_skip   = _resume.get('skip_combos', 0)
        finally:
            _calc_lock.release()
    ```
    (`historicos` já é uma variável local em `_calcular`, carregada de `carregar_historico(fp)` — confirmar; permanece.)

- [ ] **Step 5: `main.py` `_calcular_grupo` — resume_out.**
  - No bloco sob o lock, substituir:
    ```python
            solucoes = resolver_multiref(refs_data, tamanhos, cfg,
                                         callback=cb, timeout_s=timeout,
                                         n_mapas_max=n_mapas_max)
            _convergiu = getattr(resolver_multiref, '_convergiu', True)
    ```
    por:
    ```python
            _resume_g = {}
            solucoes = resolver_multiref(refs_data, tamanhos, cfg,
                                         callback=cb, timeout_s=timeout,
                                         n_mapas_max=n_mapas_max, resume_out=_resume_g)
            _convergiu = _resume_g.get('convergiu', True)
    ```

- [ ] **Step 6: `tests/test_solver_multiref.py` — adaptar o teste do `_convergiu` (linhas 66-77).** Trocar:
    ```python
    resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=60)
    assert getattr(resolver_multiref, "_convergiu", None) is True
    ```
    por:
    ```python
    _r = {}
    resolver_multiref(refs, TAMS, CFG, callback=None, timeout_s=60, resume_out=_r)
    assert _r.get("convergiu") is True
    ```

- [ ] **Step 7: VERIFY (hard gate) + commit.**
  - `python -m pytest tests/test_solver_regressao.py -v` → AMBOS passam (baseline 2/39, 3/13 preservado). **Se `test_baseline_blazer_isadora_nao_piora` falhar → reverter tudo (`git checkout -- .`) e reportar BLOCKED.**
  - `python -m pytest tests/ -q` → 105 passed.
  - `python -c "import ast; [ast.parse(open(r'<proj>/'+p,encoding='utf-8').read()) for p in ['main.py','engine/solver.py','engine/solver_multiref.py','engine/mapas.py']]; print('PARSE OK')"`.
  - Grep (fora de docs/): `_mapas_historicos_injetar` → 0; `resolver\._` → 0 (nenhuma escrita/leitura de atributo); `resolver_multiref\._convergiu` → 0.
  - Manual (mantenedor, depois): o botão "Continuar" (retomada) ainda funciona — `r_prox`/`r_skip` agora vêm do dict `resume_out`.
```
git add engine/mapas.py engine/solver.py engine/solver_multiref.py main.py tests/test_solver_multiref.py
git commit -m "refactor(solver): estado de retomada/historicos via parametros (remove estado global)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## Self-Review (autor)
- **Cobertura:** remove o global `_mapas_historicos_injetar` (mapas.py) e os atributos de função (`resolver._*`, `resolver_multiref._convergiu`) — os 3 mecanismos de estado global do solver.
- **Risco contido:** params são OPCIONAIS (default None) → `test_solver_regressao` e o exemplo do CLAUDE.md (que chamam `resolver(...)` sem os novos params) continuam funcionando sem mudança; o tipo de retorno não muda. O único teste que muda é o do `_convergiu` (lia o atributo). O baseline é a trava: se mudar, reverte.
- **Lock:** mantido de propósito (serialização por política CPU). F-1 só remove a *dependência de correção* no lock.
