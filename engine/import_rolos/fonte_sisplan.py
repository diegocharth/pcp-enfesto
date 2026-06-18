"""
Adaptador para o ERP Sisplan (migracao futura).

TODO: Implementar quando a empresa migrar do Vexta para o Sisplan.
  - Verificar formato de exportacao do Sisplan (PDF? Excel? API?)
  - Implementar FonteSisplan.extrair() seguindo o mesmo contrato de FonteRolos
  - Registrar em registry.py com tipo='sisplan'

Para implementar:
  1. Obter um documento de exportacao de rolos do Sisplan.
  2. Identificar os campos equivalentes a: cor, comprimento_m, rolo_id, lote.
  3. Criar o parser (prefira pdfplumber para PDF, openpyxl para Excel).
  4. Adicionar ao registry: FONTES['sisplan'] = FonteSisplan

Contrato obrigatorio (herdado de FonteRolos):
  extrair(caminho_arquivo) -> (list[dict], list[str])
  Onde o dict tem: cor_fornecedor, comprimento_m, rolo_id, lote, artigo, reservado, linha_original
"""

from .base import FonteRolos


class FonteSisplan(FonteRolos):
    """Stub documentado para o ERP Sisplan. NAO implementado."""

    def extrair(self, caminho_arquivo):
        raise NotImplementedError(
            "Suporte ao Sisplan ainda nao foi implementado. "
            "Consulte o TODO no topo deste arquivo."
        )

    def nome_fonte(self):
        return "Sisplan (nao implementado)"
