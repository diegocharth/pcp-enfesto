# Enfestos Charth — Guia Rápido

Versão 2.15.0 — Charth

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

- **Cálculo do plano de corte** — preencha a grade e clique em "Calcular".
  O sistema mostra o plano com **menos enfestos** e, quando reduz o ajuste de
  grade, também o plano com **1 enfesto a mais**. Planos com mapas mais cheios
  aparecem como opção separada, para você aprovar. O selo **"Ótimo provado"**
  indica que, dentro da tolerância, não existe plano melhor para aquela opção
- **Múltiplas referências** — clique em "+ Nova referência" para combinar peças
- **Exportar planilha** — clique em "Exportar (.xlsx)" após calcular
- **Upload de ordem de produção** — arraste um arquivo .xlsx ou .csv
- **Alocação de Rolos** — seção no final da página para distribuir rolos por cor.
  O sistema procura a **menor compra de tecido** possível; em planos combinados
  grandes a alocação pode levar alguns segundos. Se a grade ou os parâmetros
  mudarem depois do cálculo, recalcule antes de alocar
- **Importar rolos do ERP** — botão "Importar rolos do ERP (PDF)" na seção Alocação.
  Aceita os dois relatórios do sistema: Reserva de Tecidos e Estoque Total (ROLOS).
  Na primeira vez, vincule a cor do fornecedor com a sua Cor Comercial — fica salvo.
- **Considerar Lote** — marque o botão "Considerar Lote" para a alocação tentar
  usar um único lote por cor (variação de tonalidade); desmarcado, ignora o lote
- **Plano de corte salvo** — todo plano exportado também é salvo como arquivo
  `.plano.json`; use "Carregar plano salvo" na seção Alocação para alocar rolos
  em um plano de outro dia, sem recalcular
- **Versões e restauração** — seção no final da página; toda versão fica guardada
  e você pode voltar para qualquer versão anterior se uma atualização não agradar

---

## Para usar upload de fotos da ordem (OCR)

Abra o arquivo `config.json` na pasta do sistema e preencha:
```
"anthropic_api_key": "sua-chave-aqui"
```
Chave disponível em: console.anthropic.com

---

## Precisa de ajuda?

Se o sistema avisar que faltam bibliotecas, feche-o e rode `INSTALAR.bat` de novo.

Se o instalador apresentar problema:
1. Abra o **CMD** (Prompt de Comando)
2. Execute: `pip install openpyxl pdfplumber numpy`
3. Dê duplo clique em `PCP_Enfestos.vbs`
