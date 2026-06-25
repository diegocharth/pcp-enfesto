# Retomar — estado em 2026-06-25

Nota de handoff: onde o projeto está e como continuar. (Resumo durável; o detalhe de cada frente está nos specs/planos em `docs/superpowers/`.)

## Estado atual
- **Roadmap A–F + F-1 concluído e mergeado em `main`. Frente C REFORMULADA (alocador "enfesto por enfesto").** **105 testes pytest passando.** Backend verificado AO VIVO incl. `POST /alocar_rolos` real (enfesto-por-enfesto + reaproveitamento OK).
- **Frente C REFORMULADA (2026-06-25):** o "corte separado" pós-alocação foi **substituído** por um alocador **"enfesto por enfesto"** com reaproveitamento de ponta. Regra do dono: **só camada inteira, várias pontas OK, sem emenda, margem 1x/enfesto**; o corte separado antigo (sugeria cortes parciais) era inútil sob essa regra. `engine/reaproveitamento.py` foi removido; o reaproveitamento agora vive nas `fontes` de cada enfesto. Spec/plano: `docs/superpowers/{specs,plans}/2026-06-25-alocador-enfesto-por-enfesto*`.
- **Frente G (estoque de pontas ENTRE OPs) foi construída e depois REVERTIDA a pedido do dono** (commits `025a15f`+`daf938b` revertidos): o dono NÃO quer controlar estoque de pontas para planos futuros — a ponta é reaproveitada **só dentro do mesmo plano de corte**. Não reintroduzir estoque persistente entre OPs.
- **Branch:** `main` (VERSION 2.10.1), working tree limpo, em sincronia com `origin/main`.
- **Release v2.11.0 STAGED no branch `release-2.11.0`** (VERSION bumpado + changelog, já no GitHub) — pronta para deploy com um comando após o smoke-test. Ver "Publicar/deploy".
- **A fábrica NÃO foi atualizada** (main está em VERSION 2.10.1; o release.yml só dispara com VERSION alterado em `main`).

## O que cada frente entregou
- **A** — download duplicado corrigido; resultado some ao mudar parâmetro; todos os parâmetros no Excel (single/multi-ref/alocação).
- **B** — rolos digitados em células (Tab, auto-crescer, colar lista); `%` nas tolerâncias especiais (além de absoluto).
- **C (reformulada)** — **alocador "enfesto por enfesto" com reaproveitamento de ponta**: por cor, corta o mapa mais longo primeiro e reusa a ponta que sobra como camada INTEIRA de um enfesto mais curto (só camada inteira, sem emenda, margem 1x/enfesto, greedy). Saída **por enfesto + fontes** (↻ reaproveitada), resumo por rolo, KPIs "Reaproveitado"/"Tecido economizado"; re-entrada do comprimento real do Audaces; **relatório de alocação para impressão (PDF via navegador)**. (Substituiu o "corte separado" pós-alocação.)
- **D** — pesos de eficiência eram placebo → removidos com o código morto; desempate que concentra o ajuste nas células de maior quantidade (baseline do solver preservado; coluna "Score" do Excel virou "Desvio relativo").
- **E** — abas múltiplas seguras: progresso isolado por aba (`job_id`) + aviso "na fila"; cálculo segue serializado (confiável).
- **F** — logs rotativos em `dados/logs/pcp.log`; escrita atômica de cores/params/histórico; validação de entrada + stacktrace escondido do usuário; auto-update exige `https://`.
- **F-1** — estado global do solver removido (históricos e estado de retomada via parâmetros `historicos=`/`resume_out=`); `_calc_lock` mantido por política de CPU.

## Como verificar (quando voltar)
```
cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos"
python -m pytest tests/ -q          # esperado: 105 passed (~2,5 min)
python main.py                       # abre o servidor na 5050; teste a UI no navegador
```

## Smoke-test da UI (recomendado ANTES do push — não foi testado em navegador)
1. Calcular um plano → conferir que o resultado some ao mudar um parâmetro e volta ao recalcular.
2. Exportar → conferir **1 só arquivo** no Downloads e que o Excel mostra todos os parâmetros.
3. Alocação: digitar rolos nas **células** (Tab/colar); rodar; conferir a seção **por enfesto** com **fontes** (↻ quando a ponta foi reaproveitada de outro enfesto), **sobras por rolo** e os KPIs **"Reaproveitado" / "Tecido economizado"**; preencher um **comprimento real do Audaces** e re-alocar; clicar **Imprimir relatório** (PDF).
4. Tolerância especial: testar um limite em **`%`** (ex.: PP máx `10%`) e ver no Excel.
5. Abrir **2 abas** e calcular nas duas → a 2ª mostra "na fila" e o progresso não se mistura.

## Publicar / deploy para a fábrica
A release **v2.11.0 está STAGED** no branch `release-2.11.0` (VERSION 2.10.1 → 2.11.0 + changelog; **inclui a Frente C reformulada / alocador enfesto-por-enfesto**; já no GitHub). `main` segue em 2.10.1, então **nada foi deployado** ainda. O `release.yml` só dispara o Release (que a fábrica auto-atualiza) quando um push em **`main`** altera o arquivo `VERSION`.

**Deploy — UM comando, DEPOIS de validar a UI no navegador:**
```
cd "C:\Users\CHARTH DIEGO\Desktop\CLAUDE\ENFESTOS\pcp_enfestos"
git checkout main && git merge release-2.11.0 && git push
# -> push em main com VERSION=2.11.0 dispara o release.yml -> Release v2.11.0
#    -> a fabrica auto-atualiza na proxima abertura.
```
Por que NÃO foi disparado agora: a UI não foi testada em navegador e o push de VERSION deploya direto para os operadores — você dispara quando estiver satisfeito.
(Lembrete: a v2.10.1 corrigiu o VBS→launcher; a fábrica precisa receber UMA atualização manual antes do auto-update fluir sozinho.)

## Para retomar trabalho com o Claude Code
- A memória do projeto (`project_enfestos.md`) já tem este estado — uma nova sessão recupera o contexto.
- Specs e planos de cada frente: `docs/superpowers/specs/` e `docs/superpowers/plans/`.
- Backlog opcional (não bloqueia nada): inventário persistente de pontas entre OPs (F1 da auditoria) — **DESCARTADO pelo dono** (a ponta é só para o mesmo plano de corte = Frente C; não reintroduzir); modo de solver exato via OR-Tools (avaliar); itens "depois" da auditoria E2 no spec.
