# Design — Melhorias do PCP Enfestos (Roadmap A→E)

- **Data:** 2026-06-24
- **Projeto:** `pcp_enfestos` (servidor Python local porta 5050, UI `interface.html`)
- **Versão atual:** 2.10.1
- **Dono:** Diego Faria (Charth)
- **Origem:** pedido de melhorias/correções no sistema de enfestos + análise de evolução.

Este documento é o spec único do roadmap. Cada frente (A→E) vira um ciclo próprio de implementação. Os números de linha foram verificados adversarialmente contra o código real em 2026-06-24; podem sofrer drift conforme as frentes são aplicadas em sequência (reconferir a cada frente).

---

## 1. Diagnóstico (verificado)

### 1.1 Pesos de eficiência são placebo
A UI envia `peso_enc`/`peso_op` → `main.py` grava em `cfg["peso_eficiencia_encaixe/operacional"]` (`main.py:318-319`, `498-499`) → passa ao solver. Mas:
- `engine/solver.py::_score_solucao` (152-179) usa pesos **fixos** `0.65/0.25/0.10` e **não lê** `peso_eficiencia_*`.
- O `score` calculado **não entra na ordenação**. A ordenação real é lexicográfica, em 4 sorts idênticos (`solver.py:358-362`, `387-389`; `solver_multiref.py:228-232`, `250-254`): `(n_mapas ↑, desvio_total ↑, media_pecas_mapa ↓)`.
- Os pesos só entram na **assinatura do cache** (`main.py:363`, `535`) — mexer neles força recálculo e dá a ilusão de efeito, mas o resultado é idêntico.

**Prova empírica:** rodando a grade Blazer Isadora com `enc=0.9/op=0.1`, `enc=0.1/op=0.9` e `0.6/0.4`, o resultado é **idêntico** célula a célula. → Decisão do dono: **remover da UI** (Frente D).

### 1.2 Download duplicado do plano de corte
`/exportar` (`main.py:463`), `/exportar_particao` (`629`, `639`) e `/exportar_multiref` (`650`) chamam `_copiar_para_downloads` (copia #1 ao Downloads) **e** o navegador baixa via `/baixar` (copia #2). `/exportar_alocacao` **não** copia → por isso só o plano de corte duplica. (Frente A1.)

### 1.3 Alocação de rolos — "tenho tecido mas não cobre" (reprodução empírica do VESTIDO CORINA)
Caso reconstruído e rodado no alocador real — bate exatamente com a planilha. 3 mapas single-ref, 6 peças × 1,3 m = **7,8 m por camada**.

| Cor | Rolos (m) | Déficit | Pontas estoque (m) | Σ pontas | Maior ponta |
|-----|-----------|---------|--------------------|----------|-------------|
| BLUES | 54,5 / 22,0 | 2 cam (15,6 m) | 5,87 + 5,64 | 11,50 | 5,87 |
| JAZZ | 60,0 / 22,0 | 2 cam (15,6 m) | 3,50 + 5,64 | 9,14 | 5,64 |
| PRETO | 50,0 / 22,0 | 1 cam (7,8 m) | 1,50 + 5,64 | 7,14 | 5,64 |
| SAMBA | 50,0 / 39,0 | 1 cam (7,8 m) | 1,60 + 6,53 | 8,13 | 6,53 |
| VALSA | 55,6 / 27,0 | 1 cam (7,8 m) | 7,03 + 2,69 | 9,72 | 7,03 |

- **Déficit reportado 54,6 m; refugo real 0; ponta reaproveitável 50,04 m.** Não é falta genuína de tecido.
- **Folga de 3% explica só 1 das 7 camadas faltantes** (zerá-la leva o déficit a 46,8 m). Não é a causa.
- **Causa raiz:** o alocador só consome tecido em **blocos de camada inteira** (7,8 m). A ponta de 5–7 m de cada rolo é grande o bastante para um corte parcial, mas insuficiente para uma camada cheia → classificada como estoque, déficit declarado.
- O "déficit" muitas vezes corta peças **já em excesso** (JAZZ tem +3 peças líquidas de sobra e ainda mostra 15,6 m de déficit).
- **Corte separado resolve quase tudo:** um corte avulso de k peças (`k×1,3 + 0,10 m`) cabe na maior ponta de cada cor — BLUES/JAZZ/PRETO/SAMBA 4 peças, VALSA 5. VALSA, SAMBA e JAZZ ficam 100% cobertos pelas próprias pontas; só PRETO fica marginalmente curto (<1 m).

### 1.4 Multi-aba
`ThreadingHTTPServer` (`main.py:840`) + `_calc_lock` (`206`) serializa cálculos — correto, porque o solver usa **estado global**: `engine/mapas.py::_mapas_historicos_injetar` (global, lido em 176-179), atributos de função `resolver._niveis_esgotados/_ultimo_n_explorado/_proximo_n/_skip_combos` (`solver.py:417-420`) e `resolver_multiref._convergiu` (`solver_multiref.py:245`). A fila de progresso `_progresso_fila` é **global única** com **drain destrutivo** (`/progresso` em `263-267` faz `list()` + `clear()`). Duas abas pollando se roubam mensagens. (Frente E1.)

### 1.5 Suíte de testes
Existe pytest em `tests/` — **74 testes verdes** (test_alocador_rolos 18, test_cache_planos 14, test_mapa_cores 13, test_fonte_vexta_pdf 9, test_updater 15, test_solver_multiref 5). Nenhum cobre `export_xlsx.py`, rotas HTTP nem concorrência. Os testes do alocador checam chaves específicas (sem igualdade exata do dict) → adicionar chaves novas ao retorno **não quebra**.

---

## 2. Decisões travadas

1. **Roadmap único**, frentes A→E em sequência. Cada uma é um ciclo de implementação.
2. **Pesos de eficiência: remover da UI** e documentar a hierarquia real.
3. **Multi-aba: abas seguras com fila** (abas/instâncias do navegador), distinta da feature de **multi-referência** ("abas de referência", que combinam várias referências num plano — não muda).
4. **PDF de alocação:** página HTML otimizada para impressão + `window.print()` (sem nova dependência Python). `fpdf2` fica como alternativa documentada.
5. **Preferência de grade:** critério de **desempate** por desvio relativo, sem piorar `(n_mapas, desvio_total)`.
6. **Encoding:** novos blocos em `interface.html` devem ser 100% ASCII (regra do projeto). Specs/markdown em UTF-8 via ferramenta de escrita (não PowerShell `Set-Content`).

---

## 3. Frente A — Correções rápidas

### A1 — Download duplicado
Remover as 4 chamadas de `_copiar_para_downloads` (`main.py:463, 629, 639, 650`) e o helper (`213-220`). O arquivo continua em `dados/resultados/` (histórico) e a entrega ao usuário fica só pelo `/baixar` (igual à alocação, que já funciona). Resultado: 1 arquivo no Downloads. **Comunicar ao dono:** muda de 2 para 1 arquivo.

### A2 — Resultado some ao mudar parâmetro
Hoje `#rb` some no início de `calcular()` (`959`) mas **não** quando um parâmetro muda com resultado na tela.
- Adicionar dois banners ocultos: `#rb-stale` (antes de `#rb`, linha 306) e `#aloc-stale` (antes de `#aloc-resultado`, 363) com aviso "Parâmetro alterado — recalcule".
- Listener por **delegação** ouvindo **`input` E `change`** (necessário: `criterio` e `num_opcoes` são `<select>`; `tat_*` é checkbox — só disparam `change`).
  - Params de cálculo (`mesa, consumo, max_folhas, num_opcoes, timeout, tol_abs, tol_pct, criterio, ^tlo_|^thi_|^tat_`, células da grade) → esconde `#rb` **e** `#aloc-resultado` (a alocação depende do plano).
  - Params só de alocação (`aloc-margem, aloc-folga, aloc-ponta-min`, inputs em `#aloc-cores-lista`) → esconde só `#aloc-resultado`.
  - Agir só quando o alvo estiver visível (no-op barato).
- Ao reexibir resultado, ocultar o banner: `renderResultado` (1325), `renderResultadoComComparacao` (1372), `renderResultadoGrupos` (1518), `iniciarAlocacao` (1962).
- Tolerante à ausência dos inputs de peso (removidos na Frente D).

### A3 — Todos os parâmetros no Excel
Adicionar bloco "Parâmetros do cálculo": `tol_abs`, `tol_pct`, `criterio`, `num_opcoes`, `timeout` (teto), **tempo real de processamento**, limites especiais por tamanho, versão, data/hora. Na alocação: margem de faca, folga de incerteza (%), ponta mínima útil.

Touchpoints e **gaps** descobertos na verificação:
| Arquivo | Local | Mudança |
|---|---|---|
| `export_xlsx.py` | `_aba_resumo` 132 (subtítulo 153) | já recebe `config`; expandir o cabeçalho. |
| `export_xlsx.py` | `_aba_resumo_multiref` 760 + call 1084 | **mudar assinatura** para receber `config`; consumo é **por-ref** (`solucoes[0]['refs_sol'][ri]['consumo']`), não de `config`. |
| `export_xlsx.py` | `exportar_alocacao` 1206 + `_aba_resumo_alocacao` 1096 + call 1229 | **mudar assinaturas** para receber `params`. |
| `engine/alocador_rolos.py` | retorno 366 | **Opção B (escolhida):** `alocar_rolos` devolve bloco `params: {margem_seguranca_enfesto_m, folga_incerteza_pct, folga_incerteza_m, ponta_minima_util_m}` — params chegam ao export sem depender do frontend; não quebra testes. |
| `main.py` | `_exportar` 463, `_exportar_multiref` 650 | injetar `config['versao']=VERSION` (o `cfg` repassado tem versão stale: config.json=2.9.0 ≠ VERSION 2.10.1). |
| `main.py` | `_calcular` resp 436 | adicionar `'regras_especiais': regras` ao resp (já em escopo na 324) para os limites especiais chegarem ao export. |
| `interface.html` | `exportar` 1757 / `exportarMultiref` 1529 / `exportarTodos` 1542 | incluir `timeout` no payload (o `/calcular` não o ecoa). `tempo_s` já chega no objeto reenviado. |

`tempo_s` já volta de `/calcular` (449) e `/calcular_grupo` (589) e é reenviado no objeto integral.

**Testes:** smoke verificando que os cabeçalhos das 3 funções contêm os params e a versão 2.10.1; teste de que `alocar_rolos` devolve o bloco `params`.

---

## 4. Frente B — Entrada & UI

### B1 — Células numéricas de rolo por cor
`_rolosPorCor` (`{cor: number[]}`) passa a ser a **fonte única de verdade**. Nenhum código deriva rolos de `inp.value` no envio.

- Substituir o `<input type=text>` único (1884-1891) por uma linha de células dentro de `#aloc-cores-lista` (350). Cada célula: `<input type="text" inputmode="decimal" class="aloc-cel" data-cor data-idx>` (vírgula decimal, `text-align:right`).
- N células = `Math.max(8, arr.length + 1)` (mínimo 8, sempre 1 vazia ao final). Ao preencher a última célula do DOM, anexar nova célula vazia via `appendChild` (sem re-render — preserva foco). Botão "+" manual também.
- **Tab** navega na ordem do DOM (inputs irmãos, sem tabindex custom).
- **Leitura** indexando **dentro da row** (`row.querySelectorAll('.aloc-cel')`) — evita seletor global e `CSS.escape` para cores com acento/aspas. Compacta vazias/inválidas, preserva ordem.
- **REMOVER** o snapshot `valoresSalvos` (1864-1868): hoje captura só a 1ª célula via `el.querySelector('input')` → corromperia o dado com múltiplas células. Renderizar direto de `_rolosPorCor`.
- `iniciarAlocacao` (1918): substituir o loop por rows (1927-1934) e o merge (1935-1937) por leitura direta de `_rolosPorCor`. Validação (1939) permanece.
- **Colar lote / PDF:** handler de `paste` (ou `_parseRolos`, regex `/[;\n\r]+/`) expande valores em células a partir do idx atual. Import PDF (`/importar_rolos` já existe em `main.py:709`, retorna `rolos_por_cor_comercial`) grava `_rolosPorCor[cor]=arr` e chama `atualizarCoresAlocacao()`. **Nota:** hoje não há caller JS de `/importar_rolos`; `_rolosPorCor` é o ponto de integração (ligar o fluxo de upload é trabalho à parte — ver §8).
- Rolos não são persistidos (`salvar_params` não os inclui) → sem formato a migrar.

### B2 — Percentual nas tolerâncias especiais (por-tamanho)
Campos `tlo_`/`thi_` aceitam absoluto (`4`, `-4`) **ou** percentual (`10%`).
- **Frontend:** `renderTol` (502): `tlo_`/`thi_` viram `type="text"`, placeholder `(auto) 4 ou 10%`. `lerRegras` (510): normalizar `(el?.value||'').trim()` (optional chaining retorna `undefined`, não `''`); vazio ignora; se termina com `%` valida o miolo e guarda **string** `"N%"`; senão `parseInt` (absoluto, **preserva o sinal**, ex. `-4`).
- **Formato em `regras_especiais`:** `{TAM: {lo?: number|string, hi?: number|string}}`, percentual sempre `"N%"`. JSON-safe; cache usa `json.dumps(default=str)`; retrocompatível.
- **Backend** (`tolerancia.py::calcular_limites`, ramo 17-26): helper `_resolver_limite(valor, grade_valor)` → magnitude inteira (percentual = `round(grade*pct/100)`; absoluto = `int`).
  - **CORREÇÃO CRÍTICA DE SINAL (erro pego na verificação):** o código atual faz `lo = int(r["lo"])`, **preservando o sinal digitado**. **Não** negar incondicionalmente. Só o ramo **percentual** nega a magnitude:
    - `lo` percentual (`"10%"`) → `-_resolver_limite(...)`
    - `lo` absoluto (int ou `"-4"`) → preserva o sinal
    - `hi` → `_resolver_limite(...)` (sempre positivo)
- Carregamento de plano (439-449): `lo.value=r.lo` já é cru; com `type=text` a string sobrevive. Sem mudança obrigatória.

**Decisão (sinal do `lo` percentual):** usuário digita **magnitude** (`10%`), backend nega. Bloquear `-` antes de `%` no front.

**Testes:** criar `test_tolerancia.py`: (1) absoluto int `lo=-4` permanece `-4`; (2) absoluto str `"-4"` → `-4`; (3) `hi` int `4` → `4`; (4) `hi` `"10%"` com grade 40 → `4`; (5) `lo` `"10%"` grade 40 → `-4`; (6) `"0%"` → 0; (7) `"10,5%"` (vírgula) → round; (8) ausentes → `±tol_geral`. Round-trip `lerRegras`→JSON→`calcular_limites`.

---

## 5. Frente C — Alocação de rolos (núcleo)

Premissas confirmadas no código: empacotamento **dentro** de cada rolo já é completo (re-testa todos os mapas pendentes por sub-enfesto, `alocador_rolos.py:243`); pontas **não** são reaproveitadas entre rolos; `comp_camada_m` explícito por mapa já é honrado (148); **margem de faca paga 1× por sub-enfesto** (272).

### C1 — Reaproveitamento de pontas + corte separado (passo pós-alocação)
Novo módulo `engine/reaproveitamento.py` (função pura), chamado dentro de `alocar_rolos` **após** montar `resultado_por_cor` e **antes** do `return` (366). **Não altera** o plano nem a alocação principal — só anexa chaves.

Para cada cor com déficit (`camadas_em_deficit`, chaves int):
1. Coletar pontas estoque (`ponta_classe=='estoque'`) da cor: lista de `(indice_rolo, ponta_m)`, ordenada desc.
2. Gerar submapas candidatos a partir do déficit: (a) camada inteira do mapa em déficit; (b) submapas reduzidos (subconjuntos da composição — 50%, 1-de-cada) **quando** a camada inteira não cabe. `comp = n_peças_sub × cpp[mid]`, onde `cpp[mid] = comp_camada_por_id[mid] / n_pecas[mid]`.
3. Casar submapa→pontas (FFD), com a **margem correta** (erro pego na verificação): capacidade `k*comp + margem ≤ ponta` (margem 1× por sub-enfesto, **não** por camada):
   ```
   k = floor((ponta - margem + EPS) / comp)   # EPS = 0.0001
   if k > 0: k = min(k, n_falta); ponta -= (k*comp + margem); n_falta -= k
   ```
   **Sem emenda garantido:** cada conjunto de k camadas casa contra **uma** ponta individual, nunca somando duas.

Saída anexada por cor:
```json
por_cor[cor]["sugestoes_corte_separado"] = [
  {"mapa_id":0,"rotulo":"camada inteira","composicao":{"P":2,"M":2},
   "comp_camada":4.258,"camadas_cobertas":1,
   "cortes":[{"rolo_origem_indice":0,"n_camadas":1,"comp_camada":4.258,
              "comp_total":4.358,"ponta_usada_m":4.9}],
   "deficit_residual_camadas":0}
]
```
E `resumo_geral["sugestoes_corte_total"]`. Sem ponta útil → lista vazia → UI mantém "comprar X m" (intocado).

**Atenção (gap pego na verificação):** o ramo "sem rolos" (`alocador_rolos.py:184-194`) monta `resultado_por_cor[cor]` separadamente — anexar `sugestoes_corte_separado: []` e `sobras_por_rolo: []` **também** lá, senão a UI/PDF que itera `por_cor` quebra.

**2ª passada de balanceamento entre rolos:** NÃO na v1 (risco de regressão; o ganho pedido é 100% atendido pelo corte separado).

### C2 — Re-entrada dos mapas do Audaces (UI)
Backend já honra `comp_camada_m` (148; teste `test_comp_camada_m_explicito_tem_prioridade` cobre). Falta UI:
- Bloco "Mapas / comprimento real" antes de Alocar: por mapa, comp calculado (read-only) + input "comprimento real (Audaces) [m]" (vazio = usa calculado).
- `window._compRealAudaces = {mid: valor}`. Em `_montarPlanoParaAlocacao` (1967), nas chamadas `mapas.push` (1982 single, 2000 multi), sobrescrever `comp_camada_m` por `real>0 ? real : calc`.
- **Atenção ao id:** `mid` é sequencial 0..n reatribuído a cada montagem — renderizar a UI de mapas a partir da **mesma** montagem para casar o índice. Re-alocar reusa `iniciarAlocacao` (1918). Badge "ajustado" quando `real != calc`. Alerta CRÍTICO do alocador (200-206) se real > maior rolo seguro.

### C3 — Relatório de sobras por rolo
Tudo já existe no retorno (`ponta_m`, `ponta_classe`, `refugo_real_m`); falta consolidar. Por cor:
```json
por_cor[cor]["sobras_por_rolo"] = [
  {"rolo_indice":1,"nominal_m":54.5,"seguro_m":52.87,"usado_m":...,
   "ponta_m":5.87,"ponta_classe":"estoque","reaproveitada_em":null}
]
```
`reaproveitada_em` preenchido pelo C1 quando a ponta vira corte separado. `resumo_geral["sobras_consolidado"] = {cor: {ponta_estoque_m, refugo_m, n_pontas_estoque}}`. Custo zero (derivado de `rolos_resultado`). UI: tabela "Sobras por rolo" no `<details>` de cada cor.

### C5 — Relatório de alocação para impressão (print-view HTML + `window.print()`)
- Dados de `window._ultimaAlocacao.data` + `.referencia` (1963). Sem novo fetch.
- Botão "Imprimir relatório" ao lado de "Exportar (.xlsx)" (2142). Função `abrirRelatorioAlocacao()`: `window.open` → `document.write(html)` → `onload` → `print()` (disparar no handler de clique direto, por causa de popup blocker).
- **Layout:** (1) cabeçalho ref+data; (2) resumo geral; (3) por cor (`page-break-before:always`): total de folhas, folhas de cada rolo em cada enfesto, linha "↻ ponta reaproveitada" (C1); (4) sobras totais por rolo + "Corte separado sugerido" (C1) + residual "comprar X m"; (5) CSS `@media print` escondendo botões/inputs. Usar entidades HTML (evita vazar mojibake). Layout neutro, econômico em tinta.
- *Só na alocação — não toca o cálculo do plano.* Alternativa documentada: `fpdf2` (`.pdf` baixável) se o dono quiser um arquivo de verdade.

**Touchpoints C:** `engine/alocador_rolos.py` (return 366; ramo sem-rolos 184-194; derivar `cpp`/`composicao` de 142-153); novo `engine/reaproveitamento.py`; `interface.html` (`_montarPlanoParaAlocacao` 1967-2024, `_renderResultadoAlocacao` 2082-2144, botões 2141-2142, nova `abrirRelatorioAlocacao`); `export_xlsx.py` opcional (`_aba_cor_alocacao` 1139-1203 — seções de sobras/corte separado). Nada pré-existente colide (grep de `sugestoes_corte`/`sobras_por_rolo`/`_compRealAudaces` = 0).

**Testes:** (1) déficit coberto por ponta grande, k camadas com 1 margem; (2) sem ponta útil → sugestões vazias, `tecido_a_comprar_m` inalterado; (3) submapa reduzido quando camada inteira não cabe; (4) **trava do bug corrigido**: ponta que cabe `k*comp` mas não `k*comp+margem` → `k-1`; (5) `sobras_por_rolo` bate com os agregados; (6) ramo sem-rolos retorna chaves vazias (não KeyError).

---

## 6. Frente D — Solver

### D1 — Remover pesos de eficiência + limpar código morto
Ordem segura: UI → `main.py` → `config.json` → `tolerancia.py`/`solver.py` → `export_xlsx.py` → testes → CLAUDE.md.

| Arquivo | Local | Mudança |
|---|---|---|
| `interface.html` | 171-185 | remover os 2 campos de peso (inputs, span `#peso-total`, hints). |
| `interface.html` | 117-120 | remover CSS `.peso-wrap/.peso-total/.err` (uso exclusivo). |
| `interface.html` | **411** e 451 | remover **ambas** as chamadas `sincPeso('enc')` (window.onload **e** `carregarDados`). Erro pego na verificação: omitir a 411 causaria ReferenceError no load. |
| `interface.html` | 429-430 | remover restauração de `p.peso_enc/p.peso_op` (função real: `carregarDados`, não `carregarParams`). |
| `interface.html` | 467-485 | remover `sincPeso` inteira. |
| `interface.html` | 944-945, 969, 1157 | remover `peso_enc/peso_op` da coleta, de `baseParams` e do payload single. |
| `main.py` | 318-319, 339-340, 363, 498-499, 535 | remover `cfg["peso_eficiencia_*"]`, do `salvar_params` e das 2 assinaturas de cache. |
| `config.json` | 8-9, 23-24 | remover `peso_eficiencia_*` e `peso_fragmentacao/peso_ponta_util` (config morto, 0 leitores). |
| `engine/solver.py` | 10 | remover `custo_desvio` e `check_viavel` do import (nunca chamados; manter `desvio_absoluto_total`). |
| `engine/solver.py` | 152-179, 326, 337 | remover `_score_solucao`, a chamada e o campo `score`. |
| `export_xlsx.py` | **607** | **CORREÇÃO (erro pego):** a coluna "Score otimização" **lê** `s.get('score')`. **Substituir** por "Desvio relativo" (`s['resumo']['desvio_relativo']`, da Frente D2) — métrica real, não morta. |
| `engine/tolerancia.py` | 56-95 | remover `custo_desvio` (morta). |
| `config.json` | 10-17 | `peso_desvio_por_tamanho` + `tamanhos_prioritarios_positivo` só lidos por `custo_desvio` → remover junto (**confirmar com o dono**, §8). |
| `tests/test_solver_multiref.py` | 22-25 | remover chaves de peso do CFG de teste. |
| `tests/test_alocador_rolos.py` | 24-25 | remover `peso_fragmentacao/peso_ponta_util` de `CONFIG_BASE`. |
| `CLAUDE.md` | 199-202 + premissas | documentar a hierarquia **real**: `(n_mapas ↑, desvio_total ↑, media_pecas_mapa ↓, desvio_relativo ↑)`. Sem pesos configuráveis. |

**Cache:** remover chaves da assinatura orfana entradas antigas — inofensivo (1 recálculo por grade, resultado idêntico). Opcional limpar `cache_planos.json` no deploy.

### D2 — Preferência de ajuste nas quantidades maiores (desempate por desvio relativo)
Fórmula (protege grade=0): `desvio_relativo_total = Σ_{cor,t} |cortado-grade| / max(grade, 1)`.

- **(a) em `_resolver_folhas_cor`:** `eval_fs` (50-62) passa a retornar `(d, d_rel, ok)` com `d_rel` no mesmo loop. Atualizar os **4** call sites (`72, 110, 119, 125`) e desempatar por menor `d_rel` quando `d` empata (em `best_feas_dev` 111/126, `best_local_dev` 128, e no N=1 73). Manter o curto-circuito `best_feas_dev==0`.
- **(b) na ordenação final:** acumular `desvio_relativo` por solução e gravar em `resumo['desvio_relativo']`; adicionar como **última** chave dos 4 sorts: `(n_mapas, desvio_total, -media_pecas_mapa, desvio_relativo)`. Por ser a última chave, **nunca** altera as métricas primárias — só reordena empates exatos. Em multiref a chave de desvio é `s['desvio_total']` (top-level); em solver.py é `s['resumo']['desvio_total']`.

**Baseline anti-regressão (Blazer Isadora, timeout fixo):**
- SOL1: `(n_mapas=2, desvio_total=39)`, desvio_relativo ref 2,2159.
- SOL2: `(n_mapas=3, desvio_total=13)`, desvio_relativo ref 0,7811.
- A Frente D **não pode piorar** `(n_mapas, desvio_total)` de nenhuma posição.

**Testes novos:** (1) `test_solver_blazer_isadora` (trava das métricas primárias); (2) desempate por desvio relativo (2 combos mesmo `(n_mapas, desvio, media)`, distribuições diferentes); (3) grade=0 sem divisão por zero; (4) `eval_fs` retorna 3-tupla (guarda contra esquecer um call site).

---

## 7. Frente E — Plataforma & análise

### E1 — Multi-aba seguro com fila (progresso por job)
Manter `_calc_lock` (serializa o estado global do solver — **não** mover `resolver` para fora do lock). Trocar a fila global única por progresso por job.

**Backend (`main.py`):**
- Globais: `_progressos = {}` (job_id→list), manter `_progresso_lock`/`_calc_lock`, `import uuid`.
- Helpers: `_novo_job()`, `_add_progresso(job_id,msg)`, `_drain_job(job_id)`, `_fim_job(job_id)`.
- `GET /progresso?job=ID` (263): `{"msgs": _drain_job(job), "fim": job not in _progressos}`; sem `job` → `{"msgs":[]}` (degradação graciosa).
- `_calcular` (309-449) / `_calcular_grupo` (489-589): `job_id = p.get('job_id') or _novo_job()`; `cb` usa `_add_progresso(job_id,...)`; remover os `clear()` globais (380-381, 545-546); `_fim_job(job_id)` no fim; devolver `job_id`.
- **Indicador "na fila"** — aquisição non-blocking:
  ```python
  if not _calc_lock.acquire(blocking=False):
      _add_progresso(job_id, "Aguardando outro calculo terminar (na fila)...")
      _calc_lock.acquire()
  try: ...  # injeta históricos, resolve, lê atributos de retomada
  finally: _calc_lock.release()
  ```
- **GC de jobs órfãos** (aba fechada): limpeza por idade/quantidade em `_novo_job` (evita leak no dict).

**Frontend (`interface.html`):** gerar `jobId = crypto.randomUUID()...` por POST e injetar no body (payload single 1157→fetch 1233; retomada 1175; multiref indiv 1050-1051; grupo 1104-1105). Pollar só o seu: `fetch('/progresso?job='+jobId)` em `_drainProgresso` (907), setInterval Continuar (1173), setInterval single (1229). Parar quando `resp.fim` ou o await resolver (clearInterval já existe). Passar `jobId` a `_drainProgresso` nos call-sites (1053, 1107, 1178).

**Edge cases:** cache hit responde sem progresso (UI já limpa o interval pós-await); último poll vs `_fim_job` (fallback: campo `log` da resposta em 449/589; opcional atrasar `_fim_job` ~2s); reload perde jobId (`/progresso` sem job → `{msgs:[]}`); botão Continuar gera novo job. Multi-ref numa aba é **sequencial** (`await`, sem setInterval) — jobId muda a cada passo.

**Testes:** isolamento de mensagens entre 2 jobs; non-blocking emite "na fila"; `/progresso` sem job → `{msgs:[]}`; GC de órfãos.

### E2 — Análise de evolução (auditoria priorizada)

**Desempenho**
- **[D1] Coordinate-descent pode perder o ótimo** (`solver.py:79-137`, heurístico para N≥2). Impacto médio-alto; esforço alto. *Depois* (candidato a CP-SAT).
- **[D2] FFD não reaproveita pontas entre rolos/OPs** (`alocador_rolos.py`). Impacto **alto** (tecido = maior alavanca financeira); esforço médio. *Agora* (Frente C + F1).
- **[D3] Hardcap silencioso de 7 enfestos no multiref** (`solver_multiref.py:34 min(7,...)`); tetos mágicos (`K_por_ref` 49, `MAX_COMBIS` 101, `pool_sz` 124). Impacto médio; esforço baixo (documentar) a médio (adaptativo). *Depois* — instrumentar primeiro.
- **[D4] Solver exato opcional via OR-Tools CP-SAT** (modo atrás de checkbox, guloso como default; import lazy; ortools ~50 MB). Impacto alto; esforço alto. *Avaliar/prototipar.*
- **[D5] Cache cresce sem limite** (`cache_planos.py`). Impacto baixo-médio; esforço baixo (LRU). *Depois.*

**Confiabilidade**
- **[C1] Estado global do solver via atributos de função** — 4 atributos em `resolver` (`solver.py:417-420`), `_convergiu` em `resolver_multiref` (245), `_mapas_historicos_injetar` global (`mapas.py:13`). Seguro **só** porque `_calc_lock` serializa. Refatorar para **retornar** objeto-resultado + passar históricos por parâmetro. Impacto médio (alto se mexido sem entender); esforço médio. *Agora* (E1 depende de o lock cobrir isso). Adaptar `test_solver_multiref.py:70-81`.
- **[C2] Encoding garbled no `interface.html`** — cosmético. *Depois.*
- **[C3] Erro a prova de operador parcial** — 500 expõe `trace` cru (`main.py:305-307`); `except: pass` mudos (194-195, 219-220). Impacto médio; esforço baixo-médio. *Depois.*
- **[C4] Sem logs persistentes** (`log_message` silenciado 224; updater só `print`). Impacto médio-alto; esforço baixo (logging rotativo em `dados/logs/`). *Agora* — habilita diagnóstico de tudo.
- **[C5] Updater** — (a) **sem verificação de hash/assinatura** (só `is_zipfile`, `updater.py:196`); (b) extração nunca remove arquivos obsoletos (234-247); (c) rollback não reescreve `VERSION` (275-307). Impacto alto; esforço médio. *Agora* para (a).
- **[C6] Escritas não-atômicas** (`salvar_cores_arquivo` 116-120, `salvar_params` 128-131, `salvar_historico` 188-189). Impacto médio; esforço baixo (reusar `.tmp`+`os.replace`). *Agora.*

**Features**
- **[F1] Inventário persistente de pontas como estoque para OPs futuras** — `dados/estoque_pontas.json` (`{cor:[{id, comprimento_m, origem_op, data}]}`); injetar como "rolos virtuais" (`_alocar_rolos` já aceita `rolos` por cor); gravar/consumir ao fim. UI: aba "Estoque de pontas". Impacto **alto** (pedido do dono + economia); esforço médio. *Agora* (casa com D2/Frente C). Escrita atômica e sob lock.
- **[F2] Undo / histórico de planos navegável** — índice `dados/planos_gerados.json` + aba "Histórico". Impacto médio; esforço baixo-médio. *Depois.*
- **[F3] Validação de entrada** — handlers confiam no payload (`int/float(p.get(...))` lança 500 cru; grade aceita negativos). Impacto médio; esforço baixo. *Agora* (combina com C3).

**Resumo de prioridade**
- **Agora (→ Frente F):** refator estado global, logs, hash do update, escrita atômica, validação de entrada.
- **Depois:** F1 (estoque de pontas entre OPs), D3, D5, C2 (encoding), C3 (esconder trace), C5b/c (update), F2 (histórico).
- **Avaliar/prototipar:** D4 (CP-SAT) e, dependente, D1.

---

## 8. Decisões confirmadas (2026-06-24)

1. **F1 (estoque de pontas entre OPs): DESCARTADO (decisão do dono, 2026-06-25).** Nesta rodada, só o corte separado **dentro da OP atual** (Frente C1). O inventário persistente entre OPs chegou a ser implementado (Frente G) mas foi **revertido a pedido do dono**: ele não quer controlar estoque de pontas para planos futuros — a ponta é para reaproveitar **só no mesmo plano de corte**. NÃO reintroduzir.
2. **Itens "Agora" da auditoria: TODOS entram** — viram a **Frente F**: refatorar estado global do solver, logs persistentes, escrita atômica, validação de entrada e hash no auto-update.
3. **Frente D: remover tudo morto** — `custo_desvio` + `peso_desvio_por_tamanho` + `tamanhos_prioritarios_positivo`. A regra "G não cresce" permanece via limites de tolerância (G máx=0).
4. **Excel: substituir "Score otimização" por "Desvio relativo"** (métrica real, alimentada pela Frente D2).
5. **PDF de alocação: print-view HTML + `window.print()`** (sem dependência nova). `fpdf2` só se o dono pedir `.pdf` baixável depois.

## 9. Frente F — Confiabilidade & robustez (confirmada)

Itens da auditoria E2 promovidos a escopo. Independentes entre si, exceto **F-1**, acoplado à Frente E.

### F-1 — Refatorar estado global do solver (pré-req da Frente E)
`resolver` (`solver.py:417-420`) pendura 4 atributos na própria função (`_niveis_esgotados`, `_ultimo_n_explorado`, `_proximo_n`, `_skip_combos`); `resolver_multiref` usa `_convergiu` (245); `mapas.py:13` usa o global `_mapas_historicos_injetar`. Refatorar para **retornar** um objeto-resultado com esses campos e **receber históricos por parâmetro** (`priorizar_mapas`). Remove a dependência de "tudo sob o `_calc_lock`" e torna o multi-aba seguro por construção. Adaptar `main.py:399-401`/`562` e `tests/test_solver_multiref.py:70-81`. **Implementar junto com a Frente E (E1).**

### F-2 — Logs persistentes
Logging rotativo em `dados/logs/pcp.log` (cálculos, erros, updates). `Handler.log_message` está silenciado (`main.py:224`); o updater só faz `print` perdido (sem console no VBS). Habilita diagnóstico de todo o resto.

### F-3 — Escrita atômica
`salvar_cores_arquivo` (`main.py:116-120`), `salvar_params` (128-131) e `salvar_historico` (188-189) escrevem direto no arquivo final → crash no meio corrompe. Reusar `.tmp` + `os.replace` (já usado em `cache_planos.py:52-62`).

### F-4 — Validação de entrada
Handlers fazem `int/float(p.get(...))` direto → 500 cru com texto inválido; grade aceita negativos. Validação central com mensagens amigáveis, combinada com esconder o `trace` cru de `main.py:305-307`.

### F-5 — Hash no auto-update
`updater.py:196` só faz `is_zipfile`. Adicionar verificação de **SHA-256** do asset antes de aplicar (hoje uma release comprometida / MITM instala código arbitrário).

**Testes:** F-1 — `resolver`/`resolver_multiref` sem estado residual entre chamadas (cobrir os 4 atributos + `_convergiu`); F-3 — escrita atômica resiste a interrupção; F-5 — rejeita asset com hash divergente.

---

## 10. Sequenciamento de implementação

A → B → C → D → (E + F-1) → F (F-2..F-5), cada frente com seu plano (writing-plans) e validação.

- **A3** (params da alocação no Excel) depende do bloco `params` no retorno de `alocar_rolos` (Opção B) — coordenar com a **Frente C**, que já mexe nesse retorno. Pode-se fazer A1/A2 primeiro e A3 junto/depois de C.
- **F-1** (estado global) é pré-requisito de segurança da **Frente E** (multi-aba) — implementar juntos.
- **F-2 (logs)** e **F-3 (escrita atômica)** são independentes e de baixo risco; podem ser puxados para o início se ajudarem a depurar as demais frentes.
- Rodar `pytest tests/ -v` (74 verdes) antes e depois de cada frente.

## 11. Plano de testes (resumo)
- Rodar `pytest tests/ -v` (74 verdes) como baseline antes de cada frente e após.
- Frente A: smoke de cabeçalhos + bloco `params`; validação manual de 1 arquivo no Downloads.
- Frente B: `test_tolerancia.py` (8 casos + round-trip); B1 validado manualmente.
- Frente C: 6 testes do alocador/reaproveitamento (incl. trava do bug de margem).
- Frente D: baseline Blazer Isadora travado + desempate relativo + grade-zero + 3-tupla.
- Frente E1: isolamento por job + non-blocking + degradação sem job + GC.
- Frente F: solver sem estado residual; escrita atômica resiste a interrupção; update rejeita hash divergente.
