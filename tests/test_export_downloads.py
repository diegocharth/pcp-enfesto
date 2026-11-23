"""Guarda de regressao do A1: o plano de corte NAO deve ser copiado para o
Downloads pelo servidor (so o navegador baixa via /baixar). Caso contrario
o arquivo aparece duas vezes no Downloads."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src_main():
    with open(os.path.join(BASE, "main.py"), encoding="utf-8") as f:
        return f.read()


def test_main_nao_referencia_copiar_para_downloads():
    src = _src_main()
    assert "_copiar_para_downloads" not in src, (
        "main.py ainda copia o arquivo para o Downloads; isso causa download "
        "duplicado do plano de corte (servidor + navegador)."
    )


def test_download_aceita_nome_fora_do_latin1():
    # Etapa 6 (C6): o cabecalho Content-Disposition precisa caber em latin-1
    # (http.server) mesmo com travessao/emoji no nome; o nome real vai em UTF-8.
    import sys
    from urllib.parse import unquote
    sys.path.insert(0, BASE)
    import main
    nome = "plano_corte_CALÇA_NAS_–_teste_😀_20261123.xlsx"
    cab = main._content_disposition(nome)
    cab.encode("latin-1")                                  # nao pode levantar erro
    assert "filename*=UTF-8''" in cab
    assert unquote(cab.split("filename*=UTF-8''")[1]) == nome
    assert 'filename="plano_corte_CALCA_NAS' in cab
    assert "_content_disposition(nome)" in _src_main()
