# PCP Enfestos — Contexto para Claude Code
> Leia este arquivo inteiro antes de qualquer coisa.

---

## O Projeto

Sistema local de otimização de plano de corte para confecção da **Charth** (moda feminina premium). Dono: **Diego Faria**.

Roda como servidor Python local na porta 5050. Interface HTML no navegador. Sem cloud, sem banco de dados. Operadores de fábrica são os usuários finais — o sistema precisa ser robusto e à prova de erro de operador.

**Stack:** Python 3.10+ · HTML/CSS/JS vanilla · openpyxl · pdfplumber · Windows 10/11

**Versão atual:** 2.15.0 (publicada em 24/11/2026: motor exato do single-ref, opções N / N+1 / mapas cheios, alocador de menor compra e as correções da Etapa 6). Push na `main` com `VERSION` novo = deploy na fábrica; subir também `VERSION` no `main.py` (há teste que confere).

---

## Terminologia do Domínio

| Termo | Significado |
|---|---|
| **Enfesto / Sub-enfesto** | Uma passagem na mesa de corte. Cada sub-enfesto tem 1 mapa + margem de faca. |
| **Mapa/Encaixe** | Composição de tamanhos: ex. `PP=2,P=3,M=1` = 6 peças. Executado no Audaces. |
| **Folhas / Camadas** | Camadas de tecido sobrepostas. Cada cor tem folhas independentes por enfesto. |
| **Grade** | Qtd de peças necessárias por cor×tamanho. Ex: BLUES/PP=23, BLUES/P=34... |
| **Desvio** | Diferença entre cortado e grade. Objetivo principal: **minimizar**. |
| **Consumo/peça** | Metros de tecido por peça (fornecido pelo Audaces, constante por coleção). |
| **Margem de faca** | Folga nas extremidades de cada sub-enfesto (cabeça + cauda). Por sub-enfesto, não por camada. |
| **Comp_seguro** | `nominal × (1 - folga_incerteza_pct)` — comprimento seguro de um rolo para alocar. |
| **Emenda (PROIBIDO)** | Camada que cruza dois rolos — inutiliza a camada. O alocador nunca permite emenda. |
| **Ponta de rolo** | Sobra FÍSICA ao final de um rolo usado: `nominal − usado` (a folga de incerteza limita o planejamento, mas não é descontada da sobra). Se ≥ `ponta_minima_util_m`: estoque. Se menor: refugo. `rolos[]` do alocador lista só os rolos usados; os demais entram em `rolos_nao_utilizados`. |

---

## Estrutura de Arquivos

```
pcp_enfestos/
├── CLAUDE.md                  ← VOCÊ ESTÁ AQUI
├── LEIA-ME.md                 ← guia para o usuário final
├── INSTALAR.bat               ← instala Python + bibliotecas + cria atalho
├── PCP_Enfestos.vbs           ← INICIALIZADOR — duplo clique do usuário
├── iniciar_visivel.bat        ← debug: abre CMD visível para ver erros
├── main.py                    ← servidor HTTP porta 5050
├── launcher.py                ← aplica restauracao/update pendente, inicia main.py
├── updater.py                 ← motor de auto-update via GitHub Releases
├── versoes.py                 ← snapshots permanentes de versao + restauracao (v2.13)
├── VERSION                    ← versao atual (ex: "2.13.0")
├── interface.html             ← UI completa no navegador (~1800 linhas)
├── config.json                ← parâmetros padrão persistentes
├── engine/
│   ├── solver_exato.py        ← motor EXATO do single-ref (padrão no ramo solver-exato)
│   ├── exato_folhas.py        ← folhas exatas por cor + repartição das 70 folhas entre cores + montagem/MOTOR_ID
│   ├── exato_fatias.py        ← busca fatiada pelo pool: rodadas curtas, retomada, orçamento de prova
│   ├── solver.py              ← motor clássico, mantido como RESERVA — NÃO MODIFICAR
│   ├── paralelo.py            ← pool de processos dos cálculos (tipos: single, exato, multiref)
│   ├── multiref_pool.py / multiref_local.py ← apoio do solver multi-ref (v2.12)
│   ├── solver_multiref.py     ← solver multi-referência (v2.9: fix crash; v2.10: n_mapas_max p/ branch-and-bound)
│   ├── tolerancia.py          ← regras de desvio permitido por tamanho
│   ├── mapas.py               ← gerador de composições de encaixe
│   ├── cache_planos.py        ← cache persistente de resultados + tempos aprendidos (ETA)
│   ├── alocador_rolos.py      ← alocacao por mochila/rolo; v2.13: metadados + Considerar Lote
│   ├── alocador_exato.py      ← Etapa 5: busca exata da cor (poucos mapas) + busca local por pares/trios de rolos
│   ├── planos.py              ← plano de corte portatil .plano.json (v2.13)
│   └── import_rolos/
│       ├── base.py            ← classe abstrata FonteRolos (contrato inclui largura_m)
│       ├── fonte_vexta_pdf.py ← parser PDF "Reserva de Tecidos" (artigo/cor por POSICAO)
│       ├── fonte_vexta_estoque_pdf.py ← parser PDF "Estoque Total/ROLOS" com LARGURA (v2.13)
│       ├── fonte_sisplan.py   ← stub para ERP Sisplan (não implementado)
│       ├── mapa_cores.py      ← mapeamento cor-fornecedor → cor-comercial
│       └── registry.py        ← detecta o formato do PDF pelo CONTEUDO (v2.13)
├── exportar/
│   ├── export_xlsx.py         ← gera planilha Excel (resultado solver + alocação)
│   ├── upload_parser.py       ← lê .xlsx/.csv de ordens de produção
│   └── upload_parser_img.py   ← OCR via Claude API (foto da ordem)
├── dados/
│   ├── cores_salvas.json      ← cadastro persistente de cores
│   ├── parametros_salvos.json ← últimos parâmetros da UI
│   ├── mapa_cores.json        ← mapeamento cor-fornecedor → cor-comercial (ERP)
│   └── resultados/            ← planilhas Excel geradas
└── tests/
    ├── test_alocador_rolos.py ← 17 testes do motor FFD
    ├── test_fonte_vexta_pdf.py← 9 testes do parser PDF
    ├── test_mapa_cores.py     ← 13 testes do mapeamento de cores
    └── test_updater.py        ← 12 testes do auto-updater
```

---

## Como Iniciar (usuário final)

1. **Primeira vez:** duplo clique em `INSTALAR.bat` → cria atalho na Área de Trabalho
2. **Uso diário:** duplo clique no atalho **"Enfestos Charth"** na Área de Trabalho
3. **Se travar / debug:** duplo clique em `iniciar_visivel.bat` — mostra o CMD com erros

O VBS (`PCP_Enfestos.vbs`) detecta se o servidor já está rodando e apenas reabre o browser nesse caso.

---

## Como Testar (desenvolvedor)

```bash
# Rodar o servidor
cd pcp_enfestos
python main.py

# Testar rotas
curl http://localhost:5050/versao
# → {"versao": "2.8.0"}

# Rodar todos os testes (~200, cerca de 4 min)
python -m pytest tests/ -q

# Bancada de comparacao dos motores single-ref (fora do zip da fabrica).
# Compara motor classico x exato caso a caso, valida as restricoes duras e
# confere contra o gabarito. Rodar SEMPRE antes de afirmar que algo melhorou.
python tools/bench/corpus.py --importar-cache   # monta dados/ordens/bench_corpus.json (OPs reais, fora do git)
python tools/bench/rodar.py                     # sai com erro se o exato piorar algum caso
python tools/bench/opcoes.py                    # opcoes de cada caso pelo caminho de producao (pool)
python tools/bench/gabarito_cpsat.py            # gabarito OR-Tools: so na maquina de dev, nunca na fabrica

# CI no GitHub: .github/workflows/testes.yml roda a suite (Linux, Python 3.12)
# em todo envio de ramo que nao seja a main; release.yml roda a mesma suite
# ANTES de criar a release (teste falhando = nada vai para a fabrica).

# Bancada do alocador de rolos (alocacoes reais exportadas pela tela)
python tools/bench/alocacao.py --extrair        # monta dados/ordens/bench_alocacao.json (fora do git)
python tools/bench/alocacao.py                  # rolo a rolo x atual (compra, rolos, prova)
python tools/bench/alocacao.py --cpsat 120      # + gabarito CP-SAT por cor (so dev)

# Testar solver diretamente
python -c "
import sys, json
sys.path.insert(0,'.')
from engine.solver import resolver
from engine.tolerancia import calcular_limites_grade
cfg = json.load(open('config.json'))
cfg.update({'consumo_peca_m':1.0645,'mesa_comprimento_m':10.0,'limite_folhas_padrao':70})
grade = {'BLUES':{'PP':41,'P':45,'M':25,'G':10},'JAZZ':{'PP':44,'P':55,'M':30,'G':11}}
tams = ['PP','P','M','G']
limites = calcular_limites_grade(grade, tams, cfg, {})
sols = resolver(grade, tams, limites, cfg, print, timeout_s=30)
for s in sols: print(s['resumo']['n_mapas'],'mapas | dev=',s['resumo']['desvio_total'])
"
```

---

## Regra de Encoding — CRÍTICA

O `interface.html` já foi corrompido antes por `Set-Content -Encoding utf8` do PowerShell (ç, ·, ─ viraram lixo tipo `Ã§`). Os caracteres garbled pré-existentes são inofensivos (o browser renderiza normalmente). **Ao editar:**
- Usar **Python** para modificar o arquivo (não PowerShell `Set-Content`)
- Inserir apenas conteúdo **100% ASCII** nos novos blocos
- Para blocos grandes, usar script Python que lê como bytes, faz replace, escreve como UTF-8

---

## Algoritmo do Solver

**Dois motores single-ref** (`config.json → "motor_single"`): `exato` (padrão no código do ramo `solver-exato`) e `classico` (`engine/solver.py`, intocado, reserva). Se o exato falhar, o servidor cai sozinho no clássico. O motor entra na assinatura do cache.

**Tolerância é restrição dura.** Dentro dela, a regra decidida pelo Diego em 10/11/2026 é:
1. **Menos enfestos primeiro** — e, no mesmo número de enfestos, menor desvio; com desvio igual, **mapas mais cheios**; depois menor desvio relativo.
2. **Mostrar sempre a alternativa de 1 enfesto a mais** quando ela reduz o desvio — o operador decide entre menos enfestos e menor desvio.
3. **Mapas mais cheios com desvio maior nunca são automáticos**: aparecem como opção separada para o operador aprovar.

(O texto antigo deste arquivo dizia "menor desvio = premissa absoluta" e contradizia o código; a regra acima é a que vale.)

**Opções devolvidas pelo motor exato** (`resumo["papel"]`, nesta ordem): `minimo_enfestos` (sempre) · `menor_desvio` (1 enfesto a mais, só se o desvio cair) · `mapas_cheios` (mesmo nº de enfestos, o de menor desvio entre os mais cheios) · `alternativa` (completa até `num_opcoes_saida`). Com `num_opcoes_saida = 1` volta só a primeira. Cada opção traz `rotulo`, `comparacao` (em relação à Opção 1) e `prova`: `provado` (busca completa em todos os mapas) ou `nao_provado` (melhor encontrado no tempo/pool).

**O que o motor exato faz de diferente:** folhas por cor exatas (o clássico perdia soluções com tolerância assimétrica, ex.: "G não cresce"); limite de folhas repartido entre as cores de forma conjunta; todos os mapas, com repetição, até 3 enfestos (4+ usa o pool do clássico). Pelo servidor, a coordenação roda na thread do pedido e cada varredura é fatiada entre os processos de `engine/paralelo.py` (um cálculo usa vários núcleos; o resultado é idêntico ao serial quando a varredura termina). Quando já existe solução, a varredura completa pode usar até metade do tempo restante para provar o ótimo (`_orcamento_prova`). Cada tarefa no pool dura no máximo `RODADA_S` (3 s) e a fatia retoma de onde parou; com vários cálculos exatos ao mesmo tempo os processos são divididos entre eles — sem isso um cálculo pesado segurava o pool e um cálculo simples voltava "sem solução". As fatias recebem a lista de mapas do coordenador (a ordem não pode depender do processo).

**Cache do motor exato:** o timeout entra na assinatura (o resultado depende do tempo: prova e opção de +1 enfesto), e resultado cortado pelo prazo total (`cortado`) não é cacheado nem ensina tempo. `/calcular` devolve `status` (`ok`/`tempo`/`nao_achou`) e `cortado`. Sem OR-Tools: decisão do dono é Python puro na fábrica; OR-Tools só como gabarito em `tools/bench/`.

**Alocação de rolos** usa a opção SELECIONADA na tela (single-ref), não mais sempre a Opção 1.

**Alocação de rolos — Etapa 5 (23/11/2026):** o alocador rolo a rolo (uma mochila por rolo, duas ordens) continua rodando primeiro e é a reserva. Depois, por cor, `engine/alocador_exato.py`: com até `EXATA_MAX_MAPAS` (8) mapas, **busca completa** com todos os rolos juntos (prova a menor compra e, sem déficit, o menor número de rolos); com mais mapas, ou se a completa não fechar, **busca local** que re-otimiza de forma exata pares e depois trios de rolos (camadas deles + o déficit). Só troca o resultado por um estritamente melhor pela mesma chave (compra, rolos, refugo, fontes) — nunca piora. Mesmo modelo físico: mm inteiros, camada inteira, sem emenda, margem de faca 1x por mapa, **paga por qualquer rolo que sirva o mapa** (não precisa ser o primeiro; há caso real em que só assim cabe). Limites (em `engine/alocador_exato.py`) por **passos de busca** (mesma entrada → mesmo resultado): `EXATA_PASSOS` (400 mil, busca completa) e `LOCAL_PASSOS` (500 mil, busca local) por cor; o relógio é só segurança — `EXATA_PRAZO_COR_S` (4 s) por etapa e `EXATA_PRAZO_TOTAL_S` (15 s) por alocação, repartido entre as cores (o que uma cor não usa passa às seguintes; os lotes de uma cor não tiram o prazo das outras). Até `EXATA_MAX_ROLOS` (200) rolos por cor na busca completa. Cada cor devolve `busca_exata`: `provado` / `provado_nos_lotes` (modo lote: ótimo só entre os rolos dos lotes escolhidos) / `nao_provado` / `nao_tentada`; `config.json → "alocacao_exata": false` desliga (volta ao rolo a rolo). **Medido (bancada + CP-SAT):** casos pequenos reais — o rolo a rolo comprava 3,5-5,25 m a mais em 3 de 8 cores, inclusive mandando comprar quando os rolos bastavam; agora igual ao gabarito, provado, em milissegundos. Plano multi-ref de 02/07 (17 mapas por cor): busca local -22,0 m nas 10 combinações cor×folga (CP-SAT: -42,8 m); a alocação inteira de 5 cores passa de 0,5 s para ~7 s. Observação: o próprio rolo a rolo (`_resolver_rolo_dp`) fica muito lento com camadas curtas (1-3 m), rolos longos (100+ m) e muitos mapas — já era assim antes da Etapa 5.

**Etapa 6 — confiabilidade (23/11/2026):** tela: plano desatualizado (grade/parâmetros mudaram depois do cálculo, `window._planoObsoleto`) não vai para a alocação — pede para recalcular; "Exportar Planilha" só exporta agrupamento multi-ref se o resultado atual for multi-ref (`_multiGrupoValidos` é limpo em Calcular/Limpar); linhas do PDF de rolos não entendidas viram aviso. Publicação: `release.yml` só publica com testes verdes; biblioteca faltando (numpy/pdfplumber/openpyxl) aparece no log e na tela (`/config_pub → faltando`, `_avisoBibliotecas`). Robustez: download com qualquer nome (`_content_disposition`, `filename*` UTF-8); mochila de um rolo com teto `DP_LIMITE_PASSOS` (1 milhão; acima disso `_encher_rolo_guloso`); `_reset_pool` só descarta pool quebrado; "Continuar" volta ao nível de 2-3 enfestos varrido em parte (`nivel_parcial`, prazo inteiro na retomada, sem laço). Textos: emoji corrompido corrigido; bloco vazio de referência sem peças no enfesto combinado some; comparação de opções recomenda a Opção 1 quando ela ganha nas duas medidas e não recomenda em empate; "Padrão + 1 alternativa extra" entrega 1 alternativa além dos papéis (`MOTOR_ID` "exato-5").

**Multi-ref — avisos honestos (Etapa 3):** `resolver_multiref` devolve em `resume_out["status"]` o motivo da parada: `impossivel` (prova sem busca: capacidade da mesa/folhas), `nao_achou` (a busca terminou sozinha, por estagnação), `tempo` (o orçamento acabou: INCONCLUSIVO) ou `ok`. `convergiu` só é verdadeiro se a busca não foi limitada pelo relógio — inclusive a descida para menos enfestos. Só resultado convergido é cacheado e ensina tempo. A tela mostra cada caso com etiqueta própria (`_avisoGrupoSemSolucao`) e, no fim, avisa quantos cálculos foram inconclusivos. Cálculo individual dentro do multi-ref usa sempre o timeout da tela (o motor exato para sozinho quando termina).

**Multi-ref — Etapa 4 (23/11/2026):** folhas de cada combinação calculadas de forma exata (`engine/multiref_exato.py`, reaproveita `_pontos_cor`/`_conjunto` do motor exato) e polimento do desvio na busca local (`multiref_local.py`). Tela: agrupamentos empatados em enfestos desempatam pelo menor desvio (coluna "Desvio" na tabela); teto de enfestos de cada grupo vem da melhor partição interna já calculada (`_tetoGrupo`: trios usam os pares); a alocação usa a opção aberta em cada grupo (`window._opGrupo`, `_solucaoDoGrupo`). Bancada: `tools/bench/multiref.py` (pares, validador `validar_multiref`) e `gabarito_cpsat.py --multiref`. **Limite medido:** a busca local do multi-ref não alcança o ótimo em pares difíceis (TERESA+LILIAN: 55 contra 42; KIARA+TERESA: não acha a combinação de 4 enfestos que existe) e mais tempo não ajuda — melhorar isso exige método de outra classe (OR-Tools resolve, mas o dono decidiu não levar à fábrica).

**Revisões de motor:** `MOTOR_ID` do motor exato (em `engine/exato_folhas.py`) e `MOTOR_ID` do multi-ref (em `engine/solver_multiref.py`) entram na assinatura do cache e nas chaves de tempo aprendido (`indiv:Nc:<motor>`, `grupo:Rr:Cc:<motor>`; o clássico fica sem sufixo). **Ao mudar o resultado de um motor, mude o `MOTOR_ID` dele** — senão a fábrica continua recebendo planos antigos do cache.

**Ranqueamento do motor clássico (reserva):** estritamente lexicográfico — `menos enfestos -> menor desvio -> mais peças/mapa -> menor desvio relativo`. NÃO existem pesos de eficiência configuráveis (os antigos `peso_enc`/`peso_op`/`peso_eficiencia_*` eram placebo e foram removidos — o solver nunca os lia).

**Regra crítica — Mapas Estratégicos:**
- `hi = 0` → cria mapa puro dedicado (ex: G=1 somente) — **obrigatório**
- `hi >= 1` → solver inclui tamanho normalmente — NÃO criar mapa estratégico

---

## Rotas HTTP

| Método | Rota | Descrição |
|---|---|---|
| GET | `/versao` | `{"versao":"2.8.0"}` |
| GET | `/cores` | Cadastro de cores salvas |
| GET | `/params` | Últimos parâmetros salvos da UI |
| GET | `/config_pub` | `{"tem_api_key":bool}` |
| GET | `/progresso` | Mensagens de progresso do cálculo atual |
| GET | `/encerrar` | Encerra o servidor |
| GET | `/mapa_cores` | Mapeamento cor-fornecedor → cor-comercial |
| GET | `/checar_update` | Consulta GitHub Releases por nova versão |
| GET | `/aprendizado` | Tempos medianos aprendidos por classe de problema (alimenta a ETA realista) |
| POST | `/calcular` | Executa solver single-ref |
| POST | `/calcular_grupo` | Executa solver multi-ref |
| POST | `/exportar` | Gera .xlsx do resultado do solver |
| POST | `/exportar_multiref` | Gera .xlsx do resultado multi-ref |
| POST | `/exportar_particao` | Gera as planilhas de TODAS as partes do agrupamento num único .zip |
| POST | `/salvar_cores` | Persiste cadastro de cores |
| POST | `/salvar_params` | Persiste parâmetros da UI |
| POST | `/upload` | Parse de .xlsx/.csv de ordem de produção |
| POST | `/upload_imagem` | OCR via Claude API |
| POST | `/alocar_rolos` | Alocação de rolos (aceita números OU objetos c/ metadados; `considerar_lote`) |
| POST | `/exportar_alocacao` | Gera .xlsx da alocação de rolos |
| POST | `/importar_rolos` | Importa rolos de PDF do ERP (2 formatos Vexta, detecção automática) |
| POST | `/salvar_mapa_cor` | Salva mapeamento cor-fornecedor → cor-comercial |
| POST | `/sinalizar_update` | Agenda update para próxima abertura |
| GET | `/versoes` | Snapshots locais + estado do auto-update (v2.13) |
| POST | `/restaurar_versao` | Agenda restauração de versão p/ próxima abertura (v2.13) |
| POST | `/cancelar_restauracao` | Cancela restauração agendada (v2.13) |
| POST | `/reativar_update` | Religa auto-update após restauração (v2.13) |
| POST | `/salvar_plano` | Salva plano de corte portátil .plano.json (v2.13) |
| GET | `/planos_salvos` | Lista planos portáteis salvos (v2.13) |
| POST | `/carregar_plano` | Carrega plano portátil salvo (v2.13) |
| POST | `/importar_plano` | Importa arquivo .plano.json enviado pela UI (v2.13) |

---

## Dependências Python

```
openpyxl      — exportar planilhas Excel
pdfplumber    — importar rolos do ERP via PDF
numpy         — usado pelo motor clássico e pela busca local do multi-ref
```

Instalar: `pip install openpyxl pdfplumber numpy`

O motor exato do single-ref é Python puro (não precisa de numpy). Sem numpy o multi-ref perde a busca local em silêncio — conferir na máquina da fábrica. O restante usa apenas stdlib (http.server, json, os, threading, urllib, zipfile, etc.). O OR-Tools NÃO é dependência: só o gabarito de `tools/bench/` o usa, na máquina de desenvolvimento.

Chave nova no `config.json`: `"motor_single": "exato"` (ou `"classico"` para voltar ao motor antigo sem trocar de versão).

---

## Config.json — referência

```json
{
  "versao": "2.3.0",
  "mesa_comprimento_m": 10.0,
  "limite_folhas_padrao": 70,
  "desvio_absoluto_padrao": 4,
  "desvio_percentual_padrao": 20,
  "criterio_combinacao": "MIN",
  "num_opcoes_saida": 2,
  "anthropic_api_key": "",
  "margem_seguranca_enfesto_m": 0.10,
  "folga_incerteza_pct": 0.03,
  "folga_incerteza_m": 0.0,
  "ponta_minima_util_m": 0.5,
  "alocacao_exata": true,
  "auto_update": true,
  "github_repo": "SEU_USUARIO/pcp-enfestos",
  "update_canal": "estavel"
}
```

Para ativar auto-update: preencher `github_repo` com o repositório real (ex: `"charth/pcp-enfestos"`).

---

## Grade de Teste Rápido

```python
# Blazer Isadora — referência do motor exato (gabarito CP-SAT em 10/11/2026):
#   Opção 1 (menos enfestos):   2 enfestos | desvio 34 | 6,5 pç/mapa | ótimo provado
#   Opção 2 (+1 enfesto):       3 enfestos | desvio 12 | 6,3 pç/mapa | melhor encontrado
#   Opção 3 (mapas mais cheios): 2 enfestos | desvio 36 | 7,5 pç/mapa | ótimo provado
# Motor clássico (reserva): 2 enfestos desvio 39 e 3 enfestos desvio 13.
grade = {
    'BLUES':   {'PP':41,'P':45,'M':25,'G':10},
    'BOSSA':   {'PP':19,'P':20,'M':13,'G':2},
    'JAZZ':    {'PP':44,'P':55,'M':30,'G':11},
    'PRETO':   {'PP':47,'P':54,'M':31,'G':12},
    'SAMBA':   {'PP':39,'P':37,'M':18,'G':5},
    'VALSA':   {'PP':45,'P':50,'M':23,'G':5},
    'VANILLA': {'PP':49,'P':51,'M':27,'G':9},
}
```

---

## Preferências do Diego

- Linguagem: **português BR**, direto, estruturado
- Quer **execução real**, não teoria
- Espera **crítica e counterpoints**, não validação
- Sistema tem que dar **os melhores resultados possíveis** — não aceita resultado pior que o manual
- **Usuários finais são operadores de fábrica** — código robusto, à prova de erro de operador
- Compartilha o sistema com a equipe da fábrica
