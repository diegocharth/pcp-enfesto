# Frente C — Alocação de Rolos (núcleo) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando sobra déficit numa cor, sugerir um corte separado a partir das pontas reaproveitáveis (em vez de mandar comprar tecido), reportar as sobras por rolo, permitir re-entrada do comprimento real do Audaces, e gerar um relatório de alocação para impressão (PDF via navegador).

**Architecture:** Núcleo testável no backend — novo módulo `engine/reaproveitamento.py` (função pura `sugerir_corte_separado`) chamado por `alocar_rolos` como passo pós-alocação que apenas **anexa** chaves ao resultado (não altera o plano nem a alocação principal FFD). A UI lê essas chaves novas para renderizar sugestões + tabela de sobras, oferece campos de comprimento real do Audaces, e abre uma print-view HTML (`window.print()`).

**Tech Stack:** Python 3.10+ stdlib, pytest; HTML/CSS/JS vanilla. Sem dependência nova (PDF via navegador).

**Pré-requisitos / ordem:**
- Branch `frente-c-alocacao` (a partir de `main`, que já tem A + B).
- Baseline: `cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos" && python -m pytest tests/ -q` → **88 passam**.
- **Encoding:** novo código em `interface.html` 100% ASCII (entidades; sem acento cru). Editar com Edit.
- Ordem: C-T1 → C-T2 (backend, TDD) → C-T3 → C-T4 → C-T5 (UI) → C-T6 (xlsx). Backend primeiro (testável e fornece os dados).
- Premissas confirmadas no código (`engine/alocador_rolos.py`): `comp_camada_por_id` (142-153), déficit por cor `camadas_em_deficit` chaves int (304), pontas por rolo `ponta_m`/`ponta_classe` (289-301), margem 1× por sub-enfesto (272), `comp_camada_m` explícito por mapa honrado (148), e o ramo "sem rolos" monta `resultado_por_cor[cor]` separado (184-194). **Nada disto é alterado** — só anexamos chaves.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `engine/reaproveitamento.py` (novo) | `sugerir_corte_separado(...)` — função pura: dado o déficit e as pontas reaproveitáveis de uma cor, monta cortes avulsos que cabem nas pontas (sem emenda). Sem I/O, sem estado. |
| `engine/alocador_rolos.py` | Chama `sugerir_corte_separado` por cor e anexa `sugestoes_corte_separado`; anexa `sobras_por_rolo` por cor e `sobras_consolidado`/`sugestoes_corte_total` em `resumo_geral`. Inclui o ramo "sem rolos". |
| `tests/test_reaproveitamento.py` (novo) | Testa o algoritmo isolado (cabe/não cabe com margem, submapa reduzido, sem ponta, várias pontas). |
| `tests/test_alocador_rolos.py` | + testes de integração (chaves anexadas, ramo sem-rolos). |
| `interface.html` | C-T3 render (sugestões + sobras), C-T4 (campo comprimento real Audaces + repasse em `_montarPlanoParaAlocacao`), C-T5 (`abrirRelatorioAlocacao` print-view). |
| `exportar/export_xlsx.py` | C-T6 (opcional): seções "Sobras por rolo" e "Corte separado" na aba da cor. |

---

## Task C-T1: `engine/reaproveitamento.py` — corte separado a partir das pontas

**Files:**
- Create: `engine/reaproveitamento.py`
- Modify: `engine/alocador_rolos.py` (integração antes do `return`, e no ramo "sem rolos")
- Test: `tests/test_reaproveitamento.py` (criar)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reaproveitamento.py`:

```python
"""C1: sugerir_corte_separado monta cortes avulsos que cabem nas pontas
reaproveitaveis (sem emenda), cobrindo deficit sem comprar tecido."""
from engine.reaproveitamento import sugerir_corte_separado

# Mapa 0: 6 pecas, camada 7.8m (consumo/peca = 1.3). Composicao P=3,M=3.
COMP = {0: 7.8}
COMPOS = {0: {"P": 3, "M": 3}}
CPP = {0: 1.3}
MARGEM = 0.10


def test_sem_pontas_nao_sugere():
    sugs = sugerir_corte_separado({0: 2}, COMP, COMPOS, CPP, [], MARGEM)
    assert sugs == []


def test_camada_inteira_cabe_em_ponta():
    # ponta de 8.0m: cabe floor((8.0-0.10)/7.8)=1 camada inteira.
    sugs = sugerir_corte_separado({0: 1}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 1, "ponta_m": 8.0}], MARGEM)
    assert len(sugs) == 1
    s = sugs[0]
    assert s["mapa_id"] == 0
    assert s["rotulo"] == "camada inteira"
    assert s["camadas_cobertas"] == 1
    assert s["deficit_residual_camadas"] == 0
    assert s["cortes"][0]["rolo_origem_indice"] == 1
    assert s["cortes"][0]["n_camadas"] == 1


def test_margem_respeitada_nao_gera_emenda():
    # ponta de 7.85m cabe 7.8 de camada, mas NAO 7.8+0.10=7.90 -> 0 camadas inteiras.
    # Como a camada inteira nao cabe, tenta submapa reduzido (metade: 3 pecas=3.9m;
    # 3.9+0.10=4.0 <= 7.85 -> cabe 1). Deve sugerir o submapa, nunca exceder a ponta.
    sugs = sugerir_corte_separado({0: 1}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 0, "ponta_m": 7.85}], MARGEM)
    assert len(sugs) == 1
    s = sugs[0]
    assert s["rotulo"] != "camada inteira"      # caiu no submapa reduzido
    # capacidade respeitada: comp_total <= ponta
    assert s["cortes"][0]["comp_total"] <= 7.85 + 1e-9


def test_varias_camadas_numa_ponta_uma_margem():
    # ponta 24.0m, camada 7.8m: floor((24.0-0.10)/7.8)=3 camadas, 1 margem.
    sugs = sugerir_corte_separado({0: 5}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 0, "ponta_m": 24.0}], MARGEM)
    s = sugs[0]
    assert s["cortes"][0]["n_camadas"] == 3
    assert s["cortes"][0]["comp_total"] == round(3 * 7.8 + 0.10, 4)
    assert s["deficit_residual_camadas"] == 2   # 5 - 3 ainda faltam


def test_combina_varias_pontas_sem_emenda():
    # duas pontas de 8.0m, deficit 2 camadas: cada ponta cobre 1 (cada uma seu sub-enfesto).
    sugs = sugerir_corte_separado({0: 2}, COMP, COMPOS, CPP,
                                  [{"rolo_origem_indice": 0, "ponta_m": 8.0},
                                   {"rolo_origem_indice": 1, "ponta_m": 8.0}], MARGEM)
    s = sugs[0]
    assert s["camadas_cobertas"] == 2
    assert len(s["cortes"]) == 2
    assert s["deficit_residual_camadas"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reaproveitamento.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.reaproveitamento'`.

- [ ] **Step 3: Create the module**

Create `engine/reaproveitamento.py`:

```python
"""
PCP Enfestos -- Reaproveitamento de pontas (corte separado) v1.0
================================================================

Passo POS-ALOCACAO. Nao altera o plano de corte nem a alocacao principal.
Quando sobra deficit numa cor, tenta cobri-lo cortando pecas avulsas nas
PONTAS reaproveitaveis (>= ponta_minima_util) que ja sobraram nos rolos
daquela cor -- evitando comprar tecido novo.

Regras:
  - Sem emenda: cada conjunto de k camadas e casado contra UMA ponta individual
    (nunca soma duas pontas numa mesma camada).
  - Margem de faca: paga UMA vez por sub-enfesto (k*comp + margem <= ponta).
  - Candidatos por mapa em deficit, do maior para o menor comprimento:
      1) camada inteira do mapa;
      2) submapa reduzido (metade; 1-de-cada) -- so quando a camada inteira
         nao cabe em nenhuma ponta.
"""

import math

_EPS = 0.0001


def _gerar_candidatos(mid, comp_camada_por_id, composicao_por_id, cpp_por_id):
    """Lista [(comp_m, composicao, rotulo)] do maior para o menor comprimento."""
    base = composicao_por_id.get(mid, {}) or {}
    cpp = float(cpp_por_id.get(mid, 0.0))
    cands = [(float(comp_camada_por_id.get(mid, 0.0)), dict(base), "camada inteira")]
    total_base = sum(base.values())

    meia = {t: int(round(q / 2.0)) for t, q in base.items() if int(round(q / 2.0)) > 0}
    if meia and sum(meia.values()) < total_base and cpp > 0:
        cands.append((sum(meia.values()) * cpp, meia, "metade"))

    umdecada = {t: 1 for t, q in base.items() if q > 0}
    if umdecada and sum(umdecada.values()) < total_base and cpp > 0:
        cands.append((sum(umdecada.values()) * cpp, umdecada, "1 de cada"))

    # Maior comprimento primeiro (mais fiel a grade).
    cands.sort(key=lambda c: -c[0])
    return cands


def sugerir_corte_separado(deficit, comp_camada_por_id, composicao_por_id,
                           cpp_por_id, pontas, margem):
    """
    Args:
        deficit: {mapa_id(int): n_camadas_faltantes(int)}
        comp_camada_por_id: {mapa_id: comprimento_camada_m}
        composicao_por_id:  {mapa_id: {tam: qtd}}
        cpp_por_id:         {mapa_id: comprimento_por_peca_m}
        pontas: [{"rolo_origem_indice": int, "ponta_m": float}, ...] (pontas estoque da cor)
        margem: float (margem de faca por sub-enfesto)
    Returns:
        [{"mapa_id","rotulo","composicao","comp_camada","camadas_cobertas",
          "cortes":[{"rolo_origem_indice","n_camadas","comp_camada","comp_total","ponta_usada_m"}],
          "deficit_residual_camadas"}]
    """
    margem = float(margem)
    # copia mutavel das pontas (consumimos comprimento ao alocar cortes)
    rem = [[int(p["rolo_origem_indice"]), float(p["ponta_m"])] for p in pontas]
    rem.sort(key=lambda x: -x[1])  # maiores primeiro (FFD)

    sugestoes = []
    # mapas em deficit, camada maior primeiro
    for mid in sorted((m for m, n in deficit.items() if n > 0),
                      key=lambda m: -comp_camada_por_id.get(m, 0.0)):
        n_falta = int(deficit[mid])
        candidatos = _gerar_candidatos(mid, comp_camada_por_id, composicao_por_id, cpp_por_id)
        for comp, compos_sub, rotulo in candidatos:
            if comp <= 0 or n_falta <= 0:
                continue
            cortes = []
            for slot in rem:
                if n_falta <= 0:
                    break
                k = int(math.floor((slot[1] - margem + _EPS) / comp))
                if k <= 0:
                    continue
                k = min(k, n_falta)
                comp_total = round(k * comp + margem, 4)
                cortes.append({
                    "rolo_origem_indice": slot[0],
                    "n_camadas": k,
                    "comp_camada": round(comp, 4),
                    "comp_total": comp_total,
                    "ponta_usada_m": round(slot[1], 4),
                })
                slot[1] -= (k * comp + margem)
                n_falta -= k
            if cortes:
                sugestoes.append({
                    "mapa_id": mid,
                    "rotulo": rotulo,
                    "composicao": compos_sub,
                    "comp_camada": round(comp, 4),
                    "camadas_cobertas": sum(c["n_camadas"] for c in cortes),
                    "cortes": cortes,
                    "deficit_residual_camadas": n_falta,
                })
                break  # aceita o melhor candidato deste mapa
    return sugestoes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reaproveitamento.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Integrate into `alocar_rolos`**

In `engine/alocador_rolos.py`, add the import at the top (after `import math`):

```python
from engine.reaproveitamento import sugerir_corte_separado
```

Build the per-map helpers ONCE, right after `comp_camada_por_id` is computed (after the loop ending ~line 153). Insert:

```python
    composicao_por_id = {}
    cpp_por_id = {}
    for m in mapas_plano:
        mid_ = int(m["id"])
        composicao_por_id[mid_] = dict(m.get("composicao", {}))
        n_pecs = int(m.get("n_pecas", sum(m.get("composicao", {}).values()))) or 1
        cpp_por_id[mid_] = round(comp_camada_por_id.get(mid_, 0.0) / n_pecs, 6)
```

Then, where the per-color result dict is built for the NORMAL case (the block `resultado_por_cor[cor] = { ... }` around lines 329-339), add the suggestions. Right BEFORE that assignment, compute:

```python
        pontas_estoque = [
            {"rolo_origem_indice": r["indice"], "ponta_m": r["ponta_m"]}
            for r in rolos_resultado if r["ponta_classe"] == "estoque" and r["ponta_m"] > 0
        ]
        sugestoes_cs = sugerir_corte_separado(
            deficit, comp_camada_por_id, composicao_por_id, cpp_por_id,
            pontas_estoque, margem
        ) if deficit else []
```

and add to the `resultado_por_cor[cor]` dict the key:

```python
            "sugestoes_corte_separado" : sugestoes_cs,
```

In the "sem rolos" branch (lines 184-194), add to that dict:

```python
            "sugestoes_corte_separado" : [],
```

Finally, in `resumo_geral` (around lines 356-364), add:

```python
        "sugestoes_corte_total"   : sum(
            len(res.get("sugestoes_corte_separado", []))
            for res in resultado_por_cor.values()
        ),
```

- [ ] **Step 6: Add an integration test to `tests/test_alocador_rolos.py`**

```python
def test_alocacao_anexa_sugestoes_corte_separado():
    """C1: cor com deficit e ponta reaproveitavel recebe sugestoes_corte_separado."""
    plano = {
        "mapas": [{"id": 0, "n_pecas": 6, "composicao": {"P": 3, "M": 3}}],
        "camadas": {"AZUL": {0: 5}},   # demanda 5 camadas
        "consumo_peca": 1.3,           # camada 7.8m
    }
    # 1 rolo de 30m: cabe floor((30*0.97 - margem)/7.8) camadas; sobra ponta;
    # mas 5 camadas nao cabem -> deficit + ponta estoque -> deve sugerir corte separado.
    cfg = dict(CONFIG_BASE)
    cfg["folga_incerteza_pct"] = 0.03
    res = alocar_rolos(plano, {"AZUL": [30.0]}, cfg)
    cr = res["por_cor"]["AZUL"]
    assert "sugestoes_corte_separado" in cr
    assert "sugestoes_corte_total" in res["resumo_geral"]


def test_sem_rolos_tem_chaves_vazias():
    """C1: cor sem rolos nao quebra a UI (chave presente, vazia)."""
    plano = {"mapas": [{"id": 0, "n_pecas": 4, "composicao": {"P": 4}}],
             "camadas": {"AZUL": {0: 2}}, "consumo_peca": 1.0}
    res = alocar_rolos(plano, {}, dict(CONFIG_BASE))
    assert res["por_cor"]["AZUL"]["sugestoes_corte_separado"] == []
```

- [ ] **Step 7: Run full suite + commit**

Run: `python -m pytest tests/ -q` → 95 passed (88 + 5 + 2).

```bash
git add engine/reaproveitamento.py engine/alocador_rolos.py tests/test_reaproveitamento.py tests/test_alocador_rolos.py
git commit -m "feat(alocador): corte separado a partir das pontas (reaproveitamento)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task C-T2: Relatório de sobras por rolo

**Files:**
- Modify: `engine/alocador_rolos.py` (anexar `sobras_por_rolo` por cor; `sobras_consolidado` em `resumo_geral`)
- Test: `tests/test_alocador_rolos.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_alocador_rolos.py`:

```python
def test_sobras_por_rolo_e_consolidado():
    """C3: cada cor expoe sobras_por_rolo; resumo_geral expoe sobras_consolidado."""
    plano = {"mapas": [{"id": 0, "n_pecas": 4, "composicao": {"P": 4}}],
             "camadas": {"AZUL": {0: 2}}, "consumo_peca": 1.0}
    res = alocar_rolos(plano, {"AZUL": [20.0]}, dict(CONFIG_BASE))
    cr = res["por_cor"]["AZUL"]
    assert "sobras_por_rolo" in cr and len(cr["sobras_por_rolo"]) == 1
    s = cr["sobras_por_rolo"][0]
    for k in ("rolo_indice", "nominal_m", "seguro_m", "usado_m", "ponta_m",
              "ponta_classe", "reaproveitada_em"):
        assert k in s
    assert "sobras_consolidado" in res["resumo_geral"]
    assert "AZUL" in res["resumo_geral"]["sobras_consolidado"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_alocador_rolos.py::test_sobras_por_rolo_e_consolidado -v`
Expected: FAIL with `KeyError: 'sobras_por_rolo'` / `assert 'sobras_por_rolo' in cr`.

- [ ] **Step 3: Implement**

In `engine/alocador_rolos.py`, before the NORMAL `resultado_por_cor[cor] = {...}` assignment, compute:

```python
        sobras_por_rolo = [
            {
                "rolo_indice"  : r["indice"] + 1,
                "nominal_m"    : r["comprimento_nominal_m"],
                "seguro_m"     : r["comprimento_seguro_m"],
                "usado_m"      : r["usado_m"],
                "ponta_m"      : r["ponta_m"],
                "ponta_classe" : r["ponta_classe"],
                "reaproveitada_em": None,
            }
            for r in rolos_resultado
        ]
```

and add to the per-color dict:

```python
            "sobras_por_rolo"          : sobras_por_rolo,
```

In the "sem rolos" branch add `"sobras_por_rolo": []`.

In `resumo_geral`, add:

```python
        "sobras_consolidado"      : {
            c: {
                "ponta_estoque_m"  : res["ponta_estoque_total_m"],
                "refugo_m"         : res["refugo_real_m"],
                "n_pontas_estoque" : sum(
                    1 for s in res.get("sobras_por_rolo", [])
                    if s["ponta_classe"] == "estoque" and s["ponta_m"] > 0
                ),
            }
            for c, res in resultado_por_cor.items()
        },
```

(Optional cross-link: when a ponta is consumed by a `sugestoes_corte_separado` corte, set the matching `sobras_por_rolo[i].reaproveitada_em` to the map label. Keep simple in v1: leave `None` and let the UI show the suggestion separately. Do NOT over-engineer.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_alocador_rolos.py -v` → all PASS.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest tests/ -q` → 96 passed.

```bash
git add engine/alocador_rolos.py tests/test_alocador_rolos.py
git commit -m "feat(alocador): sobras por rolo + consolidado no resumo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task C-T3: Render das sugestões + sobras na UI

**Files:**
- Modify: `interface.html` (`_renderResultadoAlocacao` ~2201; novos helpers)

Sem teste JS — verificação manual + revisão. ASCII.

- [ ] **Step 1: Add render helpers (before `_renderResultadoAlocacao`, ~line 2200)**

```javascript
function _htmlCorteSeparado(cr) {
  var sugs = cr.sugestoes_corte_separado || [];
  if (!sugs.length) return '';
  var h = '<div style="margin-top:6px;background:var(--okb);border:1px solid var(--ok);border-radius:var(--r);padding:6px;font-size:12px">';
  h += '<b style="color:var(--ok)">Corte separado sugerido (usa as pontas):</b>';
  sugs.forEach(function(s) {
    var compos = Object.keys(s.composicao||{}).map(function(t){ return s.composicao[t]+t; }).join('+');
    h += '<div style="padding:3px 0">';
    h += 'Mapa ' + s.mapa_id + ' (' + s.rotulo + ': ' + compos + ', ' + s.comp_camada + 'm): ';
    h += (s.cortes||[]).map(function(c){
      return c.n_camadas + ' camada(s) na ponta do rolo ' + (c.rolo_origem_indice+1) +
             ' (' + c.ponta_usada_m + 'm)';
    }).join('; ');
    if (s.deficit_residual_camadas > 0) {
      h += ' &mdash; ainda faltam ' + s.deficit_residual_camadas + ' camada(s).';
    }
    h += '</div>';
  });
  h += '</div>';
  return h;
}

function _htmlSobrasPorRolo(cr) {
  var sob = cr.sobras_por_rolo || [];
  if (!sob.length) return '';
  var h = '<div style="margin-top:6px;font-size:11px"><b>Sobras por rolo:</b>';
  h += '<table style="width:100%;border-collapse:collapse;margin-top:3px">';
  h += '<tr style="color:var(--tx2)"><td>Rolo</td><td>Usado</td><td>Ponta</td><td>Classe</td></tr>';
  sob.forEach(function(s) {
    var cor = s.ponta_classe === 'estoque' ? 'var(--ok)' : 'var(--er)';
    h += '<tr><td>' + s.rolo_indice + '</td><td>' + s.usado_m + 'm</td>'
       + '<td style="color:' + cor + '">' + s.ponta_m + 'm</td><td>' + s.ponta_classe + '</td></tr>';
  });
  h += '</table></div>';
  return h;
}
```

- [ ] **Step 2: Call them inside the per-color `<details>`**

In `_renderResultadoAlocacao`, inside the `corList.forEach`, AFTER the déficit block (the `if (Object.keys(cr.camadas_em_deficit||{}).length) { ... }` that ends ~line 2253) and BEFORE `html += '</div></details>';` (line 2254), insert:

```javascript
    html += _htmlCorteSeparado(cr);
    html += _htmlSobrasPorRolo(cr);
```

- [ ] **Step 3: Verify**

- New code ASCII; braces balanced; `python -m pytest tests/ -q` → 96 (Python unaffected).
- Manual: alocar com déficit cobrível por pontas → aparece o bloco "Corte separado sugerido" e a tabela de sobras dentro do detalhe da cor.

- [ ] **Step 4: Commit**

```bash
git add interface.html
git commit -m "feat(ui): exibe corte separado sugerido e sobras por rolo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task C-T4: Re-entrada do comprimento real do Audaces

**Files:**
- Modify: `interface.html` (`_montarPlanoParaAlocacao` ~2086; nova UI de mapas + `window._compRealAudaces`; `iniciarAlocacao` para re-alocar)

Sem teste JS — manual. ASCII. O backend já honra `comp_camada_m` (alocador linha 148), então é só repassar.

- [ ] **Step 1: Add a per-map "comprimento real" UI builder**

Add a helper that renders the maps with editable real-length inputs. Insert before `_montarPlanoParaAlocacao` (~line 2085):

```javascript
// C2: comprimento real do mapa (Audaces) por id. Vazio = usa o calculado.
window._compRealAudaces = window._compRealAudaces || {};

function _renderMapasAudaces() {
  var box = document.getElementById('aloc-mapas-audaces');
  if (!box) return;
  var plano = _montarPlanoParaAlocacao();
  if (!plano) { box.innerHTML = ''; return; }
  var h = '<div style="font-size:12px;font-weight:600;color:var(--tx2);margin:8px 0 4px">'
        + 'Comprimento real dos mapas (Audaces) &mdash; vazio usa o calculado:</div>';
  plano.mapas.forEach(function(m) {
    var calc = m.comp_camada_m;
    var real = window._compRealAudaces[m.id];
    h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;font-size:12px">';
    h += '<span style="width:160px">Mapa ' + m.id + ' (' + m.n_pecas + ' pc, calc ' + calc + 'm)</span>';
    h += '<input type="text" inputmode="decimal" class="aloc-audaces" data-mid="' + m.id + '" '
       + 'value="' + (real !== undefined && real !== null ? String(real).replace('.', ',') : '') + '" '
       + 'placeholder="real (m)" style="width:90px;padding:4px 6px;border:1px solid var(--bd2);border-radius:var(--r)">';
    h += '</div>';
  });
  box.innerHTML = h;
  box.querySelectorAll('.aloc-audaces').forEach(function(inp) {
    inp.addEventListener('input', function() {
      var v = parseFloat(String(this.value).trim().replace(',', '.'));
      var mid = parseInt(this.dataset.mid, 10);
      if (!isNaN(v) && v > 0) window._compRealAudaces[mid] = v;
      else delete window._compRealAudaces[mid];
    });
  });
}
```

Add the container in the allocation card. In the HTML, immediately AFTER the `#aloc-rolos-por-cor` block's closing and BEFORE the "Alocar Rolos" button row (locate `<button class="btn btn-p" onclick="iniciarAlocacao()">`), insert:

```html
  <div id="aloc-mapas-audaces"></div>
```

Call `_renderMapasAudaces()` at the end of `atualizarCoresAlocacao()` (so the maps list refreshes when a plan is calculated). Add this as the last line before its closing `}`:

```javascript
  _renderMapasAudaces();
```

- [ ] **Step 2: Apply the real length in `_montarPlanoParaAlocacao`**

In `_montarPlanoParaAlocacao`, the two `mapas.push({...comp_camada_m:...})` lines (single ~2101, multi ~2119) must use the real value when present. Replace:

Single (`addGrupoSingle`, line ~2101):
```javascript
      mapas.push({id:mid, composicao:m, n_pecas:np, comp_camada_m:+(np*consumo).toFixed(4)});
```
with:
```javascript
      var _calcS=+(np*consumo).toFixed(4), _realS=(window._compRealAudaces||{})[mid];
      mapas.push({id:mid, composicao:m, n_pecas:np, comp_camada_m:(_realS>0?+(+_realS).toFixed(4):_calcS)});
```

Multi (`addGrupoMulti`, line ~2119):
```javascript
      mapas.push({id:mid, composicao:compos, n_pecas:np, comp_camada_m:+((comps[k]||0)).toFixed(4)});
```
with:
```javascript
      var _calcM=+((comps[k]||0)).toFixed(4), _realM=(window._compRealAudaces||{})[mid];
      mapas.push({id:mid, composicao:compos, n_pecas:np, comp_camada_m:(_realM>0?+(+_realM).toFixed(4):_calcM)});
```

**Atenção:** o `mid` é sequencial 0..n reatribuído a cada chamada de `_montarPlanoParaAlocacao`. Como `_renderMapasAudaces` também chama `_montarPlanoParaAlocacao` para listar, os ids batem desde que a montagem seja determinística (é — mesma ordem de grupos/mapas). Re-alocar usa o mesmo `iniciarAlocacao()`.

- [ ] **Step 3: Verify**

- ASCII; braces balanced; `python -m pytest tests/ -q` → 96.
- Manual: calcular plano → a lista de mapas aparece com o comprimento calculado; preencher um "real" e clicar "Alocar Rolos" → a alocação usa o valor real (o `body.plano.mapas[i].comp_camada_m` reflete o real). Limpar o campo volta ao calculado.

- [ ] **Step 4: Commit**

```bash
git add interface.html
git commit -m "feat(ui): re-entrada do comprimento real do Audaces por mapa

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task C-T5: Relatório de alocação para impressão (print-view)

**Files:**
- Modify: `interface.html` (`abrirRelatorioAlocacao` nova; botão em `_renderResultadoAlocacao`)

Sem teste JS — manual. ASCII. Sem dependência: usa `window.print()`.

- [ ] **Step 1: Add `abrirRelatorioAlocacao` + HTML builder (near `exportarAlocacao`, ~line 2264)**

```javascript
function _htmlImpressaoAlocacao(d, ref) {
  var res = d.resumo_geral || {};
  var cores = Object.keys(d.por_cor || {});
  var h = '<html><head><meta charset="utf-8"><title>Alocacao ' + ref + '</title>';
  h += '<style>body{font-family:Arial,sans-serif;font-size:12px;color:#222;margin:18px}'
     + 'h1{font-size:18px}h2{font-size:14px;border-bottom:1px solid #999;margin-top:18px}'
     + 'table{border-collapse:collapse;width:100%;margin:4px 0}td,th{border:1px solid #ccc;padding:3px 6px;text-align:left}'
     + '.cor{page-break-inside:avoid}.def{color:#b00}.ok{color:#070}'
     + '@media print{button{display:none}}</style></head><body>';
  h += '<h1>Alocacao de Rolos &mdash; ' + ref + '</h1>';
  h += '<div>Tecido usado: ' + (+(res.tecido_usado_total_m||0)).toFixed(1) + 'm | '
     + 'Ponta estoque: ' + (+(res.ponta_estoque_total_m||0)).toFixed(1) + 'm | '
     + 'Refugo: ' + (+(res.refugo_real_total_m||0)).toFixed(1) + 'm | '
     + 'Sub-enfestos: ' + (res.n_sub_enfestos_total||0) + '</div>';

  cores.forEach(function(cor) {
    var cr = d.por_cor[cor];
    h += '<div class="cor"><h2>' + cor + '</h2>';
    // folhas por rolo em cada enfesto
    (cr.rolos||[]).forEach(function(r, ri) {
      h += '<div><b>Rolo ' + (ri+1) + '</b> (' + r.comprimento_nominal_m + 'm): ';
      h += (r.sub_enfestos||[]).map(function(s){
        return s.n_camadas + ' folha(s) do mapa ' + s.mapa_id;
      }).join('; ') || 'sem uso';
      h += ' | ponta ' + r.ponta_m + 'm (' + r.ponta_classe + ')</div>';
    });
    // corte separado
    (cr.sugestoes_corte_separado||[]).forEach(function(s){
      var compos = Object.keys(s.composicao||{}).map(function(t){return s.composicao[t]+t;}).join('+');
      h += '<div class="ok">&#8635; Corte separado: mapa ' + s.mapa_id + ' (' + s.rotulo + ': ' + compos + ') &mdash; '
         + (s.cortes||[]).map(function(c){return c.n_camadas+' na ponta do rolo '+(c.rolo_origem_indice+1);}).join('; ');
      if (s.deficit_residual_camadas>0) h += ' (faltam ' + s.deficit_residual_camadas + ')';
      h += '</div>';
    });
    var comprar = parseFloat(cr.tecido_a_comprar_m)||0;
    if (comprar>0) h += '<div class="def">Comprar aprox. ' + comprar.toFixed(1) + 'm para fechar.</div>';
    h += '</div>';
  });

  h += '<h2>Sobras totais por rolo</h2><table><tr><th>Cor</th><th>Rolo</th><th>Ponta (m)</th><th>Classe</th></tr>';
  cores.forEach(function(cor) {
    (d.por_cor[cor].sobras_por_rolo||[]).forEach(function(s){
      h += '<tr><td>' + cor + '</td><td>' + s.rolo_indice + '</td><td>' + s.ponta_m + '</td><td>' + s.ponta_classe + '</td></tr>';
    });
  });
  h += '</table></body></html>';
  return h;
}

function abrirRelatorioAlocacao() {
  if (!window._ultimaAlocacao) return;
  var w = window.open('', '_blank');
  if (!w) { alert('Permita pop-ups para gerar o relatorio.'); return; }
  w.document.write(_htmlImpressaoAlocacao(window._ultimaAlocacao.data, window._ultimaAlocacao.referencia));
  w.document.close();
  w.onload = function() { w.focus(); w.print(); };
}
```

- [ ] **Step 2: Add the print button**

In `_renderResultadoAlocacao`, change the button row (the `html += '<div class="btn-row"...exportarAlocacao()...'` near line 2260) to include the print button:

```javascript
  html += '<div class="btn-row" style="margin-top:8px">'
    +'<button class="btn btn-ok" onclick="exportarAlocacao()">&#128190; Exportar Alocacao (.xlsx)</button>'
    +'<button class="btn btn-s" onclick="abrirRelatorioAlocacao()">&#128424; Imprimir relatorio</button></div>';
```

- [ ] **Step 3: Verify**

- ASCII; braces balanced; `python -m pytest tests/ -q` → 96.
- Manual: após alocar, clicar "Imprimir relatorio" abre uma aba com o relatório (folhas por cor/rolo, corte separado, sobras totais) e o diálogo de impressão (Salvar como PDF).

- [ ] **Step 4: Commit**

```bash
git add interface.html
git commit -m "feat(ui): relatorio de alocacao para impressao (print-view / PDF)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task C-T6: Sobras + corte separado na planilha de alocação (opcional)

**Files:**
- Modify: `exportar/export_xlsx.py` (`_aba_cor_alocacao` ~1139-1203)

- [ ] **Step 1: Append sections after the rolls table**

In `_aba_cor_alocacao`, after the rolls loop (after line ~1203, before the function ends), append (use the existing `_cel`, `r` counter, color constants):

```python
    sobras = cor_res.get("sobras_por_rolo", [])
    if sobras:
        r += 1
        _cel(ws, r, 1, "Sobras por rolo", negrito=True, fundo=C_AZUL_MED, cor_txt=C_BRANCO)
        r += 1
        for s in sobras:
            _cel(ws, r, 1, f"Rolo {s['rolo_indice']}")
            _cel(ws, r, 2, s["ponta_m"], alinha="right")
            _cel(ws, r, 3, s["ponta_classe"])
            r += 1

    sugs = cor_res.get("sugestoes_corte_separado", [])
    if sugs:
        r += 1
        _cel(ws, r, 1, "Corte separado sugerido", negrito=True, fundo=C_VERDE, cor_txt=C_VERDE_TX)
        r += 1
        for s in sugs:
            compos = "+".join(f"{q}{t}" for t, q in (s.get("composicao") or {}).items())
            cortes = "; ".join(f"{c['n_camadas']}x rolo {c['rolo_origem_indice']+1}" for c in s.get("cortes", []))
            _cel(ws, r, 1, f"Mapa {s['mapa_id']} ({s['rotulo']}: {compos})")
            _cel(ws, r, 2, cortes)
            r += 1
```


- [ ] **Step 2: Verify**

`python -m pytest tests/ -q` → 96 (export not unit-tested for this; manual: export an allocation with a suggestion and confirm the sheet shows the two sections).

- [ ] **Step 3: Commit**

```bash
git add exportar/export_xlsx.py
git commit -m "feat(export): sobras e corte separado na aba da cor da alocacao

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente C
- [ ] `python -m pytest tests/ -q` → 96 passed (88 + 5 reaproveitamento + 3 alocador).
- [ ] Manual: déficit cobrível por pontas → sugere corte separado (não manda comprar tudo); Audaces real recalcula; relatório imprime; xlsx mostra sobras/corte.
- [ ] Merge `frente-c-alocacao` → `main` (fast-forward) + remover branch.

## Self-Review (autor do plano)
- **Cobertura do spec (Frente C):** C1 corte separado (C-T1) ✓; C3 sobras (C-T2) ✓; render (C-T3) ✓; C2 Audaces (C-T4) ✓; C5 PDF print-view (C-T5) ✓; xlsx (C-T6, opcional) ✓.
- **Sem placeholders:** todo step com código completo.
- **Consistência:** `sugerir_corte_separado` (C-T1) produz a estrutura que C-T3/C-T5/C-T6 leem (`sugestoes_corte_separado` com `cortes[].rolo_origem_indice/n_camadas/comp_total`); `sobras_por_rolo` (C-T2) lido por C-T3/C-T5/C-T6; `window._compRealAudaces` (C-T4) consumido em `_montarPlanoParaAlocacao`; backend já honra `comp_camada_m`. Não altera plano nem alocação principal.
- **Risco:** o algoritmo do corte separado é o ponto sensível — coberto por 5 testes unitários (cabe/não-cabe com margem, submapa reduzido, várias pontas) + 2 de integração. Validar contra o caso real (VESTIDO CORINA) na verificação manual.
