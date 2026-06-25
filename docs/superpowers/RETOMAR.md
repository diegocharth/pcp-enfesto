# Retomar — estado em 2026-06-25

Nota de handoff: onde o projeto está e como continuar. (Resumo durável; o detalhe de cada frente está nos specs/planos em `docs/superpowers/`.)

## Estado atual
- **Roadmap A–F + F-1 concluído e mergeado em `main`. Frente C REFORMULADA (alocador "enfesto por enfesto").** **105 testes pytest passando.** Backend verificado AO VIVO incl. `POST /alocar_rolos` real (enfesto-por-enfesto + reaproveitamento OK).
- **Frente C REFORMULADA (2026-06-25):** o "corte separado" pós-alocação foi **substituído** por um alocador **"enfesto por enfesto"** com reaproveitamento de ponta. Regra do dono: **só camada inteira, várias pontas OK, sem emenda, margem 1x/enfesto**; o corte separado antigo (sugeria cortes parciais) era inútil sob essa regra. `engine/reaproveitamento.py` foi removido; o reaproveitamento agora vive nas `fontes` de cada enfesto. Spec/plano: `docs/superpowers/{specs,plans}/2026-06-25-alocador-enfesto-por-enfesto*`.
- **Frente G (estoque de pontas ENTRE OPs) foi construída e depois REVERTIDA a pedido do dono** (commits `025a15f`+`daf938b` revertidos): o dono NÃO quer controlar estoque de pontas para planos futuros — a ponta é reaproveitada **só dentro do mesmo plano de corte**. Não reintroduzir estoque persistente entre OPs.
- **Branch:** `main` (VERSION **2.11.0**, commit `d189d9a`), working tree limpo, em sincronia com `origin/main`. A branch de staging `release-2.11.0` já foi mergeada (fast-forward) e removida.
- **DEPLOYADO em 2026-06-25 (a pedido do dono):** o push da `main` com VERSION 2.11.0 disparou o `release.yml` → **Release v2.11.0 publicada no GitHub** (tag `v2.11.0` em `d189d9a`). A fábrica auto-atualiza na próxima abertura via `launcher.py`/`updater.py`.
- **Ressalva do auto-update:** o fluxo automático só funciona se a máquina da fábrica já estiver em **≥ 2.10.1** (a v2.10.1 corrigiu o VBS→launcher). Se ainda estiver numa versão anterior, precisa de **UMA** atualização manual (recopiar a pasta / re-rodar INSTALAR / editar a linha do VBS); daí em diante 2.11.0 e futuras fluem sozinhas.

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

## Smoke-test da UI (v2.11.0 já deployada — valide no navegador; a UI foi revisada por código, não testada em navegador daqui)
1. Calcular um plano → conferir que o resultado some ao mudar um parâmetro e volta ao recalcular.
2. Exportar → conferir **1 só arquivo** no Downloads e que o Excel mostra todos os parâmetros.
3. Alocação: digitar rolos nas **células** (Tab/colar); rodar; conferir a seção **por enfesto** com **fontes** (↻ quando a ponta foi reaproveitada de outro enfesto), **sobras por rolo** e os KPIs **"Reaproveitado" / "Tecido economizado"**; preencher um **comprimento real do Audaces** e re-alocar; clicar **Imprimir relatório** (PDF).
4. Tolerância especial: testar um limite em **`%`** (ex.: PP máx `10%`) e ver no Excel.
5. Abrir **2 abas** e calcular nas duas → a 2ª mostra "na fila" e o progresso não se mistura.

## Publicar / deploy para a fábrica — JÁ FEITO (v2.11.0, 2026-06-25)
A `main` foi empurrada com VERSION 2.11.0 (commit `d189d9a`), disparando o `release.yml` → **Release v2.11.0 publicada** no GitHub (tag `v2.11.0`). A fábrica auto-atualiza na próxima abertura (`launcher.py`→`updater.py` puxam a Release mais nova). **Ressalva:** o auto-update só flui se a máquina já estiver em **≥ 2.10.1** (a v2.10.1 corrigiu o VBS→launcher); senão, UMA atualização manual primeiro (recopiar a pasta / re-rodar INSTALAR / editar a linha do VBS).

**Para a PRÓXIMA release:** bumpar `VERSION` (+ changelog em main.py/CLAUDE.md) e `git push` na `main` — isso por si só dispara o `release.yml` (não precisa de branch de staging). Se quiser revisar antes de publicar, trabalhe num branch e só altere o `VERSION` ao mergear na `main`.

## Para retomar trabalho com o Claude Code
- A memória do projeto (`project_enfestos.md`) já tem este estado — uma nova sessão recupera o contexto.
- Specs e planos de cada frente: `docs/superpowers/specs/` e `docs/superpowers/plans/`.
- Backlog opcional (não bloqueia nada): inventário persistente de pontas entre OPs (F1 da auditoria) — **DESCARTADO pelo dono** (a ponta é só para o mesmo plano de corte = Frente C; não reintroduzir); modo de solver exato via OR-Tools (avaliar); itens "depois" da auditoria E2 no spec.
