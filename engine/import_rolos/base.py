"""
Interface base para adaptadores de fonte de rolos.

Para adicionar suporte a um novo ERP, crie um arquivo fonteXXX.py neste pacote
que implemente a classe FonteRolos e registre-o em registry.py.
"""


class FonteRolos:
    """
    Interface que todo adaptador de fonte de rolos deve implementar.
    Recebe o caminho para um arquivo (PDF, Excel, CSV, etc.) e retorna
    uma lista de registros de rolo no formato padronizado.
    """

    def extrair(self, caminho_arquivo):
        """
        Le o arquivo e retorna lista de registros crus.

        Args:
            caminho_arquivo (str): Caminho absoluto para o arquivo.

        Returns:
            list[dict]: Lista de dicts com as chaves:
                - cor_fornecedor (str): Nome da cor como aparece no ERP/fornecedor.
                - comprimento_m (float): Comprimento do rolo em metros.
                - rolo_id (str | None): Numero/ID do rolo, se disponivel.
                - lote (str | None): Numero do lote, se disponivel.
                - artigo (str | None): Codigo/nome do artigo, se disponivel.
                - reservado (bool): True se rolo esta reservado (secao "Reservados").
                - linha_original (str): Linha de texto original para rastreabilidade.

        Raises:
            FileNotFoundError: Se o arquivo nao existir.
            ValueError: Se o formato do arquivo nao for reconhecido.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} deve implementar o metodo extrair()."
        )

    def nome_fonte(self):
        """Retorna identificador legivel desta fonte (para logs e mensagens)."""
        return self.__class__.__name__
