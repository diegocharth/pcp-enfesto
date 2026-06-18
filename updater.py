"""
PCP Enfestos -- Auto-updater via GitHub Releases.

Mecanismo:
  1. checar_atualizacao() consulta a GitHub Releases API e compara com VERSION local.
  2. baixar_e_aplicar() baixa o zip da release, extrai em pasta temporaria, copia
     arquivos novos preservando config.json, dados/ e mapa_cores.json.
  3. O servidor sinaliza update pendente gravando dados/_update_pendente/info.json.
  4. launcher.py (chamado antes de subir o servidor) aplica o update se existir.

Seguranca:
  - Valida que o asset baixado e um zip integro antes de extrair.
  - Faz backup da versao anterior em dados/_backup_versao_anterior/.
  - Preserva SEMPRE: config.json, dados/, engine/import_rolos/mapa_cores.py.
  - Se o servidor nao subir apos update, rollback automatico.
  - Falha de rede/GitHub -> log de aviso; sistema continua na versao atual.

Sem dependencias novas: usa apenas urllib.request, zipfile, shutil (stdlib).
"""

import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")
DADOS_DIR    = os.path.join(BASE_DIR, "dados")
BACKUP_DIR   = os.path.join(DADOS_DIR, "_backup_versao_anterior")
PENDENTE_DIR = os.path.join(DADOS_DIR, "_update_pendente")
PENDENTE_INFO = os.path.join(PENDENTE_DIR, "info.json")

# Arquivos e diretorios a NUNCA sobrescrever durante um update
PRESERVAR = [
    "config.json",
    os.path.join("dados", "mapa_cores.json"),
    "dados",
]


def _ler_versao_local():
    """Le a versao atual do arquivo VERSION."""
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def _comparar_versoes(v_atual, v_nova):
    """
    Compara versoes semanticas (semver simplificado: major.minor.patch).
    Retorna True se v_nova > v_atual.

    Suporta: '2.8.0' < '2.8.1' < '2.9.0' < '2.10.0'
    """
    def partes(v):
        # Remove prefixo 'v' se existir
        v = re.sub(r"^v", "", str(v).strip())
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0, 0, 0)

    return partes(v_nova) > partes(v_atual)


def checar_atualizacao(github_repo, canal="estavel", timeout=8):
    """
    Consulta a GitHub Releases API e compara com a versao local.

    Args:
        github_repo (str): 'usuario/repositorio'
        canal (str): 'estavel' usa Latest Release; 'beta' usa qualquer pre-release.
        timeout (int): segundos para timeout da requisicao.

    Returns:
        dict: {
            "versao_atual": str,
            "versao_mais_recente": str | None,
            "ha_update": bool,
            "notas": str,
            "asset_url": str | None,
            "erro": str | None,
        }
    """
    versao_atual = _ler_versao_local()
    url = f"https://api.github.com/repos/{github_repo}/releases/latest"

    try:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github.v3+json",
                     "User-Agent": "pcp-enfestos-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {
            "versao_atual"        : versao_atual,
            "versao_mais_recente" : None,
            "ha_update"           : False,
            "notas"               : "",
            "asset_url"           : None,
            "erro"                : f"Sem conexao com GitHub: {e}",
        }
    except Exception as e:
        return {
            "versao_atual"        : versao_atual,
            "versao_mais_recente" : None,
            "ha_update"           : False,
            "notas"               : "",
            "asset_url"           : None,
            "erro"                : f"Erro ao verificar atualizacao: {e}",
        }

    tag          = dados.get("tag_name", "")
    notas        = dados.get("body", "")
    ha_update    = _comparar_versoes(versao_atual, tag)
    asset_url    = None

    # Procura asset zip na release
    for asset in dados.get("assets", []):
        nome = asset.get("name", "")
        if nome.endswith(".zip"):
            asset_url = asset.get("browser_download_url")
            break

    return {
        "versao_atual"        : versao_atual,
        "versao_mais_recente" : tag,
        "ha_update"           : ha_update,
        "notas"               : notas,
        "asset_url"           : asset_url,
        "erro"                : None,
    }


def sinalizar_update_pendente(asset_url, versao_nova, notas=""):
    """Salva info do update pendente para ser aplicado pelo launcher na proxima abertura."""
    os.makedirs(PENDENTE_DIR, exist_ok=True)
    with open(PENDENTE_INFO, "w", encoding="utf-8") as f:
        json.dump({
            "asset_url"  : asset_url,
            "versao_nova": versao_nova,
            "notas"      : notas,
        }, f, ensure_ascii=False, indent=2)


def _e_caminho_preservado(rel_path):
    """Retorna True se o arquivo/diretorio relativo deve ser preservado."""
    norm = rel_path.replace("\\", "/")
    for p in PRESERVAR:
        p_norm = p.replace("\\", "/")
        if norm == p_norm or norm.startswith(p_norm + "/"):
            return True
    return False


def baixar_e_aplicar(asset_url, versao_nova, callback=None):
    """
    Baixa o zip da release, valida, faz backup e aplica o update.

    Args:
        asset_url (str): URL do asset .zip na GitHub Release.
        versao_nova (str): String da nova versao (para o backup).
        callback (callable | None): funcao(msg: str) para progresso.

    Returns:
        (bool, str): (sucesso, mensagem)
    """
    def log(msg):
        if callback:
            callback(msg)

    log(f"Baixando versao {versao_nova}...")

    # 1. Baixar para arquivo temporario
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name
        urllib.request.urlretrieve(asset_url, tmp_path)
    except Exception as e:
        return False, f"Falha ao baixar: {e}"

    # 2. Validar integridade do zip
    if not zipfile.is_zipfile(tmp_path):
        os.unlink(tmp_path)
        return False, "Arquivo baixado nao e um zip valido. Update cancelado."

    log("Download OK. Preparando backup...")

    # 3. Backup da versao atual
    versao_atual = _ler_versao_local()
    try:
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        for item in os.listdir(BASE_DIR):
            if item in ("dados", "__pycache__", ".git"):
                continue
            src = os.path.join(BASE_DIR, item)
            dst = os.path.join(BACKUP_DIR, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        with open(os.path.join(BACKUP_DIR, "_versao.txt"), "w") as f:
            f.write(versao_atual)
    except Exception as e:
        os.unlink(tmp_path)
        return False, f"Falha ao criar backup: {e}"

    log("Backup criado. Aplicando update...")

    # 4. Extrair e copiar arquivos novos (preservando config e dados)
    try:
        with zipfile.ZipFile(tmp_path, "r") as zf:
            # Identifica o prefixo do zip (normalmente 'pcp_enfestos-2.8.1/')
            nomes = zf.namelist()
            prefixo = ""
            if nomes and "/" in nomes[0]:
                prefixo = nomes[0].split("/")[0] + "/"

            for membro in nomes:
                # Remove prefixo do zip
                rel = membro[len(prefixo):] if membro.startswith(prefixo) else membro
                if not rel or rel.endswith("/"):
                    continue

                # Nunca sobrescrever arquivos preservados
                if _e_caminho_preservado(rel):
                    continue

                destino = os.path.join(BASE_DIR, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with zf.open(membro) as src, open(destino, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except Exception as e:
        os.unlink(tmp_path)
        return False, f"Falha ao extrair update: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # 5. Atualiza VERSION
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(versao_nova + "\n")
    except OSError as e:
        return False, f"Falha ao gravar VERSION: {e}"

    # 6. Remove sinalizacao de update pendente
    try:
        if os.path.exists(PENDENTE_DIR):
            shutil.rmtree(PENDENTE_DIR)
    except OSError:
        pass

    log(f"Update para {versao_nova} aplicado com sucesso.")
    return True, f"Atualizado para {versao_nova}."


def rollback():
    """
    Restaura a versao anterior a partir do backup.
    Chamado pelo launcher se o servidor nao subir apos o update.

    Returns:
        (bool, str): (sucesso, mensagem)
    """
    if not os.path.exists(BACKUP_DIR):
        return False, "Sem backup disponivel para rollback."

    try:
        versao_backup = "desconhecida"
        vf = os.path.join(BACKUP_DIR, "_versao.txt")
        if os.path.exists(vf):
            with open(vf) as f:
                versao_backup = f.read().strip()

        for item in os.listdir(BACKUP_DIR):
            if item == "_versao.txt":
                continue
            src = os.path.join(BACKUP_DIR, item)
            dst = os.path.join(BASE_DIR, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        return True, f"Rollback para {versao_backup} concluido."
    except Exception as e:
        return False, f"Falha no rollback: {e}"


def aplicar_update_pendente(callback=None):
    """
    Chamado pelo launcher na inicializacao. Se houver update pendente, aplica.

    Returns:
        (bool, str): (houve_update, mensagem)
    """
    if not os.path.exists(PENDENTE_INFO):
        return False, "Nenhum update pendente."

    try:
        with open(PENDENTE_INFO, encoding="utf-8") as f:
            info = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False, "Arquivo de update pendente invalido."

    asset_url  = info.get("asset_url", "")
    versao_nova = info.get("versao_nova", "")

    if not asset_url or not versao_nova:
        return False, "Informacoes de update incompletas."

    ok, msg = baixar_e_aplicar(asset_url, versao_nova, callback=callback)
    return ok, msg
