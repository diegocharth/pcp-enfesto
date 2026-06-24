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
