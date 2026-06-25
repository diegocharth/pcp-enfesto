# Alocador "enfesto por enfesto" com reaproveitamento de ponta — Design

> Data: 2026-06-25 · Autor: Diego (dono) + Claude Code · Status: aprovado nas seções, aguardando revisão do spec escrito

## 1. Contexto e fronteira

A **alocação de tecido** (`engine/alocador_rolos.py`) é um passo **a jusante e independente** do plano de corte. Ela recebe o plano **pronto** (mapas × camadas por cor, produzido pelo solver) e decide **como cortar aquilo nos rolos disponíveis**.

**Invariantes (não negociáveis):**
- O **solver / plano de corte é intocável**. A alocação **nunca** altera o plano, os mapas ou o número de enfestos. O objetivo do solver (minimizar enfestos) é a premissa; a alocação só serve o plano dado.
- O reaproveitamento de ponta **não cria enfesto novo**. Os enfestos vêm do plano; a única mudança é permitir que **uma camada de um enfesto seja cortada de uma ponta que sobrou de outro enfesto** (da mesma cor, mesmo plano), desde que a ponta cubra a **camada inteira**.
- **Por cor**: cor diferente = tecido diferente; ponta **nunca** cruza de uma cor para outra.
- **Só dentro do mesmo plano (OP)**: não há estoque persistente de pontas entre OPs (decisão do dono — ver `2026-06-24-...-design.md` seção 8).

**Problema que resolve:** o modelo atual junta todos os rolos da cor e empilha todos os mapas juntos (empacotamento global). Isso não corresponde ao processo real da fábrica, que **corta um enfesto por vez** e reaproveita a ponta que sobra de um enfesto como camada inteira de **outro** enfesto (tipicamente de um mapa mais curto). O modelo atual nunca deixa uma ponta ≥ uma camada inteira (empacota tudo), então o reaproveitamento "só camada inteira" nunca dispara nele.

## 2. Regras do reaproveitamento (decisões do dono)

1. **Só camada inteira.** Uma ponta só é usada num enfesto se cobrir a camada inteira daquele mapa (`ponta >= comp_camada`). Nada de submapa parcial (metade / 1-de-cada). Ponta menor que a camada do mapa simplesmente não é usada por aquele enfesto.
2. **Sem emenda.** Cada camada sai inteira de **uma única** ponta/rolo. Nunca soma dois pedaços numa mesma camada.
3. **Várias pontas OK.** Um enfesto pode ser coberto por **várias** pontas/rolos, desde que **cada camada** saia inteira de uma única fonte.
4. **Margem de faca 1× por enfesto.** O enfesto é uma pilha única, cortada de uma vez; a margem (cabeça + cauda) é paga **uma vez** para o enfesto inteiro, não importa de quantas fontes vieram as camadas.

## 3. Algoritmo (por cor)

Entrada por cor: a demanda `{mapa_id: n_camadas}`, o `comp_camada_por_id[mid]` (comprimento da camada de cada mapa — já honrado hoje, inclusive explícito por mapa em enfestos multi-ref combinados), os rolos da cor (comprimentos nominais), e os parâmetros (`margem`, `folga_incerteza`, `ponta_minima_util`).

1. **Comprimento seguro dos rolos:** `comp_seguro(nominal) = nominal * (1 - folga_incerteza_pct) - folga_incerteza_m` (igual ao atual, `_comp_seguro`).
2. **Ordena os enfestos** (mapas com demanda > 0) por `comp_camada` **decrescente** (mapa mais longo primeiro). Empate: maior demanda primeiro (determinístico).
3. **Pool de pedaços disponíveis** = lista de `{comprimento_m, origem}` começando com os rolos novos (cada rolo é um pedaço com `comprimento_m = comp_seguro`, `origem = {tipo:"rolo", rolo_indice:i}`). À medida que enfestos são cortados, as **pontas geradas (≥ ponta_minima_util)** entram no pool com `origem = {tipo:"ponta", rolo_indice:i (rolo raiz), enfesto_origem: mid}`.
4. **Para cada enfesto** (mapa `mid`, camada `cc`, precisa de `K` camadas):
   - Ordena o pool por `comprimento_m` **decrescente**, mas **prioriza pontas sobre rolos novos** no desempate (consumir sobra antes de abrir rolo novo). Critério final: `(tipo=='ponta' primeiro, depois comprimento desc)`.
   - **Margem 1×:** a **fonte primária** = o **primeiro pedaço do pool, na ordem acima, com `L >= cc + M`** (reserva a margem `M` que inicia a pilha). Capacidade de camadas da primária = `floor((L - M) / cc)`; das demais fontes = `floor(L / cc)`. Se **nenhum** pedaço tiver `L >= cc + M`, o enfesto não fecha nenhuma camada das fontes (tudo vira déficit). (Modelagem: a margem cabeça+cauda é cobrada uma vez, na fonte que inicia a pilha.)
   - Percorre o pool tirando camadas inteiras até cobrir `K` ou esgotar o pool. De cada pedaço de comprimento `L`: `k = min(camadas_que_faltam, capacidade(L))` camadas; consumo `k*cc` (+ `M` se for a primária); **ponta gerada** = `L - k*cc - (M se primária)`. Registra a fonte `{tipo, origem, n_camadas:k, reaproveitada: tipo=='ponta'}`.
   - **Atualiza o pool:** remove os pedaços consumidos; adiciona as pontas geradas que forem `>= ponta_minima_util` (classe estoque) — as menores são refugo e saem do pool, mas ficam registradas na sobra do rolo raiz.
   - **Déficit do enfesto** = `K - camadas_cobertas` → comprar `deficit * cc` (sem margem na compra; é estimativa de tecido).
5. **Após todos os enfestos da cor:** o pool tem as pontas finais. Cada rolo raiz é resumido (nominal, seguro, total usado somando tudo que ele alimentou — direto e via ponta —, ponta final e classe). Pontas finais `>= ponta_minima_util` = estoque; senão refugo.

**Por que mapa-longo-primeiro:** ponta de mapa longo (grande) pode virar camada inteira de mapa curto; o contrário nunca acontece. Cortar os longos primeiro deixa as pontas grandes disponíveis quando os curtos forem processados → maximiza o reaproveitamento sem busca exaustiva.

### Exemplo (cor AZUL, 2 enfestos, margem 0,10 m)

Plano: E1 = mapa longo (camada 7,8 m, precisa 4 camadas); E2 = mapa curto (camada 4,0 m, precisa 3). Rolos AZUL: 20 m e 12 m (assuma seguro = nominal para o exemplo).

- **E1 (7,8 m), ordem 1.** Pool = [rolo 20, rolo 12].
  - Primária rolo 20: `floor((20 - 0,10)/7,8) = 2` camadas; consumo `2*7,8 + 0,10 = 15,7`; ponta = `20 - 15,7 = 4,3 m`.
  - Rolo 12 (não primária): `floor(12/7,8) = 1` camada; consumo `7,8`; ponta = `4,2 m`.
  - Cobertas 3 de 4 → **déficit 1** (comprar 7,8 m). Pontas geradas 4,3 e 4,2 (< 7,8, não servem ao E1) entram no pool.
- **E2 (4,0 m), ordem 2.** Pool = [ponta 4,3 (do rolo 20/E1), ponta 4,2 (do rolo 12/E1)].
  - Primária ponta 4,3: `floor((4,3 - 0,10)/4,0) = 1` camada; ponta = `4,3 - 4,1 = 0,2 m` (refugo).
  - Ponta 4,2: `floor(4,2/4,0) = 1` camada; ponta = `0,2 m` (refugo).
  - Cobertas 2 de 3 → **déficit 1** (comprar 4,0 m). **2 camadas reaproveitadas** (tecido economizado ~8 m que não foi comprado/aberto).

## 4. Formato da saída (JSON)

`alocar_rolos(plano, rolos, config)` mantém a assinatura; muda o conteúdo de `por_cor[cor]`:

```jsonc
por_cor[cor] = {
  "enfestos": [                      // na ordem de corte (mapa longo -> curto)
    {
      "mapa_id": 0,
      "comp_camada_m": 7.8,
      "camadas_necessarias": 4,
      "camadas_cobertas": 3,
      "camadas_em_deficit": 1,
      "margem_m": 0.10,
      "tecido_usado_m": 23.5,        // soma das camadas cobertas*cc + margem
      "tecido_a_comprar_m": 7.8,     // deficit * cc
      "fontes": [
        {"tipo": "rolo", "rolo_indice": 0, "n_camadas": 2, "comp_camada_m": 7.8,
         "comp_usado_m": 15.7, "primaria": true,  "reaproveitada": false},
        {"tipo": "rolo", "rolo_indice": 1, "n_camadas": 1, "comp_camada_m": 7.8,
         "comp_usado_m": 7.8,  "primaria": false, "reaproveitada": false}
      ]
    },
    {
      "mapa_id": 1, "comp_camada_m": 4.0, "camadas_necessarias": 3,
      "camadas_cobertas": 2, "camadas_em_deficit": 1, "margem_m": 0.10,
      "tecido_usado_m": 8.1, "tecido_a_comprar_m": 4.0,
      "fontes": [
        {"tipo": "ponta", "rolo_indice": 0, "enfesto_origem": 0, "n_camadas": 1,
         "comp_camada_m": 4.0, "comp_usado_m": 4.1, "primaria": true,  "reaproveitada": true},
        {"tipo": "ponta", "rolo_indice": 1, "enfesto_origem": 0, "n_camadas": 1,
         "comp_camada_m": 4.0, "comp_usado_m": 4.0, "primaria": false, "reaproveitada": true}
      ]
    }
  ],
  "rolos": [                          // resumo por rolo (alimenta "Sobras por rolo")
    {"rolo_indice": 1, "nominal_m": 20.0, "seguro_m": 20.0, "usado_m": 19.8,
     "ponta_m": 0.2, "ponta_classe": "refugo"},
    {"rolo_indice": 2, "nominal_m": 12.0, "seguro_m": 12.0, "usado_m": 11.8,
     "ponta_m": 0.2, "ponta_classe": "refugo"}
  ],
  "camadas_alocadas":  {"0": 3, "1": 2},
  "camadas_em_deficit": {"0": 1, "1": 1},
  "tecido_usado_m": 31.6,
  "tecido_a_comprar_m": 11.8,
  "ponta_estoque_total_m": 0.0,
  "refugo_real_m": 0.4,
  "refugo_percentual": 1.25,
  "reaproveitamento": {"camadas_reaproveitadas": 2, "tecido_economizado_m": 8.0}
}
```

`resumo_geral` consolida entre cores: `sobras_consolidado` (mantido), totais de tecido usado/comprado/economizado, `camadas_reaproveitadas_total`. **Saem** do retorno: `sugestoes_corte_separado`, `sugestoes_corte_total`. Mantidos: `params`, `alertas`.

## 5. Integração e remoções

- **Assinatura estável:** `alocar_rolos(plano, rolos, config)` — `main.py`, multi-ref e câmbio não mudam de chamada; só consomem o novo formato.
- **Removidos:** `engine/reaproveitamento.py` (e `sugerir_corte_separado`/`_gerar_candidatos`), `tests/test_reaproveitamento.py`, o import e a chamada em `alocador_rolos.py`, as chaves `sugestoes_corte_separado`/`sugestoes_corte_total`, o bloco "Corte separado sugerido" da UI (`_htmlCorteSeparado`) e do Excel. O reaproveitamento agora vive nas `fontes` de cada enfesto.
- **Excel (`exportar/export_xlsx.py::exportar_alocacao` / `_aba_cor_alocacao`):** por cor, uma seção **por enfesto** (mapa, camadas, fontes com marca ↻ quando reaproveitada, déficit) + a tabela **"Sobras por rolo"** + resumo da cor (usado / reaproveitado / a comprar / refugo). Remove a seção de corte separado.
- **UI (`interface.html::_renderResultadoAlocacao` + relatório de impressão):** idem — por enfesto, fontes com ↻, sobras por rolo, déficit, resumo. Edições **100% ASCII** (regra de encoding do projeto; usar Python/replace por bytes para blocos grandes).
- **Multi-ref:** o `main.py` agrega por cor entre grupos; o `comp_camada_por_id` explícito por mapa (enfestos combinados) continua honrado.

## 6. Casos de borda

- **Sem rolos / cor sem rolos:** todos os enfestos em déficit; `enfestos[].fontes = []`; `rolos = []`; reaproveitamento zero.
- **Um único mapa na cor:** nunca há mapa mais curto pra receber a ponta → reaproveitamento zero (as pontas viram estoque/refugo). Comportamento correto.
- **Todos os mapas com a mesma camada:** ponta < camada sempre (igual ao caso de um mapa) → reaproveitamento zero. Correto.
- **Ponta exatamente = camada (sem margem):** serve como **não-primária** (1 camada, ponta 0). Como primária precisa de `cc + margem`.
- **Ponta entre `cc` e `cc + margem`:** serve como não-primária; como primária só se outra fonte já pagou a margem. (Subtileza aceitável; documentada.)
- **Folga de incerteza:** aplicada no `comp_seguro` dos rolos novos; pontas já são comprimento real medido (sem folga adicional).
- **Plano multi-ref combinado:** `comp_camada_por_id` explícito por mapa é usado como `cc`.

## 7. Testes

Unitários do novo alocador por cor (em `tests/test_alocador_rolos.py`, reaproveitando os fixtures existentes):
- **Ordem:** enfestos processados do mapa mais longo pro mais curto.
- **Reaproveitamento real:** o exemplo AZUL — ponta de mapa longo vira camada inteira de mapa curto; `reaproveitamento.camadas_reaproveitadas == 2`.
- **Só camada inteira:** ponta `< cc` do mapa não é usada por aquele enfesto (vira sobra), não corte parcial.
- **Sem emenda:** cada `fonte.n_camadas` sai de um único pedaço.
- **Margem 1×/enfesto:** o `tecido_usado_m` do enfesto cobra a margem uma única vez (não por fonte).
- **Déficit:** falta de tecido → `camadas_em_deficit` e `tecido_a_comprar_m` corretos; reaproveitamento não infla cobertura além do real.
- **Carrega ponta por ≥ 2 enfestos:** ponta gerada no E1 usada no E2 e o resto (se houver) no E3.
- **Nunca cruza cor:** ponta de uma cor não aparece nas fontes de outra.
- **Estoque vs refugo:** classificação por `ponta_minima_util`.
- Mantidos: parsing de rolo, `comp_seguro`/folga, `params`, camada multi-ref combinada, `sobras_por_rolo`/`sobras_consolidado`.
- **Smoke-test ao vivo** do `POST /alocar_rolos` no servidor real após a implementação.
- Suíte completa verde (baseline 105 − 5 testes do reaproveitamento removido + novos testes do alocador).

## 8. Não-objetivos

- Não tocar no solver / plano / número de enfestos.
- Não reintroduzir estoque de pontas entre OPs.
- Não reaproveitar entre cores.
- Não cortar submapa parcial / emenda.
- Não buscar o ótimo exato (greedy mapa-longo-primeiro é suficiente e determinístico).

## 9. Versão / release

Faz parte da release **v2.11.0** (Frente C reformulada). A `release-2.11.0` será re-sincronizada a partir da `main` após a implementação. Sem deploy até o smoke-test no navegador.
