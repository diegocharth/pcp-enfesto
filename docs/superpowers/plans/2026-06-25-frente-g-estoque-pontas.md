# Frente G — Estoque de Pontas entre OPs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Persistir as pontas reaproveitáveis (ponta_classe=='estoque') de uma alocação e permitir reusá-las como insumo de uma alocação futura (de outra OP), com gerência manual no painel.

**Architecture:** Lógica pura testável + I/O fino no `main.py` (reusa `_salvar_json_atomico`). Arquivo `dados/estoque_pontas.json` = `{COR: [{id, comprimento_m, origem, data}]}`. Reuso entre OPs: o frontend (quando o checkbox "incluir estoque" está ligado) mescla os comprimentos do estoque nos `rolos[cor]` antes de chamar `/alocar_rolos` — o alocador NÃO muda (recebe mais "rolos"). Sem baixa automática na v1 (operador gerencia).

**Tech Stack:** Python stdlib, pytest; HTML/JS vanilla.

**Pré-requisitos:**
- Branch `frente-g-estoque-pontas` (de `main`, com A–F + F-1). Baseline: `cd "<proj>" && python -m pytest tests/ -q` → **105 passam**.
- **Encoding:** novo código em `interface.html` 100% ASCII.
- Ordem: G-T1 (backend, TDD) → G-T2 (frontend).

---

## Task G-T1: Backend — armazenamento + rotas do estoque

**Files:** Modify `main.py`. Test: `tests/test_estoque_pontas.py` (criar).

- [ ] **Step 1: Write the failing tests.** Create `tests/test_estoque_pontas.py`:

```python
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
    assert len(base["AZUL"]) == 1   # entrada original nao mutada


def test_remover_por_id():
    est = {"AZUL": [{"id": "a", "comprimento_m": 3.0}, {"id": "b", "comprimento_m": 4.0}]}
    novo = main._estoque_remover(est, "AZUL", "a")
    assert [e["id"] for e in novo["AZUL"]] == ["b"]


def test_carregar_inexistente_retorna_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ESTOQUE_PONTAS_FILE", str(tmp_path / "nao_existe.json"))
    assert main.carregar_estoque_pontas() == {}
```

- [ ] **Step 2: Run → FAIL** (`_estoque_adicionar`/`_estoque_remover`/`carregar_estoque_pontas`/`ESTOQUE_PONTAS_FILE` missing). `python -m pytest tests/test_estoque_pontas.py -v`.

- [ ] **Step 3: Implement in `main.py`.**
  - Add the constant in the `*_FILE` block (after `TEMPOS_FILE`, ~line 53):
    ```python
    ESTOQUE_PONTAS_FILE = os.path.join(BASE_DIR, "dados", "estoque_pontas.json")
    ```
  - Add `import uuid` near the top imports (if not already present).
  - Add the helpers near the other load/save helpers (after `salvar_params`, ~line 165). Use the existing `_salvar_json_atomico` and `_ensure_dados`:
    ```python
    def carregar_estoque_pontas():
        if os.path.exists(ESTOQUE_PONTAS_FILE):
            try:
                with open(ESTOQUE_PONTAS_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def salvar_estoque_pontas(estoque):
        _ensure_dados()
        _salvar_json_atomico(ESTOQUE_PONTAS_FILE, estoque)

    def _estoque_adicionar(estoque, resultado, origem="", agora=""):
        """Funcao pura: devolve (novo_estoque, n_adicionadas) acrescentando as
        pontas reaproveitaveis (ponta_classe=='estoque', ponta_m>0) do resultado."""
        novo = {c: list(v) for c, v in (estoque or {}).items()}
        n = 0
        for cor, cr in (resultado.get("por_cor") or {}).items():
            linhas = cr.get("sobras_por_rolo") or cr.get("rolos") or []
            for r in linhas:
                if r.get("ponta_classe") == "estoque" and float(r.get("ponta_m") or 0) > 0:
                    novo.setdefault(cor, [])
                    novo[cor].append({
                        "id": uuid.uuid4().hex[:8],
                        "comprimento_m": round(float(r["ponta_m"]), 3),
                        "origem": origem or "",
                        "data": agora or "",
                    })
                    n += 1
        return novo, n

    def _estoque_remover(estoque, cor, ponta_id):
        """Funcao pura: devolve o estoque sem a ponta de id `ponta_id` na cor."""
        novo = {c: list(v) for c, v in (estoque or {}).items()}
        if cor in novo:
            novo[cor] = [e for e in novo[cor] if e.get("id") != ponta_id]
            if not novo[cor]:
                del novo[cor]
        return novo
    ```

- [ ] **Step 4: Add the routes.**
  - GET `/estoque_pontas`: in `do_GET`, near the other GET routes (e.g. after `/aprendizado` or `/mapa_cores`), add:
    ```python
        elif path == "/estoque_pontas":
            self._send(200, {"estoque": carregar_estoque_pontas()})
    ```
  - POST `/estoque_pontas`: in `do_POST`'s routing block (the `if/elif` chain ~290-307), add:
    ```python
            elif path == "/estoque_pontas":      self._estoque_pontas(json.loads(body))
    ```
    and add the handler method to the Handler class (near `_alocar_rolos`):
    ```python
    def _estoque_pontas(self, p):
        import time
        acao = p.get("acao", "")
        est = carregar_estoque_pontas()
        if acao == "guardar":
            agora = time.strftime("%Y-%m-%d %H:%M")
            est, n = _estoque_adicionar(est, p.get("resultado", {}),
                                        origem=p.get("origem", ""), agora=agora)
            salvar_estoque_pontas(est)
            self._send(200, {"ok": True, "adicionadas": n, "estoque": est})
        elif acao == "remover":
            est = _estoque_remover(est, p.get("cor", ""), p.get("id", ""))
            salvar_estoque_pontas(est)
            self._send(200, {"ok": True, "estoque": est})
        elif acao == "limpar":
            cor = p.get("cor")
            est = {} if not cor else {c: v for c, v in est.items() if c != cor}
            salvar_estoque_pontas(est)
            self._send(200, {"ok": True, "estoque": est})
        else:
            self._send(400, {"erro": "acao invalida (use guardar/remover/limpar)."})
    ```

- [ ] **Step 5: Run tests + full suite.** `python -m pytest tests/test_estoque_pontas.py -v` → 5 PASS. `python -m pytest tests/ -q` → 110 passed (105 + 5).

- [ ] **Step 6: Commit.**
```
git add main.py tests/test_estoque_pontas.py
git commit -m "feat(estoque): armazenamento + rotas de estoque de pontas entre OPs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task G-T2: Frontend — painel + incluir estoque na alocação

**Files:** Modify `interface.html` (card de alocação ~302-351; `iniciarAlocacao` ~2008; novos helpers).

Sem teste JS — verificação manual + live smoke. ASCII.

- [ ] **Step 1: Add the panel + include-checkbox HTML.** No card de alocação (`#card-alocacao`), imediatamente ANTES de `<div id="aloc-resultado" ...>` (~line 351), inserir:
```html
  <!-- ESTOQUE DE PONTAS (entre OPs) -->
  <div style="margin-top:10px;border-top:1px solid var(--bd1);padding-top:8px">
    <label style="font-size:12px;cursor:pointer">
      <input type="checkbox" id="aloc-incluir-estoque"> Incluir estoque de pontas nesta alocacao
    </label>
    <details style="margin-top:6px">
      <summary style="cursor:pointer;font-size:12px;font-weight:600;color:var(--tx2)">Estoque de pontas</summary>
      <div id="aloc-estoque-lista" style="font-size:12px;margin-top:6px"></div>
      <div class="btn-row" style="margin-top:6px">
        <button type="button" class="btn btn-s btn-sm" onclick="_guardarEstoquePontas()">Guardar pontas reaproveitaveis desta alocacao</button>
      </div>
    </details>
  </div>
```

- [ ] **Step 2: Add the JS helpers** (perto de `iniciarAlocacao`, ~line 2007). Use `_rolosPorCor` and `window._ultimaAlocacao` (já existentes):
```javascript
// Frente G: estoque de pontas entre OPs
window._estoquePontas = window._estoquePontas || {};

async function _carregarEstoque() {
  try {
    var d = await (await fetch('/estoque_pontas')).json();
    window._estoquePontas = d.estoque || {};
  } catch(e) { window._estoquePontas = {}; }
  _renderEstoque();
}

function _renderEstoque() {
  var div = document.getElementById('aloc-estoque-lista');
  if (!div) return;
  var est = window._estoquePontas || {};
  var cores = Object.keys(est);
  if (!cores.length) { div.innerHTML = '<span style="color:var(--tx3)">Estoque vazio.</span>'; return; }
  var h = '';
  cores.forEach(function(cor) {
    h += '<div style="margin-bottom:4px"><b>' + cor + ':</b> ';
    h += (est[cor] || []).map(function(e) {
      return '<span style="display:inline-block;margin:2px;padding:2px 6px;background:var(--sf2);border-radius:var(--r)">'
        + e.comprimento_m + 'm'
        + (e.origem ? ' <span style="color:var(--tx3)">(' + e.origem + ')</span>' : '')
        + ' <a href="#" onclick="_removerPontaEstoque(\'' + cor + '\',\'' + e.id + '\');return false;" '
        + 'style="color:var(--er);text-decoration:none">x</a></span>';
    }).join('');
    h += '</div>';
  });
  div.innerHTML = h;
}

async function _guardarEstoquePontas() {
  if (!window._ultimaAlocacao) { alert('Faca uma alocacao primeiro.'); return; }
  var body = {acao: 'guardar', resultado: window._ultimaAlocacao.data,
              origem: window._ultimaAlocacao.referencia || ''};
  var d = await (await fetch('/estoque_pontas', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json();
  window._estoquePontas = d.estoque || {};
  _renderEstoque();
  alert((d.adicionadas || 0) + ' ponta(s) guardada(s) no estoque.');
}

async function _removerPontaEstoque(cor, id) {
  var d = await (await fetch('/estoque_pontas', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({acao: 'remover', cor: cor, id: id})})).json();
  window._estoquePontas = d.estoque || {};
  _renderEstoque();
}
```

- [ ] **Step 3: Merge estoque into the allocation when the checkbox is on.** Em `iniciarAlocacao` (~2008), DEPOIS de montar `rolos` a partir de `_rolosPorCor` (o bloco do B-T3: `Object.keys(_rolosPorCor).forEach(...)`) e ANTES da validação `if (!Object.keys(rolos).length)`, inserir:
```javascript
  var incl = document.getElementById('aloc-incluir-estoque');
  if (incl && incl.checked) {
    var est = window._estoquePontas || {};
    Object.keys(est).forEach(function(cor) {
      var extras = (est[cor] || []).map(function(e) { return +e.comprimento_m; }).filter(function(n) { return n > 0; });
      if (extras.length) rolos[cor] = (rolos[cor] || []).concat(extras);
    });
  }
```

- [ ] **Step 4: Load the estoque on startup.** Encontrar onde `atualizarCoresAlocacao()` é chamado no boot/carregamento (ou o `window.onload`/`carregarDados`), e adicionar uma chamada `_carregarEstoque();` no boot (uma vez), para o painel já vir preenchido. Se não houver um ponto óbvio, chamar `_carregarEstoque()` ao final de `atualizarCoresAlocacao()`.

- [ ] **Step 5: Verify.**
  - Novo código 100% ASCII; JS balanceado.
  - `python -m pytest tests/ -q` → 110 passed (Python intacto).
  - Manual: alocar → "Guardar pontas..." adiciona as pontas estoque ao painel; recarregar a página mantém o estoque; marcar "Incluir estoque" e alocar de novo → as pontas entram como rolos extras; "x" remove uma ponta.

- [ ] **Step 6: Commit.**
```
git add interface.html
git commit -m "feat(ui): painel de estoque de pontas + incluir estoque na alocacao

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente G
- [ ] `python -m pytest tests/ -q` → 110 passed.
- [ ] Live smoke: GET /estoque_pontas; POST guardar (de uma alocação real) → estoque cresce; POST remover → encolhe.
- [ ] Merge `frente-g-estoque-pontas` → `main` (ff) + remover branch + push do código.

## Self-Review (autor)
- **Cobertura:** estoque persistente (`estoque_pontas.json`) + guardar/remover/limpar + reuso via merge de rolos no front. Complementa C (corte separado dentro da OP) com reuso ENTRE OPs (#8 na forma completa).
- **Sem placeholders:** backend com código completo + testes puros; frontend com helpers completos.
- **Risco:** baixo — backend aditivo (novas rotas/arquivo, não toca solver/alocador); o reuso é só mesclar comprimentos nos `rolos` (o alocador já lida com isso). Sem baixa automática (v1) — documentado.
