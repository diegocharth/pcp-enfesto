# Frente B — Entrada & UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir digitar rolos em células numéricas (8 iniciais, auto-crescimento, Tab) e aceitar percentual (`10%`) além de absoluto nos limites especiais de tolerância.

**Architecture:** B2 backend (`tolerancia.py`) é a fundação testável (TDD). B2 frontend ajusta `renderTol`/`lerRegras` para trafegar `"N%"` ou inteiro. B1 troca o input de texto único por uma linha de células por cor, com `_rolosPorCor` como fonte única de verdade. Frontend é vanilla JS (sem harness) — verificação manual + revisão; backend tem pytest.

**Tech Stack:** Python 3.10+ stdlib, pytest; HTML/CSS/JS vanilla.

**Pré-requisitos / ordem:**
- Branch `frente-b-entrada-ui` (criado a partir de `main`, que já tem a Frente A).
- Baseline: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/ -q` → **80 passam**.
- **Encoding:** novo código em `interface.html` deve ser **100% ASCII** (sem acento cru; usar entidades). Editar com a ferramenta Edit, nunca PowerShell.
- Números de linha verificados em 2026-06-24 (pós-Frente A) — **reconferir** lendo o arquivo antes de editar; B1 desloca linhas para B-T3 se feito por último (ordem recomendada: B-T1 → B-T2 → B-T3).
- B-T1 e B-T2 são as duas metades do mesmo recurso (% nas tolerâncias): B-T1 (backend, testável) primeiro.

---

## File Structure

| Arquivo | Responsabilidade nesta frente |
|---|---|
| `engine/tolerancia.py` | B2 backend: helper `_resolver_limite` + interpretação `"N%"`/absoluto em `calcular_limites`, preservando o sinal do `lo` absoluto. |
| `tests/test_tolerancia.py` (novo) | Testa `calcular_limites` (8 casos: sinal, percentual, vírgula, retrocompat). |
| `interface.html` | B2 frontend: `renderTol` inputs `type=text`; `lerRegras` interpreta `"N%"`/absoluto. B1: células de rolo em `atualizarCoresAlocacao` + helpers; leitura direta de `_rolosPorCor` em `iniciarAlocacao`. |

---

## Task B-T1: B2 backend — percentual nas tolerâncias especiais (`tolerancia.py`)

**Files:**
- Modify: `engine/tolerancia.py` (`calcular_limites`, ramo `regras_especiais` linhas 17-26; novo helper)
- Test: `tests/test_tolerancia.py` (criar)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tolerancia.py`:

```python
"""B2: calcular_limites aceita limite especial absoluto (com sinal preservado)
ou percentual ('N%', relativo a grade). Regra critica: so o ramo percentual
nega a magnitude do lo; o absoluto preserva o sinal digitado."""
from engine.tolerancia import calcular_limites

CFG = {"desvio_absoluto_padrao": 4, "desvio_percentual_padrao": 20,
       "criterio_combinacao": "MIN"}


def test_lo_absoluto_int_preserva_sinal():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"lo": -4, "hi": 4}})
    assert (lo, hi) == (-4, 4)


def test_lo_absoluto_str_preserva_sinal():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"lo": "-4", "hi": "4"}})
    assert (lo, hi) == (-4, 4)


def test_hi_percentual_grade_40():
    # 40 * 10% = 4 ; lo ausente -> -tol_geral (min(4, round(40*20/100)=8) = 4)
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"hi": "10%"}})
    assert hi == 4
    assert lo == -4


def test_lo_percentual_magnitude_negada():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"lo": "10%"}})
    assert lo == -4


def test_percentual_zero():
    lo, hi = calcular_limites(40, "G", CFG, {"G": {"hi": "0%"}})
    assert hi == 0


def test_percentual_virgula_decimal():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {"hi": "10,5%"}})
    assert hi == round(40 * 10.5 / 100)  # round(4.2) == 4


def test_limites_ausentes_usam_tol_geral():
    lo, hi = calcular_limites(40, "M", CFG, {"M": {}})
    assert (lo, hi) == (-4, 4)


def test_retrocompat_g_hi_zero_int():
    lo, hi = calcular_limites(12, "G", CFG, {"G": {"hi": 0}})
    assert hi == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/test_tolerancia.py -v`
Expected: the percentual tests FAIL (current code does `int(r["hi"])` → `int("10%")` raises `ValueError`). The absoluto/retrocompat tests may already pass.

- [ ] **Step 3: Implement the helper and the corrected branch**

In `engine/tolerancia.py`, add the helper immediately before `def calcular_limites(` (line 10):

```python
def _resolver_limite(valor, grade_valor):
    """Magnitude inteira (>=0 p/ percentual) de um limite especial.
    String terminando em '%' -> relativo a grade (round); senao absoluto."""
    if isinstance(valor, str):
        s = valor.strip()
        if s.endswith('%'):
            pct = float(s[:-1].strip().replace(',', '.'))
            return int(round(float(grade_valor) * pct / 100.0))
        return int(round(float(s.replace(',', '.'))))
    return int(valor)
```

Replace the special-rules branch (currently lines 17-26):

```python
    if regras_especiais and tamanho in regras_especiais:
        r = regras_especiais[tamanho]
        # Calcular tol geral para usar quando lo ou hi não forem informados
        tol_abs = int(config.get("desvio_absoluto_padrao", 4))
        tol_pct = max(1, round(float(grade_valor) * float(config.get("desvio_percentual_padrao", 20)) / 100.0))
        criterio = config.get("criterio_combinacao", "MIN").upper()
        tol_geral = min(tol_abs, tol_pct) if criterio == "MIN" else max(tol_abs, tol_pct)
        lo = int(r["lo"]) if "lo" in r else -tol_geral
        hi = int(r["hi"]) if "hi" in r else tol_geral
        return (lo, hi)
```

with:

```python
    if regras_especiais and tamanho in regras_especiais:
        r = regras_especiais[tamanho]
        # Calcular tol geral para usar quando lo ou hi não forem informados
        tol_abs = int(config.get("desvio_absoluto_padrao", 4))
        tol_pct = max(1, round(float(grade_valor) * float(config.get("desvio_percentual_padrao", 20)) / 100.0))
        criterio = config.get("criterio_combinacao", "MIN").upper()
        tol_geral = min(tol_abs, tol_pct) if criterio == "MIN" else max(tol_abs, tol_pct)
        # 'lo': percentual -> magnitude negada; absoluto (int ou str) -> sinal preservado.
        if "lo" in r:
            v = r["lo"]
            if isinstance(v, str) and v.strip().endswith('%'):
                lo = -_resolver_limite(v, grade_valor)
            elif isinstance(v, str):
                lo = int(round(float(v.strip().replace(',', '.'))))
            else:
                lo = int(v)
        else:
            lo = -tol_geral
        hi = _resolver_limite(r["hi"], grade_valor) if "hi" in r else tol_geral
        return (lo, hi)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tolerancia.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Run full suite + commit**

Run: `python -m pytest tests/ -q` → 88 passed (80 + 8 novos).

```bash
git add engine/tolerancia.py tests/test_tolerancia.py
git commit -m "feat(tolerancia): limites especiais aceitam percentual (N%) alem de absoluto

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task B-T2: B2 frontend — `renderTol`/`lerRegras` aceitam `%`

**Files:**
- Modify: `interface.html` (`renderTol` linhas 508-515; `lerRegras` linhas 516-529)

Sem teste JS automatizado — verificação manual no Step final. O backend (B-T1) já prova a interpretação de `"N%"`.

- [ ] **Step 1: `renderTol` — inputs de texto**

Replace `renderTol` (lines 508-515):

```javascript
function renderTol() {
  document.getElementById('tol-body').innerHTML = tamanhos.map(t =>
    `<tr><td><b>${t}</b></td>
     <td><input type="number" id="tlo_${t}" placeholder="(auto)" style="width:58px"></td>
     <td><input type="number" id="thi_${t}" placeholder="(auto)" value="${t==='G'?0:''}" style="width:58px"></td>
     <td><input type="checkbox" id="tat_${t}" ${t==='G'?'checked':''}></td></tr>`
  ).join('');
}
```

with (type=text, placeholder hint, slightly wider; G default 0 and checkbox kept):

```javascript
function renderTol() {
  document.getElementById('tol-body').innerHTML = tamanhos.map(t =>
    `<tr><td><b>${t}</b></td>
     <td><input type="text" id="tlo_${t}" placeholder="(auto)" style="width:72px"></td>
     <td><input type="text" id="thi_${t}" placeholder="4 ou 10%" value="${t==='G'?0:''}" style="width:72px"></td>
     <td><input type="checkbox" id="tat_${t}" ${t==='G'?'checked':''}></td></tr>`
  ).join('');
}
```

- [ ] **Step 2: `lerRegras` — interpretar `%`/absoluto, normalizar undefined, percentual sempre magnitude**

Replace `lerRegras` (lines 516-529):

```javascript
function lerRegras() {
  const r={};
  tamanhos.forEach(t=>{
    if(document.getElementById(`tat_${t}`)?.checked){
      const lo=document.getElementById(`tlo_${t}`)?.value;
      const hi=document.getElementById(`thi_${t}`)?.value;
      const o={};
      if(lo!=='') o.lo=parseInt(lo);
      if(hi!=='') o.hi=parseInt(hi);
      if(Object.keys(o).length) r[t]=o;
    }
  });
  return r;
}
```

with:

```javascript
function lerRegras() {
  const r={};
  const parseLim=(raw)=>{
    const s=(raw||'').trim();
    if(s==='') return undefined;
    if(s.endsWith('%')){
      const m=parseFloat(s.slice(0,-1).trim().replace(',','.'));
      return isNaN(m) ? undefined : (Math.abs(m)+'%');  // percentual sempre magnitude
    }
    const n=parseInt(s,10);                              // absoluto: preserva sinal (-4)
    return isNaN(n) ? undefined : n;
  };
  tamanhos.forEach(t=>{
    if(document.getElementById(`tat_${t}`)?.checked){
      const o={};
      const vlo=parseLim(document.getElementById(`tlo_${t}`)?.value);
      const vhi=parseLim(document.getElementById(`thi_${t}`)?.value);
      if(vlo!==undefined) o.lo=vlo;
      if(vhi!==undefined) o.hi=vhi;
      if(Object.keys(o).length) r[t]=o;
    }
  });
  return r;
}
```

Notes: `(raw||'')` handles `?.value` returning `undefined` when an element is absent. Percentual is stored as a magnitude string `"N%"` (e.g. `"10%"`, `"10.5%"`); the backend (`_resolver_limite`) negates it for `lo`. Absolute is an int (negative allowed for `lo`). This format is JSON-safe and survives the cache signature (`json.dumps(default=str)`).

- [ ] **Step 3: Verify (no browser available to the agent)**

- Confirm the two functions were replaced and the inserted JS is 100% ASCII and brace-balanced.
- Sanity: `python -m pytest tests/ -q` → 88 passed (Python unaffected).
- Manual (maintainer, later): in the app, mark G active with `Máx = 0` (default), and set e.g. PP `Máx = 10%`; calculate; the special limits apply and appear in the Excel header (Frente A) as `PP[..10%]`.

- [ ] **Step 4: Commit**

```bash
git add interface.html
git commit -m "feat(ui): tolerancias especiais aceitam percentual (10%) alem de absoluto

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task B-T3: B1 — Células numéricas de rolo por cor

**Files:**
- Modify: `interface.html` (`atualizarCoresAlocacao` linhas 1878-1960; helpers novos perto de `_parseRolos` 1870; `iniciarAlocacao` leitura de rolos linhas 1977-1990)

Sem teste JS automatizado — verificação manual + revisão. Todo código novo 100% ASCII.

- [ ] **Step 1: Add cell helper functions (after `_parseRolos`, ~line 1876)**

Immediately AFTER the closing `}` of `function _parseRolos(str){...}` (line 1876) and BEFORE `function atualizarCoresAlocacao()` (1878), insert:

```javascript
// -- B1: celulas numericas de rolo. _rolosPorCor[cor] = number[] e a fonte unica. --
function _novaCelulaRolo(cor, valor) {
  var c = document.createElement('input');
  c.type = 'text';
  c.inputMode = 'decimal';
  c.className = 'aloc-cel';
  c.dataset.cor = cor;
  c.style.cssText = 'width:64px;padding:5px 6px;border:1px solid var(--bd2);border-radius:var(--r);font-size:12px;text-align:right';
  if (valor !== undefined && valor !== null) c.value = String(valor).replace('.', ',');
  c.addEventListener('input', _onCelulaRoloInput);
  c.addEventListener('paste', _onCelulaRoloPaste);
  return c;
}

function _lerCelulasCor(cellsEl) {
  var out = [];
  if (!cellsEl) return out;
  cellsEl.querySelectorAll('.aloc-cel').forEach(function(c) {
    var v = parseFloat(String(c.value).trim().replace(',', '.'));
    if (!isNaN(v) && v > 0) out.push(v);   // compacta: ignora vazias/invalidas
  });
  return out;
}

function _onCelulaRoloInput(e) {
  var c = e.target;
  var cells = c.parentNode;          // div.aloc-cels
  var cor = c.dataset.cor;
  _rolosPorCor[cor] = _lerCelulasCor(cells);
  // auto-crescer: se a celula editada e a ultima e tem valor, anexa nova vazia
  var todas = cells.querySelectorAll('.aloc-cel');
  if (c === todas[todas.length - 1] && String(c.value).trim() !== '') {
    cells.appendChild(_novaCelulaRolo(cor));
  }
}

function _onCelulaRoloPaste(e) {
  var texto = (e.clipboardData || window.clipboardData).getData('text');
  var vals = _parseRolos(texto);
  if (vals.length <= 1) return;        // 1 valor: deixa o paste normal da celula
  e.preventDefault();
  var c = e.target;
  var cells = c.parentNode;
  var cor = c.dataset.cor;
  var inputs = Array.prototype.slice.call(cells.querySelectorAll('.aloc-cel'));
  var idx = inputs.indexOf(c);
  vals.forEach(function(v, k) {
    var alvo = inputs[idx + k];
    if (!alvo) { alvo = _novaCelulaRolo(cor); cells.appendChild(alvo); inputs.push(alvo); }
    alvo.value = String(v).replace('.', ',');
  });
  _rolosPorCor[cor] = _lerCelulasCor(cells);
  var todas = cells.querySelectorAll('.aloc-cel');
  if (String(todas[todas.length - 1].value).trim() !== '') cells.appendChild(_novaCelulaRolo(cor));
}
```

- [ ] **Step 2: Remove the `valoresSalvos` snapshot**

In `atualizarCoresAlocacao`, replace this block (lines 1916-1923):

```javascript
  // Salvar valores atuais antes de reconstruir
  var valoresSalvos = {};
  lista.querySelectorAll('[data-cor]').forEach(function(el) {
    var inp = el.querySelector('input');
    if (inp && inp.value.trim()) valoresSalvos[el.dataset.cor] = inp.value;
  });

  lista.innerHTML = '';
```

with (the snapshot is obsolete — `_rolosPorCor` is the source of truth; and reading `el.querySelector('input')` would only capture the first cell):

```javascript
  lista.innerHTML = '';
```

- [ ] **Step 3: Replace the per-color row render with cells**

In `atualizarCoresAlocacao`, replace the whole `coresDisponiveis.forEach(...)` block (lines 1925-1959, from `coresDisponiveis.forEach(function(cor) {` through its closing `});`):

```javascript
  coresDisponiveis.forEach(function(cor) {
    var valAtual = valoresSalvos[cor]
      || ((_rolosPorCor[cor] || []).length ? (_rolosPorCor[cor]).join('; ') : '');

    var row = document.createElement('div');
    row.dataset.cor = cor;
    row.style.cssText = 'display:grid;grid-template-columns:140px 1fr auto;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--bd1)';

    var lbl = document.createElement('span');
    lbl.textContent = cor;
    lbl.style.cssText = 'font-weight:600;font-size:12px;color:var(--tx)';

    var inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = 'comprimentos (separe por ;), ex: 87,5; 142; 60';
    inp.value = valAtual;
    inp.style.cssText = 'padding:5px 8px;border:1px solid var(--bd2);border-radius:var(--r);font-size:12px;width:100%';
    inp.addEventListener('input', function() {
      _rolosPorCor[cor] = _parseRolos(this.value);
    });

    var btn = document.createElement('button');
    btn.className = 'btn btn-s btn-sm';
    btn.textContent = '×';
    btn.style.cssText = 'padding:3px 8px;flex-shrink:0';
    btn.addEventListener('click', function() {
      delete _rolosPorCor[cor];
      row.remove();
    });

    row.appendChild(lbl);
    row.appendChild(inp);
    row.appendChild(btn);
    lista.appendChild(row);
  });
```

with (cells row; 8 minimum + always 1 trailing empty; a manual `+` button alongside the remove `x`):

```javascript
  coresDisponiveis.forEach(function(cor) {
    var arr = _rolosPorCor[cor] || [];

    var row = document.createElement('div');
    row.dataset.cor = cor;
    row.style.cssText = 'display:grid;grid-template-columns:140px 1fr auto;align-items:start;gap:8px;padding:4px 0;border-bottom:1px solid var(--bd1)';

    var lbl = document.createElement('span');
    lbl.textContent = cor;
    lbl.style.cssText = 'font-weight:600;font-size:12px;color:var(--tx);padding-top:6px';

    var cells = document.createElement('div');
    cells.className = 'aloc-cels';
    cells.dataset.cor = cor;
    cells.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px';
    var n = Math.max(8, arr.length + 1);
    for (var i = 0; i < n; i++) cells.appendChild(_novaCelulaRolo(cor, arr[i]));

    var acoes = document.createElement('div');
    acoes.style.cssText = 'display:flex;gap:4px;flex-shrink:0';

    var add = document.createElement('button');
    add.type = 'button';
    add.className = 'btn btn-s btn-sm';
    add.textContent = '+';
    add.title = 'Adicionar celula';
    add.style.cssText = 'padding:3px 8px';
    add.addEventListener('click', function() {
      var nova = _novaCelulaRolo(cor);
      cells.appendChild(nova);
      nova.focus();
    });

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-s btn-sm';
    btn.textContent = '×';
    btn.title = 'Remover cor';
    btn.style.cssText = 'padding:3px 8px';
    btn.addEventListener('click', function() {
      delete _rolosPorCor[cor];
      row.remove();
    });

    acoes.appendChild(add);
    acoes.appendChild(btn);
    row.appendChild(lbl);
    row.appendChild(cells);
    row.appendChild(acoes);
    lista.appendChild(row);
  });
```

(Note: this removes the now-undefined `valoresSalvos` reference — it was deleted in Step 2.)

- [ ] **Step 4: Read rolls directly from `_rolosPorCor` in `iniciarAlocacao`**

In `iniciarAlocacao`, replace the roll-collection block (lines 1977-1990):

```javascript
  var listaEl = document.getElementById('aloc-cores-lista');
  var rows = listaEl ? listaEl.querySelectorAll('[data-cor]') : [];
  var rolos = {};
  rows.forEach(function(row) {
    var cor = row.dataset.cor;
    var inp = row.querySelector('input[type=text]');
    if (inp) {
      var vals = _parseRolos(inp.value);
      if (vals.length) rolos[cor] = vals;
    }
  });
  Object.keys(_rolosPorCor).forEach(function(k){
    if (!rolos[k] && _rolosPorCor[k].length) rolos[k] = _rolosPorCor[k];
  });
```

with (fonte única `_rolosPorCor`, mantida em sincronia pelas células):

```javascript
  var rolos = {};
  Object.keys(_rolosPorCor).forEach(function(cor) {
    var vals = (_rolosPorCor[cor] || []).filter(function(n) { return n > 0; });
    if (vals.length) rolos[cor] = vals;
  });
```

(The validation line right after — `if (!Object.keys(rolos).length) { ... return; }` — stays unchanged.)

- [ ] **Step 5: Verify**

- Confirm the helpers were added, `valoresSalvos` no longer appears anywhere (`grep -n valoresSalvos interface.html` → empty), the new render uses `.aloc-cel`/`.aloc-cels`, and `iniciarAlocacao` reads `_rolosPorCor`.
- Confirm all new code is 100% ASCII and the JS braces/parens balance (e.g. count over the edited regions).
- Sanity: `python -m pytest tests/ -q` → 88 passed (Python unaffected).
- Manual (maintainer, later): calculate a plan; the allocation shows one row per color with 8 empty cells; type a length and Tab to the next; filling the last cell grows a new one; the `+` adds a cell; `×` removes the color; pasting `87,5; 142; 60` into a cell spreads into 3 cells; "Alocar Rolos" works as before. Re-rendering (e.g. recalculating) preserves typed values via `_rolosPorCor`.

- [ ] **Step 6: Commit**

```bash
git add interface.html
git commit -m "feat(ui): rolos por cor em celulas numericas (8+, Tab, auto-crescimento, colar lote)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente B
- [ ] `python -m pytest tests/ -q` → 88 passed (80 + 8 de tolerância).
- [ ] Manual: tolerância especial aceita `10%` e `-4`; G `Máx=0` continua.
- [ ] Manual: células de rolo (8, Tab, auto-cresce, `+`, `×`, colar lote); alocação funciona.
- [ ] Merge conforme o fluxo (branch `frente-b-entrada-ui` → `main`).

## Self-Review (autor do plano)
- **Cobertura do spec (Frente B):** B1 células (B-T3) ✓; B2 % nas tolerâncias — backend (B-T1) + frontend (B-T2) ✓; correção crítica de sinal do `lo` (só percentual nega) embutida no B-T1 e B-T2.
- **Sem placeholders:** todo step com código completo; old/new explícitos para cada Edit.
- **Consistência:** `_resolver_limite` (B-T1) e o formato `"N%"`/int casam entre `lerRegras` (B-T2) e `calcular_limites` (B-T1); helpers `_novaCelulaRolo`/`_lerCelulasCor`/`_onCelulaRoloInput`/`_onCelulaRoloPaste` e classes `.aloc-cel`/`.aloc-cels` usados consistentemente em B-T3; `_rolosPorCor` é a fonte única lida em `iniciarAlocacao`.
- **Drift:** se B-T3 for feito por último, B-T1/B-T2 não deslocam `interface.html` na região de rolos (tolerância está antes); ainda assim reconferir linhas antes de cada Edit.
