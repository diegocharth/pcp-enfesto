# Alocador "enfesto por enfesto" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescrever o núcleo por-cor do alocador de tecido para o modelo "enfesto por enfesto" com reaproveitamento de ponta (só camada inteira, várias pontas OK, sem emenda, margem 1×/enfesto, greedy mapa-longo-primeiro), removendo o "corte separado" antigo.

**Architecture:** Função pura `_alocar_cor(...)` em `engine/alocador_rolos.py` aloca uma cor processando os enfestos do mapa mais longo pro mais curto, mantendo um pool de pedaços (rolos + pontas carregadas), cada peça pertencendo a um rolo-raiz. `alocar_rolos(plano, rolos, config)` mantém a assinatura e o contrato de entrada; muda o conteúdo de `por_cor[cor]` (ganha `enfestos[]` e `reaproveitamento`, `rolos[]` vira resumo). Consumidores (Excel, UI, multi-ref) leem o novo formato. Solver/plano são intocados.

**Tech Stack:** Python 3.10+ stdlib, pytest, openpyxl, HTML/JS vanilla (ASCII). Repo: `C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos`. Base: `main` em `ca5bdb2`. Spec: `docs/superpowers/specs/2026-06-25-alocador-enfesto-por-enfesto-design.md`.

**Encoding:** `interface.html` é UTF-8 válido; as funções de alocação alvo (2147-2367) são 100% ASCII. Editar só com ASCII; usar a entidade `&#8635;` (↻) para "reaproveitada". NÃO tocar em `_sugestoesAlocacao` (2154-2195, tem emojis literais).

**Branch:** trabalhar em `main` (commits frequentes). Ao final, re-sincronizar `release-2.11.0` a partir de `main`.

---

## Formato de saída alvo (contrato)

`por_cor[cor]`:
```python
{
  "enfestos": [   # ordem de corte: mapa mais longo -> mais curto
    {
      "mapa_id": int, "comp_camada_m": float,
      "camadas_necessarias": int, "camadas_cobertas": int, "camadas_em_deficit": int,
      "margem_m": float, "tecido_usado_m": float, "tecido_a_comprar_m": float,
      "fontes": [
        {"tipo": "rolo"|"ponta", "rolo_indice": int,   # 1-based, rolo-raiz
         "enfesto_origem": int|None,                    # mapa_id do enfesto que gerou a ponta (None p/ rolo)
         "n_camadas": int, "comp_camada_m": float, "comp_usado_m": float,
         "primaria": bool, "reaproveitada": bool}
      ]
    }
  ],
  "rolos": [   # resumo final por rolo
    {"rolo_indice": int, "nominal_m": float, "seguro_m": float,
     "usado_m": float, "ponta_m": float, "ponta_classe": "estoque"|"refugo"}
  ],
  "camadas_alocadas": {mid: int}, "camadas_em_deficit": {mid: int},
  "tecido_usado_m": float, "tecido_a_comprar_m": float,
  "ponta_estoque_total_m": float, "refugo_real_m": float, "refugo_percentual": float,
  "n_sub_enfestos": int,   # nº de enfestos efetivamente cortados (camadas_cobertas>0)
  "reaproveitamento": {"camadas_reaproveitadas": int, "tecido_economizado_m": float}
}
```
`resumo_geral`: mantém `tecido_usado_total_m`, `ponta_estoque_total_m`, `refugo_real_total_m`, `refugo_percentual_medio`, `n_sub_enfestos_total`, `cores_com_deficit`, `sobras_consolidado`, `alertas`; **adiciona** `camadas_reaproveitadas_total`, `tecido_economizado_total_m`; **remove** `sugestoes_corte_total`. `params` inalterado.

**Removidos do JSON:** `sugestoes_corte_separado`, `sugestoes_corte_total`, `sobras_por_rolo` (vira `rolos[]`), `rolos[].sub_enfestos`.

---

## File Structure

- `engine/alocador_rolos.py` — MODIFICAR: nova função `_alocar_cor` + reescrever o corpo do loop por-cor em `alocar_rolos`; remover tudo do corte separado; novo `resumo_geral`. Preservar `_comp_seguro`, `_validar_entradas`, parse de `comp_camada_por_id`.
- `engine/reaproveitamento.py` — DELETAR.
- `tests/test_reaproveitamento.py` — DELETAR.
- `tests/test_alocador_rolos.py` — MODIFICAR: adaptar 8, remover 2, adicionar ~6 novos.
- `tests/test_alocador_enfestos.py` — CRIAR: testes focados do novo `_alocar_cor`.
- `exportar/export_xlsx.py` — MODIFICAR: `_aba_cor_alocacao` (remover corte separado; trocar tabela de rolos por seção por-enfesto+fontes; "Sobras por rolo" lê `rolos[]`); `_aba_resumo_alocacao` (KPI de reaproveitamento). `sobras_consolidado` no engine lê `rolos[]`.
- `interface.html` — MODIFICAR: `_renderResultadoAlocacao` (rolos→enfestos+fontes), remover `_htmlCorteSeparado` + chamada, `_htmlSobrasPorRolo` lê `rolos[]`, `_htmlImpressaoAlocacao` (enfestos+fontes; remover corte separado).
- `main.py` — SEM mudança de código (handler `/alocar_rolos` já é posicional e serializa as-is). Apenas verificação.

---

## Task 1: Núcleo `_alocar_cor` — esqueleto e pool

**Files:**
- Modify: `engine/alocador_rolos.py` (adicionar função nova, perto de `_comp_seguro`)
- Test: `tests/test_alocador_enfestos.py` (criar)

- [ ] **Step 1: Escrever o teste do caso trivial (1 mapa cabe tudo, sem reaproveitamento)**

Criar `tests/test_alocador_enfestos.py`:
```python
"""Novo alocador enfesto-por-enfesto: _alocar_cor (por cor)."""
from engine.alocador_rolos import _alocar_cor

CFG = {"margem_seguranca_enfesto_m": 0.10, "folga_incerteza_pct": 0.0,
       "folga_incerteza_m": 0.0, "ponta_minima_util_m": 0.5}


def test_um_mapa_cabe_tudo():
    # mapa 0 cc=4.0, precisa 3; rolo de 20m (seguro=20, folga 0) cabe 4 camadas.
    r = _alocar_cor({0: 3}, {0: 4.0}, [20.0], CFG)
    assert r["camadas_alocadas"] == {0: 3}
    assert r["camadas_em_deficit"] == {}
    e = r["enfestos"][0]
    assert e["mapa_id"] == 0 and e["camadas_cobertas"] == 3
    assert e["camadas_em_deficit"] == 0
    # margem 1x: 3*4.0 + 0.10
    assert abs(e["tecido_usado_m"] - 12.10) < 1e-6
    assert len(e["fontes"]) == 1
    f = e["fontes"][0]
    assert f["tipo"] == "rolo" and f["rolo_indice"] == 1
    assert f["n_camadas"] == 3 and f["reaproveitada"] is False and f["primaria"] is True
    # ponta final do rolo = 20 - (12.10) = 7.90 -> estoque
    assert len(r["rolos"]) == 1
    assert abs(r["rolos"][0]["ponta_m"] - 7.90) < 1e-6
    assert r["rolos"][0]["ponta_classe"] == "estoque"
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 0
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `python -m pytest tests/test_alocador_enfestos.py::test_um_mapa_cabe_tudo -v`
Expected: FAIL (`ImportError: cannot import name '_alocar_cor'`).

- [ ] **Step 3: Implementar `_alocar_cor`**

Adicionar em `engine/alocador_rolos.py` (após `_comp_seguro`, antes de `alocar_rolos`):
```python
def _alocar_cor(demanda, comp_camada_por_id, rolos_cor, config):
    """Aloca o tecido de UMA cor pelo modelo enfesto-por-enfesto com
    reaproveitamento de ponta (so camada inteira, sem emenda, margem 1x/enfesto,
    greedy mapa-longo-primeiro). Funcao pura."""
    margem    = float(config.get("margem_seguranca_enfesto_m", 0.10))
    ponta_min = float(config.get("ponta_minima_util_m", 0.5))
    _EPS = 1e-4

    # Estado por rolo-raiz: peca atual no pool (comprimento), usado acumulado.
    rolos = []   # [{rolo_indice, nominal_m, seguro_m, restante_m, usado_m, origem, enfesto_origem}]
    for i, nom in enumerate(rolos_cor):
        seguro = round(_comp_seguro(nom, config), 6)
        rolos.append({
            "rolo_indice": i + 1, "nominal_m": float(nom), "seguro_m": seguro,
            "restante_m": seguro, "usado_m": 0.0,
            "origem": "rolo", "enfesto_origem": None,
        })

    camadas_alocadas = {mid: 0 for mid in demanda}
    enfestos = []

    # Ordem de corte: mapa mais longo primeiro; empate -> maior demanda.
    ordem = sorted(demanda.keys(),
                   key=lambda m: (-comp_camada_por_id.get(m, 0.0), -demanda[m]))

    for mid in ordem:
        cc = float(comp_camada_por_id.get(mid, 0.0))
        K  = int(demanda[mid])
        cobertas = 0
        fontes = []
        if cc > 0 and K > 0:
            # Pool ordenado: pontas antes de rolos novos; depois maior restante.
            disponiveis = [r for r in rolos if r["restante_m"] > 0]
            disponiveis.sort(key=lambda r: (r["origem"] == "rolo", -r["restante_m"]))
            # Fonte primaria = primeiro pedaco com restante >= cc + margem.
            primaria = next((r for r in disponiveis
                             if r["restante_m"] + _EPS >= cc + margem), None)
            if primaria is not None:
                for r in disponiveis:
                    if cobertas >= K:
                        break
                    eh_primaria = (r is primaria)
                    overhead = margem if eh_primaria else 0.0
                    cap = int(math.floor((r["restante_m"] - overhead + _EPS) / cc))
                    if cap <= 0:
                        continue
                    k = min(cap, K - cobertas)
                    consumo = k * cc + overhead
                    fontes.append({
                        "tipo": r["origem"], "rolo_indice": r["rolo_indice"],
                        "enfesto_origem": r["enfesto_origem"],
                        "n_camadas": k, "comp_camada_m": round(cc, 4),
                        "comp_usado_m": round(consumo, 4),
                        "primaria": eh_primaria, "reaproveitada": r["origem"] == "ponta",
                    })
                    r["restante_m"] = round(r["restante_m"] - consumo, 6)
                    r["usado_m"]    = round(r["usado_m"] + consumo, 6)
                    r["origem"] = "ponta"          # apos uso, vira ponta reaproveitavel
                    r["enfesto_origem"] = mid
                    cobertas += k
        camadas_alocadas[mid] = cobertas
        deficit_e = K - cobertas
        enfestos.append({
            "mapa_id": mid, "comp_camada_m": round(cc, 4),
            "camadas_necessarias": K, "camadas_cobertas": cobertas,
            "camadas_em_deficit": deficit_e, "margem_m": round(margem, 4),
            "tecido_usado_m": round(cobertas * cc + (margem if cobertas > 0 else 0.0), 4),
            "tecido_a_comprar_m": round(deficit_e * cc, 4),
            "fontes": fontes,
        })

    # Resumo por rolo (estado final).
    rolos_out, ponta_est, refugo_real, nom_total = [], 0.0, 0.0, 0.0
    for r in rolos:
        ponta = round(max(0.0, r["restante_m"]), 4)
        classe = "estoque" if ponta >= ponta_min else "refugo"
        rolos_out.append({
            "rolo_indice": r["rolo_indice"], "nominal_m": round(r["nominal_m"], 4),
            "seguro_m": round(r["seguro_m"], 4),
            "usado_m": round(r["seguro_m"] - ponta, 4),
            "ponta_m": ponta, "ponta_classe": classe,
        })
        nom_total += r["nominal_m"]
        if classe == "estoque":
            ponta_est += ponta
        else:
            refugo_real += ponta

    camadas_def = {mid: (int(demanda[mid]) - camadas_alocadas[mid])
                   for mid in demanda if int(demanda[mid]) - camadas_alocadas[mid] > 0}
    reap_camadas = sum(f["n_camadas"] for e in enfestos for f in e["fontes"]
                       if f["reaproveitada"])
    reap_tecido  = sum(f["n_camadas"] * f["comp_camada_m"] for e in enfestos
                       for f in e["fontes"] if f["reaproveitada"])
    return {
        "enfestos": enfestos, "rolos": rolos_out,
        "camadas_alocadas": camadas_alocadas, "camadas_em_deficit": camadas_def,
        "tecido_usado_m": round(sum(e["tecido_usado_m"] for e in enfestos), 3),
        "tecido_a_comprar_m": round(sum(e["tecido_a_comprar_m"] for e in enfestos), 3),
        "ponta_estoque_total_m": round(ponta_est, 3),
        "refugo_real_m": round(refugo_real, 3),
        "refugo_percentual": round(100 * refugo_real / nom_total, 2) if nom_total > 0 else 0.0,
        "n_sub_enfestos": sum(1 for e in enfestos if e["camadas_cobertas"] > 0),
        "reaproveitamento": {"camadas_reaproveitadas": reap_camadas,
                             "tecido_economizado_m": round(reap_tecido, 3)},
    }
```
(Confirmar que `import math` já existe no topo — está.)

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `python -m pytest tests/test_alocador_enfestos.py::test_um_mapa_cabe_tudo -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/alocador_rolos.py tests/test_alocador_enfestos.py
git commit -m "feat(alocador): nucleo _alocar_cor enfesto-por-enfesto (caso trivial)"
```

---

## Task 2: `_alocar_cor` — reaproveitamento, só-camada-inteira, déficit, multi-cor

**Files:**
- Test: `tests/test_alocador_enfestos.py`

- [ ] **Step 1: Escrever os testes das regras**

Acrescentar em `tests/test_alocador_enfestos.py`:
```python
def test_reaproveita_ponta_de_mapa_longo_em_mapa_curto():
    # E1 cc=7.8 (4 camadas), E2 cc=4.0 (3). Rolos 20 e 12 (folga 0).
    r = _alocar_cor({0: 4, 1: 3}, {0: 7.8, 1: 4.0}, [20.0, 12.0], CFG)
    # Ordem: mapa 0 (longo) primeiro.
    assert [e["mapa_id"] for e in r["enfestos"]] == [0, 1]
    e0, e1 = r["enfestos"]
    # E1: rolo 20 -> 2 camadas (primaria, 2*7.8+0.10=15.7); rolo 12 -> 1 (7.8). Cobertas 3, deficit 1.
    assert e0["camadas_cobertas"] == 3 and e0["camadas_em_deficit"] == 1
    # E2: pontas 4.3 (do rolo 20) e 4.2 (do rolo 12) -> 1 camada cada. Cobertas 2, deficit 1.
    assert e1["camadas_cobertas"] == 2 and e1["camadas_em_deficit"] == 1
    assert all(f["reaproveitada"] for f in e1["fontes"])
    assert all(f["tipo"] == "ponta" for f in e1["fontes"])
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 2
    assert abs(r["reaproveitamento"]["tecido_economizado_m"] - 8.0) < 1e-6


def test_ponta_menor_que_camada_nao_e_usada():
    # E1 cc=7.8 (precisa 2). Rolo 8.0 -> 1 camada, ponta 0.10. E2 cc=4.0 (precisa 1).
    # A ponta 0.10 < 4.0 nao serve ao E2 (nada de submapa parcial).
    r = _alocar_cor({0: 2, 1: 1}, {0: 7.8, 1: 4.0}, [8.0], CFG)
    e1 = [e for e in r["enfestos"] if e["mapa_id"] == 1][0]
    assert e1["camadas_cobertas"] == 0
    assert e1["fontes"] == []
    assert r["reaproveitamento"]["camadas_reaproveitadas"] == 0


def test_sem_emenda_cada_fonte_um_pedaco():
    r = _alocar_cor({0: 4}, {0: 7.8}, [20.0, 12.0], CFG)
    e0 = r["enfestos"][0]
    # rolo 20 -> 2 camadas; rolo 12 -> 1 camada; cada fonte sai de um unico rolo.
    assert sorted(f["n_camadas"] for f in e0["fontes"]) == [1, 2]
    assert e0["camadas_cobertas"] == 3


def test_deficit_sem_pedaco_para_primaria():
    # cc=7.8 + margem 0.10 = 7.90; rolo 7.0 (<7.90) nao hospeda a pilha -> deficit total.
    r = _alocar_cor({0: 1}, {0: 7.8}, [7.0], CFG)
    assert r["enfestos"][0]["camadas_cobertas"] == 0
    assert r["camadas_em_deficit"] == {0: 1}
    assert abs(r["tecido_a_comprar_m"] - 7.8) < 1e-6


def test_ordem_empate_maior_demanda_primeiro():
    # dois mapas com mesma cc; o de maior demanda vem primeiro.
    r = _alocar_cor({0: 2, 1: 5}, {0: 4.0, 1: 4.0}, [50.0], CFG)
    assert [e["mapa_id"] for e in r["enfestos"]] == [1, 0]
```

- [ ] **Step 2: Rodar e ver passar (a implementação da Task 1 já cobre)**

Run: `python -m pytest tests/test_alocador_enfestos.py -v`
Expected: PASS em todos. Se algum falhar, ajustar `_alocar_cor` (não os testes) até passar.

- [ ] **Step 3: Commit**

```bash
git add tests/test_alocador_enfestos.py
git commit -m "test(alocador): regras do _alocar_cor (reaproveitamento, camada inteira, deficit, ordem)"
```

---

## Task 3: Integrar `_alocar_cor` em `alocar_rolos` e remover o corte separado

**Files:**
- Modify: `engine/alocador_rolos.py` (loop por-cor, resumo_geral, imports, docstring)

- [ ] **Step 1: Remover o import do corte separado**

Apagar a linha (topo do arquivo):
```python
from engine.reaproveitamento import sugerir_corte_separado
```

- [ ] **Step 2: Remover o 2º loop de mapas (composicao_por_id / cpp_por_id)**

Apagar o bloco (linhas ~165-171):
```python
    composicao_por_id = {}
    cpp_por_id = {}
    for m in mapas_plano:
        mid_ = int(m["id"])
        composicao_por_id[mid_] = dict(m.get("composicao", {}))
        n_pecs = int(m.get("n_pecas", sum(m.get("composicao", {}).values()))) or 1
        cpp_por_id[mid_] = round(comp_camada_por_id.get(mid_, 0.0) / n_pecs, 6)
```

- [ ] **Step 3: Substituir o corpo do loop por-cor**

No loop `for cor in todas_cores:`, manter o parse (`demanda`, `rolos_cor`), o `continue` de demanda vazia, a verificação crítica de camada-maior-que-rolo (alertas), e SUBSTITUIR todo o miolo (empacotamento 228-321 + déficit-agregados 323-347 + pontas/sobras 349-368 + `resultado_por_cor[cor]` 370-382) por:

```python
        # Ramo: cor sem rolos -> deficit total (mantem alertas existentes).
        if not rolos_cor:
            alertas.append(f"{cor}: nenhum rolo disponivel; toda a demanda vira compra.")
            cr = _alocar_cor(demanda, comp_camada_por_id, [], config)
        else:
            # Verificacao critica: camada que nao cabe em nenhum rolo.
            maior_seguro = max(_comp_seguro(r, config) for r in rolos_cor)
            for mid, cc in comp_camada_por_id.items():
                if mid in demanda and cc > maior_seguro + 0.001:
                    alertas.append(
                        f"{cor}: CRITICO -- camada do mapa {mid} ({cc:.2f}m) nao cabe "
                        f"em nenhum rolo (maior seguro {maior_seguro:.2f}m)."
                    )
            cr = _alocar_cor(demanda, comp_camada_por_id, rolos_cor, config)

        for mid, n in cr["camadas_em_deficit"].items():
            cc = comp_camada_por_id.get(mid, 0.0)
            alertas.append(f"{cor}: deficit de {n} camada(s) do mapa {mid} -- "
                           f"comprar aprox. {round(n * cc, 2)}m.")
        if cr["camadas_em_deficit"]:
            acc["cores_com_deficit"].append(cor)

        resultado_por_cor[cor] = cr
        acc["tecido_usado_total_m"]   += cr["tecido_usado_m"]
        acc["ponta_estoque_total_m"]  += cr["ponta_estoque_total_m"]
        acc["refugo_real_total_m"]    += cr["refugo_real_m"]
        acc["n_sub_enfestos_total"]   += cr["n_sub_enfestos"]
```
(Garantir que `acc` é inicializado antes do loop com as chaves usadas — já existe; manter `cores_com_deficit` como lista.)

- [ ] **Step 4: Reescrever `resumo_geral` (remover sugestoes_corte_total; ler `rolos[]`; somar reaproveitamento)**

Substituir o bloco do `resumo_geral` (399-422) por:
```python
    nom_total_geral = sum(r["nominal_m"]
                          for res in resultado_por_cor.values() for r in res["rolos"])
    refugo_medio = (round(100 * acc["refugo_real_total_m"] / nom_total_geral, 2)
                    if nom_total_geral > 0 else 0.0)
    resumo_geral = {
        "tecido_usado_total_m"     : round(acc["tecido_usado_total_m"], 3),
        "ponta_estoque_total_m"    : round(acc["ponta_estoque_total_m"], 3),
        "refugo_real_total_m"      : round(acc["refugo_real_total_m"], 3),
        "refugo_percentual_medio"  : refugo_medio,
        "n_sub_enfestos_total"     : acc["n_sub_enfestos_total"],
        "cores_com_deficit"        : sorted(set(acc["cores_com_deficit"])),
        "camadas_reaproveitadas_total": sum(
            res["reaproveitamento"]["camadas_reaproveitadas"]
            for res in resultado_por_cor.values()),
        "tecido_economizado_total_m": round(sum(
            res["reaproveitamento"]["tecido_economizado_m"]
            for res in resultado_por_cor.values()), 3),
        "sobras_consolidado": {
            c: {
                "ponta_estoque_m": res["ponta_estoque_total_m"],
                "refugo_m": res["refugo_real_m"],
                "n_pontas_estoque": sum(1 for r in res["rolos"]
                                        if r["ponta_classe"] == "estoque" and r["ponta_m"] > 0),
            } for c, res in resultado_por_cor.items()
        },
        "alertas": alertas,
    }
```

- [ ] **Step 5: Atualizar a docstring de `alocar_rolos`**

Trocar qualquer menção a `sugestoes_corte_separado`/`corte separado` na docstring de retorno pelo novo formato (`enfestos[]` com `fontes[]`, `rolos[]` resumo, `reaproveitamento`). Texto curto, sem placeholder.

- [ ] **Step 6: Rodar parse + os testes do novo núcleo**

Run: `python -c "import ast; ast.parse(open('engine/alocador_rolos.py',encoding='utf-8').read()); print('OK')"`
Run: `python -m pytest tests/test_alocador_enfestos.py -v`
Expected: PASS. (test_alocador_rolos.py ainda vai falhar — adaptado na Task 5.)

- [ ] **Step 7: Commit**

```bash
git add engine/alocador_rolos.py
git commit -m "feat(alocador): alocar_rolos usa _alocar_cor; remove corte separado e sugestoes_corte_*"
```

---

## Task 4: Deletar `reaproveitamento.py` e seu teste

**Files:**
- Delete: `engine/reaproveitamento.py`, `tests/test_reaproveitamento.py`

- [ ] **Step 1: Confirmar que nada mais importa o módulo**

Run: `grep -rn "reaproveitamento import\|sugerir_corte_separado" --include=*.py .`
Expected: nenhuma ocorrência fora dos 2 arquivos a deletar (o import do engine já saiu na Task 3).

- [ ] **Step 2: Deletar os arquivos**

```bash
git rm engine/reaproveitamento.py tests/test_reaproveitamento.py
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(alocador): remove engine/reaproveitamento.py (corte separado obsoleto)"
```

---

## Task 5: Adaptar `tests/test_alocador_rolos.py` ao novo formato

**Files:**
- Modify: `tests/test_alocador_rolos.py`

Os testes que navegam `rolos[].sub_enfestos[]` ou checam chaves removidas precisam ser reescritos. Os fixtures (`MAPAS_BASE`, `CONFIG_BASE`, `CONSUMO`) e o import `from engine.alocador_rolos import alocar_rolos, _comp_seguro` permanecem.

- [ ] **Step 1: Remover os 2 testes de corte separado**

Apagar `test_alocacao_anexa_sugestoes_corte_separado` e `test_sem_rolos_tem_chaves_vazias`.

- [ ] **Step 2: Adaptar `test_comp_camada_m_explicito_tem_prioridade`**

Substituir a navegação `rolos[0].sub_enfestos[0]` por `enfestos`:
```python
def test_comp_camada_m_explicito_tem_prioridade():
    plano = {
        "mapas": [{"id": 0, "composicao": {"PP": 2, "P": 1, "M": 1}, "n_pecas": 4,
                   "comp_camada_m": 8.0}],
        "camadas": {"PRETO": {0: 5}},
        "consumo_peca": 1.0,
    }
    res = alocar_rolos(plano, {"PRETO": [60.0]}, dict(CONFIG_BASE))
    e = res["por_cor"]["PRETO"]["enfestos"][0]
    assert e["comp_camada_m"] == 8.0
    # 5 camadas * 8.0 + 0.10 margem
    assert abs(e["tecido_usado_m"] - 40.10) < 1e-3
```

- [ ] **Step 3: Adaptar `test_margem_por_sub_enfesto` (renomear)**

```python
def test_margem_uma_vez_por_enfesto():
    plano = {"mapas": [{"id": 0, "composicao": {"PP": 2, "P": 1, "M": 1}, "n_pecas": 4}],
             "camadas": {"PRETO": {0: 10}}, "consumo_peca": CONSUMO}
    res = alocar_rolos(plano, {"PRETO": [100.0]}, dict(CONFIG_BASE))
    e = res["por_cor"]["PRETO"]["enfestos"][0]
    assert e["camadas_cobertas"] == 10
    # margem cobrada 1x: 10*4*CONSUMO + 0.10
    assert abs(e["tecido_usado_m"] - (10 * 4 * CONSUMO + 0.10)) < 1e-3
```

- [ ] **Step 4: Adaptar `test_fechamento_de_ponta` -> reaproveitamento real**

```python
def test_reaproveitamento_real_mapa_longo_para_curto():
    plano = {
        "mapas": [{"id": 0, "composicao": {"M": 6}, "n_pecas": 6},
                  {"id": 1, "composicao": {"P": 3}, "n_pecas": 3}],
        "camadas": {"PRETO": {0: 4, 1: 3}}, "consumo_peca": 1.3,
    }  # cc0 = 7.8, cc1 = 3.9
    res = alocar_rolos(plano, {"PRETO": [20.0, 12.0]}, dict(CONFIG_BASE))
    cr = res["por_cor"]["PRETO"]
    assert [e["mapa_id"] for e in cr["enfestos"]] == [0, 1]
    assert cr["reaproveitamento"]["camadas_reaproveitadas"] >= 1
    e1 = [e for e in cr["enfestos"] if e["mapa_id"] == 1][0]
    assert any(f["reaproveitada"] for f in e1["fontes"])
```
(Nota: `CONFIG_BASE` tem `folga_incerteza_pct=0.03`, então seguro=19.4/11.64; conferir que o reaproveitamento ainda ocorre — os números acima são tolerantes (`>=1`).)

- [ ] **Step 5: Adaptar `test_ponta_estoque` e `test_ponta_refugo`**

Trocar a navegação para o resumo `rolos[]` (chaves `nominal_m/seguro_m/usado_m/ponta_m/ponta_classe`). Manter os cenários; ex.:
```python
def test_ponta_estoque():
    plano = {"mapas": [{"id": 0, "composicao": {"P": 4}, "n_pecas": 4}],
             "camadas": {"PRETO": {0: 1}}, "consumo_peca": 1.0}  # cc=4.0
    res = alocar_rolos(plano, {"PRETO": [10.0]}, dict(CONFIG_BASE))
    rolo = res["por_cor"]["PRETO"]["rolos"][0]
    assert rolo["ponta_classe"] == "estoque"
    assert rolo["ponta_m"] >= CONFIG_BASE["ponta_minima_util_m"]


def test_ponta_refugo():
    plano = {"mapas": [{"id": 0, "composicao": {"P": 4}, "n_pecas": 4}],
             "camadas": {"PRETO": {0: 2}}, "consumo_peca": 1.0}  # cc=4.0
    # rolo 8.3 (seguro ~8.05): 2 camadas = 8.0 + 0.10 margem nao cabe -> 1 camada,
    # ajustar para sobrar ponta < 0.5. Use rolo cujo seguro deixe ponta pequena.
    res = alocar_rolos(plano, {"PRETO": [8.35]}, dict(CONFIG_BASE))
    rolo = res["por_cor"]["PRETO"]["rolos"][0]
    assert rolo["ponta_classe"] == "refugo"
```
(Ao implementar: rodar o cálculo e ajustar o comprimento do rolo para garantir a classe esperada; documentar o número no comentário.)

- [ ] **Step 6: Adaptar `test_regra_dura_nunca_violada`**

```python
def test_regra_dura_nunca_violada():
    plano = {"mapas": MAPAS_BASE, "camadas": {"PRETO": {0: 8, 1: 6}}, "consumo_peca": CONSUMO}
    res = alocar_rolos(plano, {"PRETO": [30.0, 25.0, 20.0]}, dict(CONFIG_BASE))
    for rolo in res["por_cor"]["PRETO"]["rolos"]:
        assert rolo["usado_m"] <= rolo["seguro_m"] + 1e-3
        assert rolo["ponta_m"] >= -1e-9
```

- [ ] **Step 7: Adaptar `test_sobras_por_rolo_e_consolidado`**

```python
def test_rolos_resumo_e_consolidado():
    plano = {"mapas": [{"id": 0, "composicao": {"P": 4}, "n_pecas": 4}],
             "camadas": {"AZUL": {0: 2}}, "consumo_peca": 1.0}
    res = alocar_rolos(plano, {"AZUL": [20.0]}, dict(CONFIG_BASE))
    cr = res["por_cor"]["AZUL"]
    assert len(cr["rolos"]) == 1
    r0 = cr["rolos"][0]
    for k in ("rolo_indice", "nominal_m", "seguro_m", "usado_m", "ponta_m", "ponta_classe"):
        assert k in r0
    assert "sobras_consolidado" in res["resumo_geral"]
    assert "AZUL" in res["resumo_geral"]["sobras_consolidado"]
```

- [ ] **Step 8: Adicionar teste do bloco reaproveitamento no resumo_geral**

```python
def test_resumo_geral_tem_reaproveitamento():
    plano = {"mapas": [{"id": 0, "composicao": {"M": 6}, "n_pecas": 6},
                       {"id": 1, "composicao": {"P": 3}, "n_pecas": 3}],
             "camadas": {"PRETO": {0: 4, 1: 3}}, "consumo_peca": 1.3}
    res = alocar_rolos(plano, {"PRETO": [20.0, 12.0]}, dict(CONFIG_BASE))
    rg = res["resumo_geral"]
    assert "camadas_reaproveitadas_total" in rg
    assert "tecido_economizado_total_m" in rg
    assert "sugestoes_corte_total" not in rg
```

- [ ] **Step 9: Rodar a suíte do alocador inteira**

Run: `python -m pytest tests/test_alocador_rolos.py tests/test_alocador_enfestos.py -v`
Expected: PASS em todos. Ajustar números dos cenários (não a lógica) onde necessário, rodando o cálculo para conferir.

- [ ] **Step 10: Commit**

```bash
git add tests/test_alocador_rolos.py
git commit -m "test(alocador): adapta testes ao formato enfesto-por-enfesto"
```

---

## Task 6: Excel — `_aba_cor_alocacao` por enfesto + fontes

**Files:**
- Modify: `exportar/export_xlsx.py` (`_aba_cor_alocacao` ~1195-1285; `_aba_resumo_alocacao` ~1133-1192)

- [ ] **Step 1: Ler a função atual**

Run: ler `exportar/export_xlsx.py` linhas 1131-1320 para os helpers exatos (`_cel`, cores `C_VERDE`/`C_VERDE_TX`, padrões de cabeçalho).

- [ ] **Step 2: Reescrever `_aba_cor_alocacao`**

Substituir o miolo: manter os KPIs da cor (trocar `n_sub_enfestos` rótulo p/ "Enfestos cortados"; adicionar "Reaproveitado (camadas)" = `cor_res["reaproveitamento"]["camadas_reaproveitadas"]`). Trocar a tabela de rolos+sub_enfestos por:
- **Seção "Por enfesto"**: para cada `e` em `cor_res["enfestos"]`: linha-título `Mapa {e['mapa_id']} -- camada {e['comp_camada_m']}m -- {e['camadas_cobertas']}/{e['camadas_necessarias']} camadas` (fundo verde se reaproveitou); sub-linhas por fonte: `{f['n_camadas']}x ` + (`rolo {f['rolo_indice']}` se `tipo=='rolo'` senão `ponta do rolo {f['rolo_indice']} (do enfesto {f['enfesto_origem']})`) + marca `(reaproveitada)` quando `f['reaproveitada']`; se `e['camadas_em_deficit']>0`, linha vermelha `comprar {e['tecido_a_comprar_m']}m`.
- **Seção "Sobras por rolo"**: iterar `cor_res["rolos"]` com `rolo_indice`, `usado_m`, `ponta_m`, `ponta_classe` (fundo verde se estoque).
- **Remover** o bloco `sugs = cor_res.get("sugestoes_corte_separado", [])` (1272-1285) inteiro.

Escrever o código completo seguindo o padrão `_cel(ws, r, col, valor, ...)` existente. (O implementador escreve o corpo completo lendo os helpers da Step 1.)

- [ ] **Step 3: `_aba_resumo_alocacao` — KPI de reaproveitamento**

No bloco 2 (resumo_geral), adicionar duas linhas: "Camadas reaproveitadas" = `rg.get("camadas_reaproveitadas_total", 0)` e "Tecido economizado (m)" = `rg.get("tecido_economizado_total_m", 0)`.

- [ ] **Step 4: Teste de export (adaptar o existente em test_alocador_rolos.py)**

Reescrever `test_export_alocacao_tem_sobras_e_corte` -> `test_export_alocacao_tem_sobras_e_enfestos`:
```python
def test_export_alocacao_tem_sobras_e_enfestos():
    import tempfile, openpyxl
    from exportar.export_xlsx import exportar_alocacao
    plano = {"mapas": [{"id": 0, "composicao": {"M": 6}, "n_pecas": 6},
                       {"id": 1, "composicao": {"P": 3}, "n_pecas": 3}],
             "camadas": {"AZUL": {0: 4, 1: 3}}, "consumo_peca": 1.3}
    res = alocar_rolos(plano, {"AZUL": [20.0, 12.0]}, dict(CONFIG_BASE))
    with tempfile.TemporaryDirectory() as d:
        cam = exportar_alocacao(res, "TESTE", d, {**res.get("params", {}), "versao": "x"})
        wb = openpyxl.load_workbook(cam)
        ws = [s for s in wb.sheetnames if s.startswith("Rolos")][0]
        textos = " ".join(str(c.value) for row in wb[ws].iter_rows()
                           for c in row if c.value is not None)
    assert "Sobras por rolo" in textos
    assert "Mapa" in textos  # secao por enfesto
    assert "Corte separado" not in textos
```

- [ ] **Step 5: Rodar parse + teste de export**

Run: `python -c "import ast; ast.parse(open('exportar/export_xlsx.py',encoding='utf-8').read()); print('OK')"`
Run: `python -m pytest tests/test_alocador_rolos.py::test_export_alocacao_tem_sobras_e_enfestos -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add exportar/export_xlsx.py tests/test_alocador_rolos.py
git commit -m "feat(export): aba de alocacao por enfesto + fontes; remove corte separado do Excel"
```

---

## Task 7: UI — `interface.html` por enfesto + fontes (ASCII)

**Files:**
- Modify: `interface.html` (`_renderResultadoAlocacao` 2234-2299; `_htmlCorteSeparado` 2197-2217; `_htmlSobrasPorRolo` 2219-2232; `_htmlImpressaoAlocacao` 2301-2346)

**Encoding:** só ASCII; usar `&#8635;` para ↻. Ler as funções alvo antes de editar.

- [ ] **Step 1: Remover `_htmlCorteSeparado` e sua chamada**

Apagar a função `_htmlCorteSeparado(cr)` (2197-2217) inteira e a linha `html += _htmlCorteSeparado(cr);` em `_renderResultadoAlocacao` (manter `html += _htmlSobrasPorRolo(cr);`).

- [ ] **Step 2: Reescrever o loop por-cor de `_renderResultadoAlocacao`**

Trocar o loop que itera `cr.rolos[].sub_enfestos` por um loop que itera `cr.enfestos[]` e suas `fontes[]`:
```javascript
    (cr.enfestos || []).forEach(function(e){
      var reap = (e.fontes||[]).some(function(f){return f.reaproveitada;});
      html += '<div style="margin:4px 0;font-weight:600">'
            + (reap ? '&#8635; ' : '')
            + 'Mapa ' + e.mapa_id + ' &mdash; camada ' + e.comp_camada_m + 'm &mdash; '
            + e.camadas_cobertas + '/' + e.camadas_necessarias + ' camadas</div>';
      (e.fontes||[]).forEach(function(f){
        var de = f.tipo === 'ponta'
               ? 'ponta do rolo ' + f.rolo_indice + ' (do enfesto ' + f.enfesto_origem + ')'
               : 'rolo ' + f.rolo_indice;
        html += '<div style="margin-left:12px;font-size:12px">'
              + f.n_camadas + ' camada(s) de ' + de
              + (f.reaproveitada ? ' &#8635;' : '') + '</div>';
      });
      if (e.camadas_em_deficit > 0)
        html += '<div style="margin-left:12px;color:#b00;font-size:12px">comprar '
              + e.tecido_a_comprar_m + 'm (' + e.camadas_em_deficit + ' camada(s))</div>';
    });
```
(Adaptar nomes de variáveis/estilos ao padrão da função; manter o `<details>`/`<summary>` por cor.)

- [ ] **Step 3: Ajustar `_htmlSobrasPorRolo` para ler `cr.rolos`**

Trocar `cr.sobras_por_rolo` por `cr.rolos` (mesmas chaves `rolo_indice`, `usado_m`, `ponta_m`, `ponta_classe`):
```javascript
function _htmlSobrasPorRolo(cr) {
  var rolos = cr.rolos || [];
  if (!rolos.length) return '';
  var h = '<div style="margin-top:6px"><b>Sobras por rolo</b>'
        + '<table style="font-size:12px;width:100%"><tr><th>Rolo</th><th>Usado</th>'
        + '<th>Ponta</th><th>Classe</th></tr>';
  rolos.forEach(function(s){
    var cor = s.ponta_classe === 'estoque' ? 'green' : '#b00';
    h += '<tr><td>' + s.rolo_indice + '</td><td>' + s.usado_m + 'm</td>'
       + '<td style="color:' + cor + '">' + s.ponta_m + 'm</td>'
       + '<td>' + s.ponta_classe + '</td></tr>';
  });
  return h + '</table></div>';
}
```

- [ ] **Step 4: Reescrever o bloco de alocação de `_htmlImpressaoAlocacao`**

No loop por cor: trocar a leitura de `cr.rolos[].sub_enfestos` por `cr.enfestos[].fontes`; **remover** o bloco `(cr.sugestoes_corte_separado||[]).forEach(...)` (2326-2332). Manter o resumo, o `comprar Xm` quando `tecido_a_comprar_m>0`, e a seção "Sobras totais por rolo" (trocar `cr.sobras_por_rolo` por `cr.rolos`). Usar `&#8635;` para reaproveitada. Código completo análogo ao da Step 2, em string de impressão.

- [ ] **Step 5: Verificar ASCII e ausência de resquícios**

Run: `python -c "s=open('interface.html',encoding='utf-8').read(); import re; ok=all(ord(c)<128 for c in s[s.index('function _htmlSobrasPorRolo'):s.index('function abrirRelatorioAlocacao')]); print('ASCII regiao alvo:', ok)"`
Run: `grep -n "sugestoes_corte_separado\|_htmlCorteSeparado" interface.html`
Expected: ASCII True; grep sem ocorrências.

- [ ] **Step 6: Commit**

```bash
git add interface.html
git commit -m "feat(ui): alocacao por enfesto + fontes (reaproveitamento); remove corte separado da UI"
```

---

## Task 8: Verificação ponta-a-ponta e re-sincronizar release

**Files:** nenhum novo; verificação + git.

- [ ] **Step 1: Suíte completa verde**

Run: `python -m pytest tests/ -q`
Expected: tudo PASS (105 − 5 do reaproveitamento removido + ~6 novos do alocador ≈ 106). Anotar o número.

- [ ] **Step 2: Smoke-test ao vivo do `/alocar_rolos`**

Subir `python main.py` e fazer um POST de `/alocar_rolos` (via curl ou script) com um plano de 2 mapas de comprimentos diferentes + rolos que gerem reaproveitamento; conferir no JSON: `por_cor[cor].enfestos[].fontes` com `reaproveitada:true`, `reaproveitamento.camadas_reaproveitadas>0`, ausência de `sugestoes_corte_separado`. Encerrar o servidor.

- [ ] **Step 3: Verificar UI no servidor (manual, anotar para o Diego)**

Marcar como pendente o smoke-test no navegador (rodar uma alocação, conferir a seção por enfesto + ↻ + sobras + impressão). Isto fica para o Diego validar (UI não é testável daqui).

- [ ] **Step 4: Atualizar CLAUDE.md / RETOMAR.md / spec**

Atualizar a terminologia "Ponta de rolo" no CLAUDE.md se necessário e a nota de estado no RETOMAR.md (Frente C reformulada). Sem mudar `VERSION` em `main`.

- [ ] **Step 5: Commit + push main**

```bash
git add -A && git commit -m "docs: estado da Frente C reformulada (alocador enfesto-por-enfesto)"
git push
```

- [ ] **Step 6: Re-sincronizar `release-2.11.0`**

Recriar a release a partir da `main` nova + bump (como já feito antes): `git checkout main` → deletar `release-2.11.0` local+remoto → `git checkout -b release-2.11.0` → bump VERSION/main.py/CLAUDE.md p/ 2.11.0 (changelog cita o alocador enfesto-por-enfesto) → commit → `git push -u origin release-2.11.0`. Voltar para `main`. **Sem deploy** até o smoke-test no navegador do Diego.

---

## Self-Review (cobertura do spec)

- Spec §1 (fronteira, solver intocado): Tasks 1-3 só mexem no alocador; nada de solver. ✓
- Spec §2 (regras): só-camada-inteira (Task 2 `test_ponta_menor_que_camada_nao_e_usada`), sem emenda (`test_sem_emenda_cada_fonte_um_pedaco`), várias pontas (`test_reaproveita...`), margem 1×/enfesto (Task 5 `test_margem_uma_vez_por_enfesto`). ✓
- Spec §3 (algoritmo, primária, mapa-longo-primeiro): Task 1 código + Task 2 `test_ordem_empate...`. ✓
- Spec §4 (JSON): contrato no topo; Tasks 1/3. ✓
- Spec §5 (integração/remoções): Tasks 3,4,6,7; assinatura estável (Task 8 smoke). ✓
- Spec §6 (bordas: sem rolos, 1 mapa, primária impossível): Task 3 ramo sem-rolos, Task 2 `test_deficit_sem_pedaco_para_primaria`. ✓
- Spec §7 (testes): Tasks 2,5,6. ✓
- Spec §8 (não-objetivos): nada de estoque entre OPs / cross-cor / parcial. ✓
- Spec §9 (release): Task 8 step 6. ✓

**Consistência de nomes:** `_alocar_cor`, `enfestos[]`, `fontes[]`, `rolos[]`, `reaproveitamento`, `camadas_reaproveitadas`, `tecido_economizado_m` usados de forma idêntica em todas as tasks. ✓
