# PCP Enfestos — Contexto para Claude Code
> Leia este arquivo inteiro antes de qualquer coisa.

---

## O Projeto

Sistema local de otimização de plano de corte para confecção da **Charth** (moda feminina premium). Dono: **Diego Faria**.

Roda como servidor Python local na porta 5050. Interface HTML no navegador. Sem cloud, sem banco de dados. Operadores de fábrica são os usuários finais — o sistema precisa ser robusto e à prova de erro de operador.

**Stack:** Python 3.10+ · HTML/CSS/JS vanilla · openpyxl · pdfplumber · Windows 10/11

**Versão atual:** 2.11.0

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
| **Ponta de rolo** | Sobra ao final de um rolo. Se ≥ `ponta_minima_util_m`: estoque. Se menor: refugo. |

---

## Estrutura de Arquivos

```
pcp_enfestos/
├── CLAUDE.md                  ← VOCÊ ESTÁ AQUI
├── LEIA-ME.md                 ← guia para o usuário final
├── INSTALAR.bat               ← instala Python + bibliotecas + cria atalho
├── PCP_Enfestos.vbs           ← INICIALIZADOR — duplo clique do usuário
├── iniciar_visivel.bat        ← debug: abre CMD visível para ver erros
├── main.py                    ← servidor HTTP porta 5050 (v2.8.0)
├── launcher.py                ← aplica auto-update pendente, depois inicia main.py
├── updater.py                 ← motor de auto-update via GitHub Releases
├── VERSION                    ← "2.8.0"
├── interface.html             ← UI completa no navegador (~1800 linhas)
├── config.json                ← parâmetros padrão persistentes
├── engine/
│   ├── solver.py              ← algoritmo de busca — NÃO MODIFICAR
│   ├── solver_multiref.py     ← solver multi-referência (v2.9: fix crash; v2.10: n_mapas_max p/ branch-and-bound)
│   ├── tolerancia.py          ← regras de desvio permitido por tamanho
│   ├── mapas.py               ← gerador de composições de encaixe
│   ├── cache_planos.py        ← cache persistente de resultados + tempos aprendidos (ETA)
│   ├── alocador_rolos.py      ← motor FFD de alocação de rolos
│   └── import_rolos/
│       ├── base.py            ← classe abstrata FonteRolos
│       ├── fonte_vexta_pdf.py ← parser PDF do ERP Vexta
│       ├── fonte_sisplan.py   ← stub para ERP Sisplan (não implementado)
│       ├── mapa_cores.py      ← mapeamento cor-fornecedor → cor-comercial
│       └── registry.py        ← obtém fonte correta por tipo/extensão
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

# Rodar todos os testes (54 no total)
python -m pytest tests/ -v

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

## Algoritmo do Solver (NÃO TOCAR)

**Hierarquia de otimização:**
1. **Menor desvio da grade** — premissa absoluta
2. **Maior média de peças/mapa** — melhor aproveitamento de tecido
3. **Menor número de enfestos** — menos setup

**Ranqueamento real (lexicográfico, sem pesos configuráveis):** a ordenação das soluções é estritamente lexicográfica — `menos enfestos -> menor desvio -> mais peças/mapa -> menor desvio relativo`. NÃO existem pesos de eficiência configuráveis (os antigos `peso_enc`/`peso_op`/`peso_eficiencia_*` eram placebo e foram removidos — o solver nunca os lia).

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
| POST | `/alocar_rolos` | Motor FFD de alocação de rolos |
| POST | `/exportar_alocacao` | Gera .xlsx da alocação de rolos |
| POST | `/importar_rolos` | Importa rolos de PDF do ERP (Vexta) |
| POST | `/salvar_mapa_cor` | Salva mapeamento cor-fornecedor → cor-comercial |
| POST | `/sinalizar_update` | Agenda update para próxima abertura |

---

## Dependências Python

```
openpyxl      — exportar planilhas Excel
pdfplumber    — importar rolos do ERP via PDF
```

Instalar: `pip install openpyxl pdfplumber`

O restante usa apenas stdlib (http.server, json, os, threading, urllib, zipfile, etc.).

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
  "auto_update": true,
  "github_repo": "SEU_USUARIO/pcp-enfestos",
  "update_canal": "estavel"
}
```

Para ativar auto-update: preencher `github_repo` com o repositório real (ex: `"charth/pcp-enfestos"`).

---

## Grade de Teste Rápido

```python
# Blazer Isadora — resultado de referência: 3 enfestos | desvio ≤ 14 | ≥7 pç/mapa
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
