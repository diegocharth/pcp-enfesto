"""
Cria o zip da release excluindo dados do usuario e arquivos temporarios.
Chamado pelo GitHub Actions em .github/workflows/release.yml
Grava o zip em /tmp para evitar incluir o proprio arquivo na compressao.
"""
import os
import sys
import zipfile

BASE    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = open(os.path.join(BASE, "VERSION")).read().strip()

EXCLUIR_DIRS  = {"dados", "__pycache__", ".git", ".github", "node_modules", "tools"}
EXCLUIR_EXTS  = {".pyc", ".pyo", ".zip"}
EXCLUIR_NOMES = set()

# Gravar em /tmp para nao contaminar o projeto durante a criacao
tmp_zip = os.path.join("/tmp", f"pcp_enfestos-{VERSION}.zip")
prefix  = f"pcp_enfestos-{VERSION}/"

with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in EXCLUIR_DIRS]
        for fname in files:
            if os.path.splitext(fname)[1] in EXCLUIR_EXTS:
                continue
            if fname in EXCLUIR_NOMES:
                continue
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, BASE).replace("\\", "/")
            zf.write(full, prefix + rel)

# Mover para o diretório do projeto (onde o release action vai procurar)
import shutil
outzip = os.path.join(BASE, f"pcp_enfestos-{VERSION}.zip")
shutil.move(tmp_zip, outzip)
print(f"Zip criado: {outzip} ({os.path.getsize(outzip) // 1024} KB)")
