# Frente A — Correções Rápidas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar o download duplicado do plano de corte, fazer o resultado sumir quando um parâmetro muda, e gravar todos os parâmetros do cálculo nas planilhas Excel.

**Architecture:** Backend Python (`main.py` handlers + `exportar/export_xlsx.py`) e UI vanilla JS (`interface.html`). Os parâmetros passam a ser lidos de uma única fonte (`config`) no export; `main.py` monta o `config` (injeta versão/timeout/tempo/regras) antes de exportar. O alocador passa a devolver um bloco `params`. Na UI, um listener delegado esconde o resultado ao mudar qualquer parâmetro.

**Tech Stack:** Python 3.10+ stdlib, openpyxl, pytest; HTML/CSS/JS vanilla.

**Pré-requisitos / ordem:**
- Trabalhar no branch `melhorias-enfestos` (já criado).
- Rodar a suíte antes de começar: `python -m pytest tests/ -q` → 74 passam.
- Os números de linha foram verificados em 2026-06-24 mas **reconfira** antes de cada edição (o arquivo pode ter mudado).
- **Encoding:** todo novo bloco em `interface.html` deve ser **100% ASCII** (regra do projeto — usar entidades HTML `&#9888;` etc., nunca acento cru em código novo). Em arquivos `.py`, manter o padrão do arquivo (acentos OK, já usa UTF-8).
- A Task 2 (bloco `params` no `alocar_rolos`) também será reutilizada pela Frente C; é aditiva e não quebra testes.

---

## File Structure

| Arquivo | Responsabilidade nesta frente |
|---|---|
| `main.py` | A1: remover cópia ao Downloads. A3: injetar versão/timeout/tempo/regras no `config` antes de exportar; passar `params` ao export de alocação; adicionar `regras_especiais` à resposta de `/calcular`. |
| `engine/alocador_rolos.py` | A3 (Task 2): devolver bloco `params` no resultado. |
| `exportar/export_xlsx.py` | A3: helper `_resumo_parametros_txt(config)`; usá-lo no cabeçalho de `_aba_resumo` e `_aba_resumo_multiref` (mudar assinatura desta + call site); seção de params em `_aba_resumo_alocacao` (mudar assinatura desta e de `exportar_alocacao` + call site). |
| `interface.html` | A2: banners `#rb-stale`/`#aloc-stale` + listener delegado que esconde o resultado ao mudar parâmetro; esconder banner ao re-renderizar. A3: incluir `timeout` no payload de exportação. |
| `tests/test_export_params.py` (novo) | Testa o helper de params e os cabeçalhos. |
| `tests/test_export_downloads.py` (novo) | Guarda de regressão do A1. |
| `tests/test_alocador_rolos.py` (existente) | + teste do bloco `params`. |

---

## Task 1: A1 — Remover download duplicado

**Files:**
- Modify: `main.py` (remover helper `_copiar_para_downloads` ~213-220 e as 4 chamadas ~463, 629, 639, 650)
- Test: `tests/test_export_downloads.py` (criar)

- [ ] **Step 1: Write the failing test (guarda de regressão)**

Cria `tests/test_export_downloads.py`:

```python
"""Guarda de regressao do A1: o plano de corte NAO deve ser copiado para o
Downloads pelo servidor (so o navegador baixa via /baixar). Caso contrario
o arquivo aparece duas vezes no Downloads."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src_main():
    with open(os.path.join(BASE, "main.py"), encoding="utf-8") as f:
        return f.read()


def test_main_nao_referencia_copiar_para_downloads():
    src = _src_main()
    assert "_copiar_para_downloads" not in src, (
        "main.py ainda copia o arquivo para o Downloads; isso causa download "
        "duplicado do plano de corte (servidor + navegador)."
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_downloads.py -v`
Expected: FAIL (a string `_copiar_para_downloads` ainda existe em `main.py`).

- [ ] **Step 3: Remover o helper e as 4 chamadas**

Em `main.py`, **apagar** a definição do helper (linhas ~213-220):

```python
def _copiar_para_downloads(caminho):
    import shutil as _sh
    try:
        dl = os.path.join(os.path.expanduser('~'), 'Downloads')
        if os.path.isdir(dl):
            _sh.copy2(caminho, os.path.join(dl, os.path.basename(caminho)))
    except Exception:
        pass
```

E **apagar** as 4 linhas de chamada (manter o resto do contexto intacto):
- em `_exportar` (~463): `        _copiar_para_downloads(caminho)`
- em `_exportar_particao` caso 1 parte (~629): `            _copiar_para_downloads(arquivos[0])`
- em `_exportar_particao` caso zip (~639): `        _copiar_para_downloads(zip_cam)`
- em `_exportar_multiref` (~650): `        _copiar_para_downloads(caminho)`

Reconferir com `grep -n _copiar_para_downloads main.py` que **zero** ocorrências restam.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_downloads.py -v`
Expected: PASS.

- [ ] **Step 5: Verificação manual**

Rodar `python main.py`, calcular um plano, exportar. Conferir que o arquivo aparece **uma única vez** em `~/Downloads` (antes apareciam dois: o copiado pelo servidor e o baixado pelo navegador). O arquivo continua salvo em `dados/resultados/`.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_export_downloads.py
git commit -m "fix(export): remove copia ao Downloads (corrige download duplicado do plano)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: A3 — `alocar_rolos` devolve bloco `params`

**Files:**
- Modify: `engine/alocador_rolos.py` (montagem do `return` final ~356-366)
- Test: `tests/test_alocador_rolos.py` (existente — adicionar 1 teste)

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `tests/test_alocador_rolos.py` (reusa `CONFIG_BASE` já definido no arquivo):

```python
def test_resultado_inclui_bloco_params():
    """A3: o resultado deve carregar os parametros de alocacao usados, para
    aparecerem no Excel sem depender do frontend."""
    plano = {
        "mapas": [{"id": 0, "n_pecas": 4}],
        "camadas": {"AZUL": {0: 3}},
        "consumo_peca": 1.0,
    }
    rolos = {"AZUL": [20.0]}
    cfg = dict(CONFIG_BASE)
    cfg["margem_seguranca_enfesto_m"] = 0.10
    cfg["folga_incerteza_pct"] = 0.03
    cfg["folga_incerteza_m"] = 0.0
    cfg["ponta_minima_util_m"] = 0.5

    res = alocar_rolos(plano, rolos, cfg)

    assert "params" in res
    p = res["params"]
    assert p["margem_seguranca_enfesto_m"] == 0.10
    assert p["folga_incerteza_pct"] == 0.03
    assert p["folga_incerteza_m"] == 0.0
    assert p["ponta_minima_util_m"] == 0.5
```

(Confirme que o topo do arquivo já tem `from engine.alocador_rolos import alocar_rolos` — está lá. `CONFIG_BASE` é o dict de config de teste do arquivo.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alocador_rolos.py::test_resultado_inclui_bloco_params -v`
Expected: FAIL com `KeyError: 'params'` / `assert 'params' in res`.

- [ ] **Step 3: Adicionar o bloco `params` ao retorno**

Em `engine/alocador_rolos.py`, no fim de `alocar_rolos`, **antes** do `return` final (~366). Hoje:

```python
    return {"por_cor": resultado_por_cor, "resumo_geral": resumo_geral}
```

Trocar por:

```python
    params = {
        "margem_seguranca_enfesto_m": round(float(margem), 4),
        "folga_incerteza_pct": float(config.get("folga_incerteza_pct", 0.03)),
        "folga_incerteza_m": float(config.get("folga_incerteza_m", 0.0)),
        "ponta_minima_util_m": float(ponta_min),
    }
    return {"por_cor": resultado_por_cor, "resumo_geral": resumo_geral, "params": params}
```

(`margem` e `ponta_min` já são variáveis locais — `margem` vem de `_validar_entradas` ~136, `ponta_min` ~137.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alocador_rolos.py -v`
Expected: PASS (incluindo o novo teste; os 18 existentes continuam passando — checam chaves específicas, não igualdade exata do dict).

- [ ] **Step 5: Commit**

```bash
git add engine/alocador_rolos.py tests/test_alocador_rolos.py
git commit -m "feat(alocador): retorna bloco params (margem/folga/ponta) para o export

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: A3 — Helper de parâmetros + cabeçalho do plano single

**Files:**
- Modify: `exportar/export_xlsx.py` (novo helper; `_aba_resumo` c2.value ~153)
- Test: `tests/test_export_params.py` (criar)

- [ ] **Step 1: Write the failing test (helper puro)**

Cria `tests/test_export_params.py`:

```python
"""A3: o cabecalho das planilhas deve conter todos os parametros do calculo."""
from exportar.export_xlsx import _resumo_parametros_txt


def _cfg():
    return {
        "consumo_peca_m": 1.0645,
        "mesa_comprimento_m": 10,
        "limite_folhas_padrao": 70,
        "desvio_absoluto_padrao": 4,
        "desvio_percentual_padrao": 20,
        "criterio_combinacao": "MIN",
        "num_opcoes_saida": 2,
        "timeout": 120,
        "tempo_processamento_s": 12.3,
        "versao": "2.10.1",
        "regras_especiais": {"G": {"hi": 0}},
    }


def test_resumo_parametros_txt_tem_todos_os_campos():
    s = _resumo_parametros_txt(_cfg())
    for marca in ["Consumo", "Mesa", "Folhas", "Tol. abs", "Tol. %",
                  "Criterio", "Opcoes", "Timeout", "Tempo real",
                  "Limites especiais", "Versao"]:
        assert marca in s, f"faltou '{marca}' em: {s}"
    assert "1.0645" in s
    assert "MIN" in s
    assert "120" in s
    assert "2.10.1" in s
    assert "G" in s  # limite especial


def test_resumo_parametros_txt_sem_campos_opcionais():
    """Sem timeout/tempo/regras nao deve quebrar."""
    s = _resumo_parametros_txt({"consumo_peca_m": 1.0, "mesa_comprimento_m": 10,
                                "limite_folhas_padrao": 70})
    assert "Consumo" in s
    assert "Timeout" in s          # mostra "—"
    assert "Limites especiais" in s  # mostra "nenhum"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_params.py -v`
Expected: FAIL com `ImportError: cannot import name '_resumo_parametros_txt'`.

- [ ] **Step 3: Implementar o helper e usá-lo no `_aba_resumo`**

Em `exportar/export_xlsx.py`, adicionar o helper logo antes de `def _aba_resumo(` (~131):

```python
def _resumo_parametros_txt(config):
    """Monta a linha de parametros do calculo para o cabecalho das planilhas.
    Le tudo de `config` (fonte unica). Campos ausentes viram '—'/'nenhum'."""
    def g(k, d=None):
        v = config.get(k, d)
        return d if v is None else v

    regras = config.get("regras_especiais") or {}
    if regras:
        partes = []
        for t, r in regras.items():
            lo = r.get("lo", "")
            hi = r.get("hi", "")
            partes.append(f"{t}[{lo}..{hi}]")
        regras_txt = ", ".join(partes)
    else:
        regras_txt = "nenhum"

    timeout = config.get("timeout")
    tempo   = config.get("tempo_processamento_s")
    return (
        f"Consumo: {g('consumo_peca_m', 1.0645)} m/pc"
        f"  |  Mesa: {g('mesa_comprimento_m', 10)} m"
        f"  |  Folhas/enfesto: {g('limite_folhas_padrao', 70)}"
        f"  |  Tol. abs: {g('desvio_absoluto_padrao', '—')} pc"
        f"  |  Tol. %: {g('desvio_percentual_padrao', '—')}%"
        f"  |  Criterio: {g('criterio_combinacao', '—')}"
        f"  |  Opcoes: {g('num_opcoes_saida', '—')}"
        f"  |  Timeout: {timeout if timeout is not None else '—'} s"
        f"  |  Tempo real: {round(tempo, 1) if tempo is not None else '—'} s"
        f"  |  Limites especiais: {regras_txt}"
        f"  |  Versao {g('versao', '—')}"
    )
```

E trocar a `c2.value` de `_aba_resumo` (~153). Hoje:

```python
    c2.value = f"Gerado em {ts}  |  Consumo: {config.get('consumo_peca_m',1.0645)}m/pç  |  Mesa: {config.get('mesa_comprimento_m',10)}m  |  Limite folhas/enfesto: {config.get('limite_folhas_padrao',70)}"
```

Por:

```python
    c2.value = f"Gerado em {ts}  |  " + _resumo_parametros_txt(config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_params.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add exportar/export_xlsx.py tests/test_export_params.py
git commit -m "feat(export): cabecalho do plano single com todos os parametros

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: A3 — Cabeçalho do plano multi-ref

**Files:**
- Modify: `exportar/export_xlsx.py` (`_aba_resumo_multiref` assinatura ~760 e c2.value ~782; call site em `exportar_multiref` ~1084)
- Test: `tests/test_export_params.py` (adicionar)

- [ ] **Step 1: Write the failing test (isolation do `_aba_resumo_multiref`)**

Adicionar a `tests/test_export_params.py`:

```python
import openpyxl
from exportar.export_xlsx import _aba_resumo_multiref


def test_aba_resumo_multiref_cabecalho_tem_params():
    sol = {
        "n_mapas": 1,
        "refs_sol": [{"nome": "REF1"}],
        "resumo": {"total_folhas": 10, "desvio_total": 2,
                   "comprimento_total": 50.0, "media_pecas_mapa": 6.0},
    }
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _aba_resumo_multiref(wb, [sol], "GrupoX", _cfg())
    a2 = wb["Resumo"]["A2"].value
    assert "Tol. abs" in a2 and "Criterio" in a2 and "Versao" in a2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_params.py::test_aba_resumo_multiref_cabecalho_tem_params -v`
Expected: FAIL — `_aba_resumo_multiref` ainda recebe `(wb, solucoes, referencia)` (3 args), o teste passa 4 → `TypeError`.

- [ ] **Step 3: Mudar assinatura, call site e c2.value**

Em `exportar/export_xlsx.py`:

(a) Assinatura (~760): de
```python
def _aba_resumo_multiref(wb, solucoes, referencia):
```
para
```python
def _aba_resumo_multiref(wb, solucoes, referencia, config=None):
    config = config or {}
```

(b) c2.value (~782): de
```python
    c2.value = f"Gerado em {ts}  |  Enfesto combinado: {n_refs} refs  |  {n} opção(ões)"
```
para
```python
    c2.value = (f"Gerado em {ts}  |  Enfesto combinado: {n_refs} refs  |  {n} opcao(oes)"
                f"  |  " + _resumo_parametros_txt(config))
```

(c) Call site em `exportar_multiref` (~1084): de
```python
    _aba_resumo_multiref(wb, solucoes, referencia)
```
para
```python
    _aba_resumo_multiref(wb, solucoes, referencia, config)
```

(No multi-ref o consumo é por referência; por isso o helper não mostra um consumo único — mostra mesa/tol/critério/opções/timeout/tempo/versão, que são compartilhados.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_params.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add exportar/export_xlsx.py tests/test_export_params.py
git commit -m "feat(export): cabecalho multi-ref recebe config e mostra parametros

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: A3 — Parâmetros no Excel da alocação

**Files:**
- Modify: `exportar/export_xlsx.py` (`exportar_alocacao` assinatura ~1206 e call ~1229; `_aba_resumo_alocacao` assinatura ~1096 e corpo)
- Test: `tests/test_export_params.py` (adicionar — integração com `alocar_rolos`)

- [ ] **Step 1: Write the failing test (integração alocação)**

Adicionar a `tests/test_export_params.py`:

```python
import os, tempfile
import openpyxl
from engine.alocador_rolos import alocar_rolos
from exportar.export_xlsx import exportar_alocacao


def test_export_alocacao_mostra_parametros():
    plano = {"mapas": [{"id": 0, "n_pecas": 4}],
             "camadas": {"AZUL": {0: 3}}, "consumo_peca": 1.0}
    cfg = {"margem_seguranca_enfesto_m": 0.10, "folga_incerteza_pct": 0.03,
           "folga_incerteza_m": 0.0, "ponta_minima_util_m": 0.5}
    res = alocar_rolos(plano, {"AZUL": [20.0]}, cfg)

    with tempfile.TemporaryDirectory() as d:
        params = {**res["params"], "versao": "2.10.1"}
        cam = exportar_alocacao(res, "TESTE", d, params)
        wb = openpyxl.load_workbook(cam)
        ws = wb["Resumo Alocacao"]
        textos = " ".join(str(c.value) for row in ws.iter_rows()
                           for c in row if c.value is not None)
    assert "Margem" in textos
    assert "Folga" in textos
    assert "Ponta minima" in textos
    assert "2.10.1" in textos
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_export_params.py::test_export_alocacao_mostra_parametros -v`
Expected: FAIL — `exportar_alocacao` recebe `(resultado, referencia, pasta_saida)` (3 args), o teste passa 4 → `TypeError`.

- [ ] **Step 3: Mudar assinaturas e adicionar a seção de params**

Em `exportar/export_xlsx.py`:

(a) `exportar_alocacao` (~1206): assinatura
```python
def exportar_alocacao(resultado, referencia, pasta_saida, params=None):
```
e o call interno (~1229):
```python
    _aba_resumo_alocacao(wb, resultado, referencia, params)
```

(b) `_aba_resumo_alocacao` (~1096): assinatura
```python
def _aba_resumo_alocacao(wb, resultado, referencia, params=None):
```
e, logo após o cabeçalho (depois do bloco que escreve o título `r += 1`, ~1106), **antes** de `resumo = resultado.get(...)`, inserir uma seção de parâmetros:

```python
    from datetime import datetime as _dt
    params = params or resultado.get("params") or {}
    _cel(ws, r, 1, "Parametros da alocacao", negrito=True, fundo=C_AZUL_MED, cor_txt=C_BRANCO)
    ws.merge_cells(f"A{r}:B{r}")
    r += 1
    folga_pct = params.get("folga_incerteza_pct")
    linhas_param = [
        ("Margem de faca por sub-enfesto (m)", params.get("margem_seguranca_enfesto_m", "—")),
        ("Folga de incerteza (%)", round(folga_pct * 100, 2) if folga_pct is not None else "—"),
        ("Folga de incerteza fixa (m)", params.get("folga_incerteza_m", "—")),
        ("Ponta minima util (m)", params.get("ponta_minima_util_m", "—")),
        ("Versao", params.get("versao", "—")),
        ("Gerado em", _dt.now().strftime("%d/%m/%Y %H:%M")),
    ]
    for label, valor in linhas_param:
        _cel(ws, r, 1, label, fundo=C_CINZA_HDR, negrito=True)
        _cel(ws, r, 2, valor, alinha="right")
        r += 1
    r += 1
```

(O label "Folga de incerteza (%)" garante que o teste encontre "Folga"; "Ponta minima util (m)" garante "Ponta minima"; a versão garante "2.10.1".)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_export_params.py -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add exportar/export_xlsx.py tests/test_export_params.py
git commit -m "feat(export): planilha de alocacao mostra parametros usados

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: A3 — `main.py` monta o `config`/`params` antes de exportar

**Files:**
- Modify: `main.py` (`_calcular` resp ~436-443; `_exportar` ~451-464; `_exportar_multiref` ~642-651; `_exportar_alocacao` ~698-707; `_exportar_particao` ~604-621)

Sem teste automatizado (handlers HTTP não têm harness no projeto). Verificação manual no Step final. As Tasks 3-5 já provam o lado do export dado um `config`/`params` correto.

- [ ] **Step 1: `_calcular` — incluir `regras_especiais` na resposta**

Em `main.py`, no dict `resp` de `_calcular` (~436-443), adicionar a chave (`regras` já está em escopo, definida ~324):

```python
        resp = {
            "solucoes"  : ser(solucoes),
            "tamanhos"  : tamanhos,
            "grade"     : grade,
            "limites"   : {c: {t: list(l) for t,l in ts.items()} for c,ts in limites.items()},
            "config"    : cfg,
            "versao"    : VERSION,
            "regras_especiais": regras,
        }
```

- [ ] **Step 2: `_exportar` — injetar versão/timeout/tempo/regras no config**

Em `_exportar` (~451-464), entre `cfg = p.get("config", carregar_config())` e a chamada `exportar_xlsx(...)`, inserir:

```python
        cfg["versao"]                = VERSION
        cfg["timeout"]               = p.get("timeout")
        cfg["tempo_processamento_s"] = p.get("tempo_s")
        cfg["regras_especiais"]      = p.get("regras_especiais", cfg.get("regras_especiais"))
```

(O `_copiar_para_downloads(caminho)` já foi removido na Task 1.)

- [ ] **Step 3: `_exportar_multiref` — idem (sem regras/consumo único)**

Em `_exportar_multiref` (~642-651), entre `config = p.get("config", carregar_config())` e a chamada `exportar_multiref_xlsx(...)`, inserir:

```python
        config["versao"]                = VERSION
        config["timeout"]               = p.get("timeout")
        config["tempo_processamento_s"] = p.get("tempo_s")
```

- [ ] **Step 4: `_exportar_alocacao` — passar `params` (com versão)**

Em `_exportar_alocacao` (~698-707), trocar a chamada:

```python
            caminho = exportar_alocacao_xlsx(resultado, referencia, pasta)
```
por:

```python
            params  = {**(resultado.get("params") or {}), "versao": VERSION}
            caminho = exportar_alocacao_xlsx(resultado, referencia, pasta, params)
```

- [ ] **Step 5: `_exportar_particao` — injetar versão/timeout/tempo por grupo**

Em `_exportar_particao`, dentro do loop `for g in grupos:` (~604), após `cfg = data.get("config", carregar_config())` (~606), inserir:

```python
            cfg["versao"]                = VERSION
            cfg["timeout"]               = data.get("timeout")
            cfg["tempo_processamento_s"] = data.get("tempo_s")
            cfg["regras_especiais"]      = data.get("regras_especiais", cfg.get("regras_especiais"))
```

- [ ] **Step 6: Verificação manual**

Rodar `python main.py`. Calcular um plano single, exportar, abrir o `.xlsx` → aba **Resumo**, célula A2 contém: Consumo, Mesa, Folhas/enfesto, Tol. abs, Tol. %, Criterio, Opcoes, Timeout, Tempo real, Limites especiais, **Versao 2.10.1**. Calcular multi-ref, exportar → idem (sem consumo único). Alocar rolos, exportar → aba **Resumo Alocacao** com seção "Parametros da alocacao" (margem, folga %, ponta mínima, versão, data/hora). (O timeout/regras só aparecem completos após a Task 8; tempo e versão já aparecem agora.)

- [ ] **Step 7: Run suite + commit**

Run: `python -m pytest tests/ -q` → todos passam.

```bash
git add main.py
git commit -m "feat(export): main injeta versao/timeout/tempo/regras e params da alocacao

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: A2 — Resultado some ao mudar parâmetro

**Files:**
- Modify: `interface.html` (banners antes de `#rb` ~306 e `#aloc-resultado` ~363; helpers + listener; esconder banner em `renderResultado` ~1325, `renderResultadoComComparacao` ~1372, `renderResultadoGrupos` ~1518, `iniciarAlocacao` ~1962)

Sem teste automatizado (JS vanilla, sem harness). Verificação manual no Step final. **Todo código novo em ASCII** (sem acento cru — usar entidades).

- [ ] **Step 1: Adicionar o banner do plano (`#rb-stale`)**

Em `interface.html`, **imediatamente antes** de `<div class="rb" id="rb">` (~306), inserir:

```html
<div id="rb-stale" style="display:none;background:var(--wnb,#fff8e1);border:1px solid var(--wn,#e0b000);border-radius:var(--r);padding:10px 14px;margin-bottom:10px;color:var(--wn,#8a6d00);font-size:13px">
  &#9888; Um parametro mudou. Recalcule o plano para atualizar o resultado.
</div>
```

- [ ] **Step 2: Adicionar o banner da alocação (`#aloc-stale`)**

Em `interface.html`, **imediatamente antes** de `<div id="aloc-resultado" ...>` (~363), inserir:

```html
<div id="aloc-stale" style="display:none;margin-top:10px;background:var(--wnb,#fff8e1);border:1px solid var(--wn,#e0b000);border-radius:var(--r);padding:8px 12px;color:var(--wn,#8a6d00);font-size:12px">
  &#9888; Um parametro mudou. Refaca a alocacao para atualizar.
</div>
```

- [ ] **Step 3: Adicionar helpers + listener delegado**

Em `interface.html`, **imediatamente antes** de `function limpar(){` (~1771), inserir:

```javascript
// ── A2: invalidar resultado ao mudar parametro ────────────────────────────
function _clearStaleCalculo(){ var b=document.getElementById('rb-stale'); if(b) b.style.display='none'; }
function _clearStaleAlocacao(){ var b=document.getElementById('aloc-stale'); if(b) b.style.display='none'; }

function _esconderResultadoPlano(){
  var rb=document.getElementById('rb');
  if(rb && rb.style.display!=='none'){ rb.style.display='none';
    var s=document.getElementById('rb-stale'); if(s) s.style.display='block'; }
  _esconderResultadoAlocacao(); // plano mudou -> alocacao tambem fica obsoleta
}
function _esconderResultadoAlocacao(){
  var ar=document.getElementById('aloc-resultado');
  if(ar && ar.style.display!=='none'){ ar.style.display='none';
    var s=document.getElementById('aloc-stale'); if(s) s.style.display='block'; }
}

var _CALC_PARAM_IDS = ['mesa','max_folhas','num_opcoes','tol_abs','tol_pct','criterio','timeout'];
var _ALOC_PARAM_IDS = ['aloc-margem','aloc-folga','aloc-ponta-min'];

function _onParamChange(e){
  var t=e.target; if(!t) return;
  var id=t.id||'';
  // Parametros so de alocacao -> invalida so a alocacao
  if(_ALOC_PARAM_IDS.indexOf(id)>=0 || (t.closest && t.closest('#aloc-cores-lista'))){
    _esconderResultadoAlocacao(); return;
  }
  // Parametros de calculo / grade / tolerancia especial -> invalida plano (e alocacao)
  if(_CALC_PARAM_IDS.indexOf(id)>=0
     || /^t(lo|hi|at)_/.test(id)
     || (t.closest && (t.closest('#tol-body') || t.closest('#ref-body')))){
    _esconderResultadoPlano();
  }
}
function _onToggleChange(){ _esconderResultadoPlano(); }  // cores/tamanhos mudam a grade

document.addEventListener('input',  _onParamChange);
document.addEventListener('change', _onParamChange);   // cobre <select> e checkbox
(function(){
  var cg=document.getElementById('cores-grid');   if(cg) cg.addEventListener('click', _onToggleChange);
  var tb=document.getElementById('tam-btns');     if(tb) tb.addEventListener('click', _onToggleChange);
})();
```

- [ ] **Step 4: Esconder o banner ao re-exibir o resultado**

Adicionar `_clearStaleCalculo();` logo após cada `document.getElementById('rb').style.display='block';`:
- em `renderResultado` (~1325)
- em `renderResultadoComComparacao` (~1372)
- em `renderResultadoGrupos` (~1518)

Exemplo (renderResultado ~1325):
```javascript
  document.getElementById('rb').style.display='block';
  _clearStaleCalculo();
```

E em `iniciarAlocacao`, após `resDiv.style.display = '';` (~1962), adicionar:
```javascript
    resDiv.style.display = '';
    _clearStaleAlocacao();
```

- [ ] **Step 5: Verificação manual**

`python main.py`. (a) Calcular um plano → resultado aparece. Mudar `mesa`/`tol_abs`/`num_opcoes`/`criterio` ou editar a grade de uma referência → `#rb` some e aparece o aviso "Recalcule"; a alocação também some. (b) Recalcular → aviso some, resultado volta. (c) Alocar rolos → resultado da alocação aparece. Mudar só `aloc-margem` ou um rolo → some **só** a alocação (o plano continua). (d) Refazer alocação → aviso some.

- [ ] **Step 6: Commit**

```bash
git add interface.html
git commit -m "feat(ui): esconde resultado quando um parametro do calculo/alocacao muda

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: A3 — Frontend envia `timeout` ao exportar

**Files:**
- Modify: `interface.html` (`exportar` ~1762; `exportarMultiref` ~1532; `exportarTodos` ~1551)

Sem teste automatizado. Verificação manual. `tempo_s` e `regras_especiais` já chegam ao export pela própria resposta de `/calcular` (Task 6, Step 1); falta só o `timeout` (que `/calcular` não ecoa).

- [ ] **Step 1: `exportar` — incluir timeout no corpo**

Em `interface.html`, na função `exportar` (~1762), trocar:

```javascript
    const r=await fetch('/exportar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
```
por:

```javascript
    var _tmo=parseInt((document.getElementById('timeout')||{}).value);
    const r=await fetch('/exportar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({}, d, {timeout: isNaN(_tmo)?null:_tmo}))});
```

- [ ] **Step 2: `exportarMultiref` — idem**

Em `exportarMultiref` (~1532), trocar:

```javascript
    const r=await fetch('/exportar_multiref',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
```
por:

```javascript
    var _tmo=parseInt((document.getElementById('timeout')||{}).value);
    const r=await fetch('/exportar_multiref',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({}, data, {timeout: isNaN(_tmo)?null:_tmo}))});
```

- [ ] **Step 3: `exportarTodos` — incluir timeout no body da partição**

Em `exportarTodos` (~1551), trocar:

```javascript
      const r=await fetch('/exportar_particao',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({grupos:grupos,referencia:'plano_completo'})});
```
por:

```javascript
      var _tmo=parseInt((document.getElementById('timeout')||{}).value);
      var _grupos=grupos.map(function(g){ return {tipo:g.tipo, data:Object.assign({}, g.data, {timeout: isNaN(_tmo)?null:_tmo})}; });
      const r=await fetch('/exportar_particao',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({grupos:_grupos,referencia:'plano_completo'})});
```

(Cada grupo carrega `timeout` em `data`, que o `_exportar_particao` lê via `data.get("timeout")` — Task 6 Step 5.)

- [ ] **Step 4: Verificação manual**

`python main.py`. Calcular (single e multi-ref), exportar. Abrir os `.xlsx` → célula A2 (Resumo) agora mostra **Timeout: 120 s** e **Limites especiais** com as regras que você definiu, além de Tempo real e Versao 2.10.1.

- [ ] **Step 5: Commit**

```bash
git add interface.html
git commit -m "feat(ui): exporta o timeout usado para aparecer no Excel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificação final da Frente A

- [ ] `python -m pytest tests/ -q` → todos os testes passam (74 antigos + novos).
- [ ] Manual: 1 arquivo no Downloads ao exportar (A1).
- [ ] Manual: mudar parâmetro esconde o resultado certo (A2).
- [ ] Manual: Excel (single, multi-ref, alocação) mostra todos os parâmetros e versão 2.10.1 (A3).
- [ ] Merge/integração conforme o fluxo do projeto (branch `melhorias-enfestos`).

---

## Self-Review (preenchido pelo autor do plano)

- **Cobertura do spec (Frente A):** A1 (Task 1) ✓; A2 (Task 7) ✓; A3 — params single (Task 3), multi-ref (Task 4), alocação (Tasks 2+5), wiring main (Task 6), frontend timeout (Task 8) ✓.
- **Sem placeholders:** todo step de código traz o código completo.
- **Consistência de tipos/nomes:** `_resumo_parametros_txt(config)` definido na Task 3 e reusado na Task 4; `params` definido na Task 2 (`alocar_rolos`) e consumido nas Tasks 5/6; `exportar_alocacao(..., params=None)` assinatura única; ids dos banners `rb-stale`/`aloc-stale` consistentes entre Tasks 1/7.
- **Observação de drift:** os números de linha são de 2026-06-24; reconferir antes de cada edição (especialmente após a Task 1, que remove ~8 linhas de `main.py` e desloca as seguintes).
