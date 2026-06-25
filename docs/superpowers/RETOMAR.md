# Retomar — estado em 2026-06-25

Nota de handoff: onde o projeto está e como continuar. (Resumo durável; o detalhe de cada frente está nos specs/planos em `docs/superpowers/`.)

## Estado atual
- **Roadmap A–F + F-1 100% concluído e mergeado em `main`.** `main` no commit mais recente; **105 testes pytest passando**.
- **Branch:** `main`, working tree limpo, sem branches de frente sobrando.
- **NÃO foi feito `git push`** — há ~41 commits locais à frente de `origin/main`. Nada se perde no desligamento (commits estão no disco).

## O que cada frente entregou
- **A** — download duplicado corrigido; resultado some ao mudar parâmetro; todos os parâmetros no Excel (single/multi-ref/alocação).
- **B** — rolos digitados em células (Tab, auto-crescer, colar lista); `%` nas tolerâncias especiais (além de absoluto).
- **C** — **corte separado a partir das pontas** (cobre o déficit reaproveitando sobras, sem comprar tecido; validado no caso real VESTIDO CORINA); relatório de sobras por rolo; re-entrada do comprimento real do Audaces; **relatório de alocação para impressão (PDF via navegador)**.
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
3. Alocação: digitar rolos nas **células** (Tab/colar); rodar; conferir **corte separado sugerido** + **sobras por rolo**; preencher um **comprimento real do Audaces** e re-alocar; clicar **Imprimir relatório** (PDF).
4. Tolerância especial: testar um limite em **`%`** (ex.: PP máx `10%`) e ver no Excel.
5. Abrir **2 abas** e calcular nas duas → a 2ª mostra "na fila" e o progresso não se mistura.

## Publicar (quando estiver satisfeito)
```
git push        # envia os commits locais para o GitHub e dispara o fluxo de auto-update da fabrica
```
(Lembrete do changelog: a v2.10.1 corrigiu o VBS→launcher; a fábrica precisa receber UMA atualização manual antes do auto-update fluir sozinho.)

## Para retomar trabalho com o Claude Code
- A memória do projeto (`project_enfestos.md`) já tem este estado — uma nova sessão recupera o contexto.
- Specs e planos de cada frente: `docs/superpowers/specs/` e `docs/superpowers/plans/`.
- Backlog opcional (não bloqueia nada): inventário **persistente de pontas entre OPs** (F1 da auditoria, adiado de propósito); modo de solver exato via OR-Tools (avaliar); itens "depois" da auditoria E2 no spec.
