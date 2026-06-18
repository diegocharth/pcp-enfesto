# Enfestos Charth — Guia Rápido

Versão 2.8.0 — Charth

---

## Como instalar (primeira vez)

1. Abra a pasta `pcp_enfestos`
2. Dê **duplo clique** em **`INSTALAR.bat`**
3. Aguarde cada etapa concluir (a janela fecha sozinha ao terminar)
4. Um atalho **"Enfestos Charth"** será criado na sua Área de Trabalho

---

## Como usar

Dê **duplo clique** no atalho **Enfestos Charth** na Área de Trabalho.

O sistema abre automaticamente no seu navegador (Chrome ou Edge).

---

## Se o sistema não abrir

Dê duplo clique em **`iniciar_visivel.bat`** — uma janela preta vai aparecer mostrando o erro exato. Mande uma foto dessa janela para o suporte.

---

## Funcionalidades disponíveis

- **Cálculo do plano de corte** — preencha a grade e clique em "Calcular"
- **Múltiplas referências** — clique em "+ Nova referência" para combinar peças
- **Exportar planilha** — clique em "Exportar (.xlsx)" após calcular
- **Upload de ordem de produção** — arraste um arquivo .xlsx ou .csv
- **Alocação de Rolos** — seção no final da página para distribuir rolos por cor
- **Importar rolos do ERP** — botão "Importar do ERP (PDF)" na seção Alocação

---

## Para usar upload de fotos da ordem (OCR)

Abra o arquivo `config.json` na pasta do sistema e preencha:
```
"anthropic_api_key": "sua-chave-aqui"
```
Chave disponível em: console.anthropic.com

---

## Precisa de ajuda?

Se o instalador apresentar problema:
1. Abra o **CMD** (Prompt de Comando)
2. Execute: `pip install openpyxl pdfplumber`
3. Dê duplo clique em `PCP_Enfestos.vbs`
