# Frente D — Solver — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover os pesos de eficiência placebo (e o código morto associado) e adicionar um desempate que prefere concentrar o desvio nas células de maior quantidade — sem nunca piorar nº de enfestos nem desvio total.

**Architecture:** D2 primeiro (aditivo, com baseline anti-regressão), D1 depois (remoções em cascata por vários arquivos, usando o `desvio_relativo` de D2 para substituir a coluna "Score" do Excel). O desempate por desvio relativo entra como **última chave** dos 4 sorts (não pode alterar as métricas primárias). Um ajuste opcional no coordinate-descent é **condicionado** ao teste de baseline.

**Tech Stack:** Python 3.10+ stdlib, pytest; HTML/CSS/JS vanilla.

**Pré-requisitos / ordem:**
- Branch `frente-d-solver` (a partir de `main`, que já tem A+B+C).
- Baseline: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/ -q` → **97 passam**.
- **Baseline anti-regressão (Blazer Isadora, determinístico):** o solver retorna 2 opções — `SOL1 (n_mapas=2, desvio_total=39)` e `SOL2 (n_mapas=3, desvio_total=13)`. **Frente D não pode piorar `(n_mapas, desvio_total)` de nenhuma das duas.**
- `engine/solver.py` e `engine/solver_multiref.py` NÃO foram tocados por A/B/C — números de linha confiáveis. Os outros arquivos (interface.html, main.py, tolerancia.py, config.json, export_xlsx.py) deslocaram — números abaixo conferidos por grep em 2026-06-24; reconferir lendo.
- **Encoding:** novo código em `interface.html` 100% ASCII.
- Ordem: D-T1 (D2, aditivo) → D-T2 (D1, remoções).

---

## File Structure

| Arquivo | D2 (D-T1) | D1 (D-T2) |
|---|---|---|
| `engine/solver.py` | + `desvio_relativo` no resumo; + 4ª chave de sort; eval_fs retorna d_rel (gated) | remover `_score_solucao`, campo `score`, imports `custo_desvio`/`check_viavel` |
| `engine/solver_multiref.py` | + `desvio_relativo` no resumo + sorts | — |
| `engine/tolerancia.py` | — | remover `custo_desvio` |
| `tests/test_solver_regressao.py` (novo) | baseline + desempate + grade-zero | — |
| `interface.html` | — | remover inputs/CSS/sincPeso/coleta dos pesos |
| `main.py` | — | remover cfg/salvar/assinatura dos pesos |
| `config.json` | — | remover chaves mortas |
| `exportar/export_xlsx.py` | — | trocar coluna "Score otimização" por "Desvio relativo" |
| `tests/test_solver_multiref.py`, `tests/test_alocador_rolos.py` | — | remover chaves de peso do CFG de teste |
| `CLAUDE.md` | — | documentar hierarquia real |

---

## Task D-T1: D2 — desempate por desvio relativo (aditivo, com baseline)

**Files:**
- Modify: `engine/solver.py` (eval_fs ~50; melhores.append resumo ~333-349; sorts ~358-362 e ~387-389)
- Modify: `engine/solver_multiref.py` (loop ~155-157; resumo ~215-222; sorts ~228-232 e ~250-254)
- Test: `tests/test_solver_regressao.py` (criar)

- [ ] **Step 1: Write the failing/guard tests.** Create `tests/test_solver_regressao.py`:

```python
"""D2: desempate por desvio relativo NUNCA piora (n_mapas, desvio_total); e o
baseline Blazer Isadora permanece. Tambem: solucoes carregam desvio_relativo."""
import json, os
from engine.solver import resolver
from engine.tolerancia import calcular_limites_grade

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRADE = {
    'BLUES':   {'PP':41,'P':45,'M':25,'G':10},
    'BOSSA':   {'PP':19,'P':20,'M':13,'G':2},
    'JAZZ':    {'PP':44,'P':55,'M':30,'G':11},
    'PRETO':   {'PP':47,'P':54,'M':31,'G':12},
    'SAMBA':   {'PP':39,'P':37,'M':18,'G':5},
    'VALSA':   {'PP':45,'P':50,'M':23,'G':5},
    'VANILLA': {'PP':49,'P':51,'M':27,'G':9},
}
TAMS = ['PP','P','M','G']


def _cfg():
    cfg = json.load(open(os.path.join(BASE, 'config.json'), encoding='utf-8'))
    cfg.update({'consumo_peca_m':1.0645,'mesa_comprimento_m':10.0,'limite_folhas_padrao':70})
    return cfg


def test_baseline_blazer_isadora_nao_piora():
    cfg = _cfg()
    lim = calcular_limites_grade(GRADE, TAMS, cfg, {})
    sols = resolver(GRADE, TAMS, lim, cfg, lambda m: None, timeout_s=60)
    assert len(sols) >= 2
    # opcao 1: 2 mapas, desvio <= 39 ; opcao 2: 3 mapas, desvio <= 13 (nao piora)
    assert sols[0]['resumo']['n_mapas'] == 2 and sols[0]['resumo']['desvio_total'] <= 39
    assert sols[1]['resumo']['n_mapas'] == 3 and sols[1]['resumo']['desvio_total'] <= 13


def test_solucoes_tem_desvio_relativo():
    cfg = _cfg()
    lim = calcular_limites_grade(GRADE, TAMS, cfg, {})
    sols = resolver(GRADE, TAMS, lim, cfg, lambda m: None, timeout_s=60)
    for s in sols:
        assert 'desvio_relativo' in s['resumo']
        assert s['resumo']['desvio_relativo'] >= 0
```

- [ ] **Step 2: Run to see the baseline (and the missing key).** `python -m pytest tests/test_solver_regressao.py -v` → `test_baseline...` should PASS already (current solver gives 2/39 and 3/13); `test_solucoes_tem_desvio_relativo` FAILS (`desvio_relativo` not in resumo yet). Record the baseline numbers printed.

- [ ] **Step 3: Add `desvio_relativo` to the single-ref resumo + sort key.** In `engine/solver.py`:

(a) After `dev_total = desvio_absoluto_total(...)` (line ~329) and before `melhores.append`, compute:
```python
            dev_rel = round(sum(
                abs(cortado_tot[c].get(t, 0) - grade[c].get(t, 0)) / (grade[c].get(t, 0) or 1)
                for c in grade for t in tamanhos
            ), 4)
```
(b) Add to the resumo dict (after `"desvio_total": dev_total,`, line ~345):
```python
                    "desvio_relativo"     : dev_rel,
```
(c) Add `desvio_relativo` as the LAST sort key in BOTH sorts (lines ~358-362 and ~387-389):
```python
            melhores.sort(key=lambda s: (
                s["n_mapas"],
                s["resumo"]["desvio_total"],
                -s["resumo"]["media_pecas_mapa"],
                s["resumo"]["desvio_relativo"],
            ))
```
(do the same for the final sort ~387-389).

- [ ] **Step 4: Add `desvio_relativo` to multiref.** In `engine/solver_multiref.py`:

(a) The per-(ref,cor) loop already does `desvio_total += sum(abs(ct[t] - grade_cor.get(t, 0)) for t in tamanhos)` (~line 157). Initialize `desvio_rel_total = 0` next to `desvio_total = 0` (~line 138), and add alongside the desvio_total accumulation:
```python
                    desvio_rel_total += sum(
                        abs(ct[t] - grade_cor.get(t, 0)) / (grade_cor.get(t, 0) or 1)
                        for t in tamanhos
                    )
```
(b) In the resumo dict (~215-222), add `"desvio_relativo": round(desvio_rel_total, 4),`.
(c) Add `s["resumo"]["desvio_relativo"]` as the LAST sort key in BOTH sorts (~228-232 and ~250-254).

- [ ] **Step 5: Run the guard tests.** `python -m pytest tests/test_solver_regressao.py -v` → both PASS (baseline preserved; `desvio_relativo` present). If `test_baseline...` now FAILS, STOP — the sort change must NOT alter the baseline (it can't, since `desvio_relativo` is the last key; if it failed, something else is wrong — investigate).

- [ ] **Step 6 (OPTIONAL, GATED): folha-level steering in `_resolver_folhas_cor`.** This makes the coordinate descent prefer lower relative deviation among EQUAL-absolute-deviation points. It is OPTIONAL and must be REVERTED if it changes the baseline.

Change `eval_fs` (lines 50-62) to also return relative deviation:
```python
    def eval_fs(fs):
        """Retorna (desvio_total, desvio_relativo, viavel)."""
        d = 0; d_rel = 0.0; ok = True
        for ti in range(T):
            ct = 0
            for k in range(N):
                ct += fs[k] * rows[k][ti]
            diff = ct - g[ti]
            ad = diff if diff >= 0 else -diff
            d += ad
            d_rel += ad / (g[ti] if g[ti] > 0 else 1)
            lo, hi = lims[ti]
            if diff < lo or diff > hi:
                ok = False
        return d, d_rel, ok
```
Update the 4 call sites (72, 110, 119, 125). CRITICAL — the LOCAL move decision (`best_v`/`best_local_dev`) must stay on ABSOLUTE `d` only (to preserve the search trajectory); only the GLOBAL `best_fs` recording tie-breaks by `d_rel`:
- N=1 (70-77): `best_fs=None; best_dev=float('inf'); best_drel=float('inf')`; in the loop `d, d_rel, ok = eval_fs([f])`; `if ok and (d < best_dev or (d==best_dev and d_rel < best_drel)): best_dev=d; best_drel=d_rel; best_fs=[f];` keep `if d == 0: return best_fs`.
- coordinate descent: `best_fs=None; best_feas_dev=float('inf'); best_feas_drel=float('inf')`; seed check `cur_dev, cur_drel, cur_ok = eval_fs(fs)` with `if cur_ok and (cur_dev < best_feas_dev or (cur_dev==best_feas_dev and cur_drel < best_feas_drel)): best_feas_dev=cur_dev; best_feas_drel=cur_drel; best_fs=list(fs)`; line 119 `base_dev, _bd, _ = eval_fs(fs)`; inner loop `d, d_rel, ok = eval_fs(fs)`; `if ok and (d < best_feas_dev or (d==best_feas_dev and d_rel < best_feas_drel)): best_feas_dev=d; best_feas_drel=d_rel; best_fs=list(fs)`; **keep** `if d < best_local_dev: best_local_dev=d; best_v=v` EXACTLY (absolute only — do NOT add d_rel here).

Then run `python -m pytest tests/test_solver_regressao.py tests/test_solver_multiref.py -v`.
- **If `test_baseline_blazer_isadora_nao_piora` STILL PASSES → keep this step.**
- **If it FAILS (the baseline `(n_mapas, desvio_total)` changed) → REVERT this Step 6 entirely** (git checkout the eval_fs/descent changes), keeping only Steps 3-4 (the safe final-sort tie-break). Report that Step 6 was reverted due to baseline change.

- [ ] **Step 7: Full suite + commit.** `python -m pytest tests/ -q` → 99 passed (97 + 2 new).
```
git add engine/solver.py engine/solver_multiref.py tests/test_solver_regressao.py
git commit -m "feat(solver): desempate por desvio relativo (concentra ajuste nas qtds maiores)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task D-T2: D1 — remover pesos placebo + código morto

**Files:** `interface.html`, `main.py`, `config.json`, `engine/solver.py`, `engine/tolerancia.py`, `exportar/export_xlsx.py`, `tests/test_solver_multiref.py`, `tests/test_alocador_rolos.py`, `CLAUDE.md`.

Sem teste automatizado novo (é remoção). A rede de segurança é a suíte existente (99) + o baseline de D-T1. Verificação: a UI carrega sem erro (ast/parse + grep de referências órfãs) e a suíte passa.

- [ ] **Step 1: `interface.html` — remover os controles de peso.**
  - Remover as regras CSS `.peso-wrap`, `.peso-wrap input`, `.peso-total`, `.peso-total.err` (linhas ~117-120).
  - Remover os DOIS `<div class="field">` dos pesos: o de "Peso eficiência de encaixe" (engloba a label, o `<div class="peso-wrap">` linha ~173 com `#peso_enc` ~174 e `#peso-total` ~175, e o hint) e o de "Peso eficiência operacional" (label, `<div class="peso-wrap">` ~181 com `#peso_op` ~182, hint). Ler o bloco ~171-185 e remover os dois fields inteiros.
  - Remover as DUAS chamadas livres `sincPeso('enc');` (linha ~419 em window.onload e ~459 em carregarDados).
  - Remover as 2 linhas que restauram pesos em carregarDados (~437-438: `if (p.peso_enc...)` e `if (p.peso_op...)`).
  - Remover a função `sincPeso` inteira (~475-492).
  - Remover `const peso_enc`/`const peso_op` da coleta (~962-963).
  - Remover `peso_enc,peso_op` de `baseParams` (~987) e do `payload` single (~1175).
  - Após remover, `grep -n "peso_enc\|peso_op\|sincPeso\|peso-wrap\|peso-total" interface.html` deve retornar **zero**.

- [ ] **Step 2: `main.py` — remover plumbing dos pesos.**
  - `_calcular` (~308-309): remover as 2 linhas `cfg["peso_eficiencia_*"]`.
  - `salvar_params` (~329-330): remover `"peso_enc"`/`"peso_op"`.
  - assinatura single (~353): remover `"peso_enc": ..., "peso_op": ...,`.
  - `_calcular_grupo` (~492-493): remover as 2 linhas `cfg["peso_eficiencia_*"]`.
  - assinatura grupo (~529): remover `"peso_enc": ..., "peso_op": ...,`.
  - `grep -n "peso_eficiencia\|peso_enc\|peso_op" main.py` → zero.

- [ ] **Step 3: `config.json` — remover chaves mortas.** Remover `peso_eficiencia_encaixe` (8), `peso_eficiencia_operacional` (9), `tamanhos_prioritarios_positivo` (10), o bloco `peso_desvio_por_tamanho` (11-?), `peso_fragmentacao` (23), `peso_ponta_util` (24). Validar JSON: `python -c "import json; json.load(open(r'<proj>\config.json',encoding='utf-8')); print('OK')"`.

- [ ] **Step 4: `engine/solver.py` — remover score morto.**
  - Import (linha 10): de `from engine.tolerancia import check_viavel, custo_desvio, desvio_absoluto_total` para `from engine.tolerancia import desvio_absoluto_total` (remover `check_viavel` e `custo_desvio` — ambos nunca chamados).
  - Remover a função `_score_solucao` inteira (152-179).
  - Remover a chamada `sc = _score_solucao(...)` (linha 326).
  - Remover o campo `"score"  : sc,` do dict (linha 337).

- [ ] **Step 5: `engine/tolerancia.py` — remover `custo_desvio`.** Remover a função `custo_desvio` (~78-?, lê `peso_desvio_por_tamanho`/`tamanhos_prioritarios_positivo`). Confirmar por grep que nada mais a importa/chama (só o import em solver.py, já removido no Step 4). Manter `calcular_limites`, `_resolver_limite`, `calcular_limites_grade`, `check_viavel` (este último existe mas... confirmar: se `check_viavel` também é morto, pode remover; mas é seguro mantê-lo — só remover `custo_desvio`).

- [ ] **Step 6: `exportar/export_xlsx.py` — trocar a coluna Score.** Linha ~642: `("Score otimização", lambda s: round(s.get("score", 0), 4)),` → trocar por `("Desvio relativo", lambda s: round(s.get("resumo", {}).get("desvio_relativo", 0), 4)),`. (O `desvio_relativo` vem do resumo de D-T1; o `.get("resumo",{})` é defensivo.)

- [ ] **Step 7: testes — remover chaves de peso dos CFGs de teste.**
  - `tests/test_solver_multiref.py` (~22-25): remover `peso_eficiencia_encaixe`, `peso_eficiencia_operacional`, `peso_desvio_por_tamanho`, `tamanhos_prioritarios_positivo` do dict CFG de teste.
  - `tests/test_alocador_rolos.py` (~24-25): remover `peso_fragmentacao`, `peso_ponta_util` do `CONFIG_BASE`.

- [ ] **Step 8: `CLAUDE.md` — documentar a hierarquia real.** No bloco de exemplo de config (~199-202), remover as linhas dos pesos/`peso_desvio_por_tamanho`/`tamanhos_prioritarios_positivo`. Adicionar (na seção do solver) uma nota: a ordenação real é lexicográfica — `menos enfestos → menor desvio → mais peças/mapa → menor desvio relativo`; não há pesos configuráveis.

- [ ] **Step 9: Verify + commit.**
  - `python -c "import ast; ast.parse(open(r'<proj>\main.py',encoding='utf-8').read()); ast.parse(open(r'<proj>\engine\solver.py',encoding='utf-8').read()); ast.parse(open(r'<proj>\engine\tolerancia.py',encoding='utf-8').read()); print('OK')"`.
  - `python -m pytest tests/ -q` → 99 passed (o baseline de D-T1 protege o solver; remoções não devem quebrar nada).
  - `grep` de `peso_enc|peso_op|peso_eficiencia|_score_solucao|custo_desvio` no projeto (fora de docs) → só ocorrências esperadas (nenhuma viva).
  - Manual (mantenedor): abrir o app, calcular — não deve haver erro de JS (os campos de peso somem) e o Excel mostra "Desvio relativo" no resumo.
```
git add interface.html main.py config.json engine/solver.py engine/tolerancia.py exportar/export_xlsx.py tests/test_solver_multiref.py tests/test_alocador_rolos.py CLAUDE.md
git commit -m "refactor(solver): remove pesos de eficiencia placebo e codigo morto (score, custo_desvio)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente D
- [ ] `python -m pytest tests/ -q` → 99 passed.
- [ ] Baseline Blazer Isadora: SOL1 (2,39) / SOL2 (3,13) inalterados.
- [ ] UI sem campos de peso e sem erro; Excel com "Desvio relativo".
- [ ] Merge `frente-d-solver` → `main` (ff) + remover branch.

## Self-Review (autor do plano)
- **Cobertura do spec (Frente D):** D1 remover pesos+morto (D-T2) ✓; D2 desempate por desvio relativo (D-T1) ✓, com o ajuste de folha (Step 6) **gated** pelo baseline — honra "desde que mantenha a eficiência".
- **Sem placeholders:** código completo; old/new exatos. solver.py/multiref com linhas confiáveis; demais com linhas via grep (reconferir).
- **Consistência:** `desvio_relativo` definido em D-T1 (resumo single+multiref) e consumido em D-T2 (coluna do Excel) e nos 4 sorts; remoção do `score` (D-T2 Step 4) casada com a troca da coluna (Step 6). A segurança da D2 vem de ser a ÚLTIMA chave de sort (não altera métricas primárias) + baseline test; o Step 6 (coordinate-descent) só fica se o baseline não mudar.
- **Risco:** concentrado no Step 6 (gated/revertível). O resto é aditivo (D-T1) ou remoção coberta pela suíte (D-T2).
