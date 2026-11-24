"""Imprime cada teste que falhou (junit.xml do pytest) como anotacao do GitHub
Actions (::error ...), visivel na pagina do workflow e na API sem login.
Uso no CI: python tools/anotar_falhas.py junit.xml"""
import sys
import xml.etree.ElementTree as ET


def main(caminho):
    n = 0
    for tc in ET.parse(caminho).iter("testcase"):
        for f in list(tc.findall("failure")) + list(tc.findall("error")):
            msg = " ".join((f.get("message") or f.text or "").split())[:500]
            nome = f"{tc.get('classname')}.{tc.get('name')}"
            print(f"::error title={nome}::{msg}")
            n += 1
    print(f"{n} teste(s) com falha")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "junit.xml")
