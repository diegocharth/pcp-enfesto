"""
PCP Enfestos -- Snapshots de versao e restauracao ("voltar no tempo").

Complementa o auto-update (updater.py), que so guarda UM backup e so anda para
frente. Aqui o sistema guarda um snapshot .zip de CADA versao que ja rodou na
maquina, para sempre, e permite restaurar qualquer uma delas.

Mecanica:
  1. criar_snapshot() zipa o codigo atual em dados/_versoes/vX.Y.Z.zip
     (1 arquivo por versao; se ja existe, nao regrava). E chamado:
       - no boot do servidor (main.py) -- garante snapshot da versao atual;
       - antes de aplicar um update (launcher) -- garante a versao que sai;
       - antes de aplicar uma restauracao -- garante a versao que sai.
  2. listar_versoes() devolve os snapshots locais disponiveis.
  3. sinalizar_restauracao() agenda a restauracao (dados/_restore_pendente/).
  4. aplicar_restauracao_pendente() e chamada pelo launcher.py na abertura,
     ANTES do auto-update: extrai o zip da versao alvo preservando config.json
     e dados/ (mesma regra PRESERVAR do updater).
  5. Apos restaurar, o auto-update e DESLIGADO (config.json: auto_update=false)
     -- senao a proxima abertura subiria de novo para a ultima release e a
     restauracao nao valeria de nada. O update manual ("Atualizar agora" na UI)
     continua funcionando em qualquer versao; reativar_auto_update() religa.

Os snapshots ficam em dados/_versoes/, que e PRESERVADO por updates e
restauracoes (a pasta dados/ inteira e preservada) -- por isso valem "para
sempre", mesmo atravessando versoes.
"""

import json
import os
import re
import shutil
import tempfile
import time
import zipfile

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
VERSOES_DIR   = os.path.join(BASE_DIR, "dados", "_versoes")
RESTORE_DIR   = os.path.join(BASE_DIR, "dados", "_restore_pendente")
RESTORE_INFO  = os.path.join(RESTORE_DIR, "info.json")
CONGELADO_ARQ = os.path.join(BASE_DIR, "dados", "_update_pausado.json")

# Pastas/arquivos que NAO entram no snapshot (dados do usuario e artefatos).
_EXCLUIR_DIRS = {"dados", "__pycache__", ".git", ".pytest_cache", "build",
                 ".claude", "node_modules"}
_EXCLUIR_EXT  = {".pyc", ".pyo"}
# config.json fica FORA do snapshot: contem segredo (anthropic_api_key) e a
# restauracao o preserva de qualquer forma (regra PRESERVAR do updater).
_EXCLUIR_ARQS = {"config.json"}

# Versao valida: digitos/letras/ponto/hifen/underscore (bloqueia path traversal
# em f"v{versao}.zip" -- ex: versao="../../evil").
_RE_VERSAO_OK = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,40}$")


def _ler_versao(base_dir=None):
    base = base_dir or BASE_DIR
    try:
        with open(os.path.join(base, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def _caminho_snapshot(versao, base_dir=None):
    base = base_dir or BASE_DIR
    pasta = os.path.join(base, "dados", "_versoes")
    return os.path.join(pasta, f"v{versao}.zip")


def criar_snapshot(motivo="", base_dir=None):
    """
    Zipa o codigo da versao ATUAL em dados/_versoes/vX.Y.Z.zip.
    Idempotente: se o snapshot desta versao ja existe, nao regrava.

    Returns:
        (criado: bool, caminho: str)
    """
    base   = base_dir or BASE_DIR
    versao = _ler_versao(base)
    destino = _caminho_snapshot(versao, base)
    if os.path.exists(destino):
        return False, destino

    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + ".tmp"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for raiz, dirs, arquivos in os.walk(base):
                rel_raiz = os.path.relpath(raiz, base)
                partes = [] if rel_raiz == "." else rel_raiz.split(os.sep)
                if partes and partes[0] in _EXCLUIR_DIRS:
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if d not in _EXCLUIR_DIRS]
                for nome in arquivos:
                    if os.path.splitext(nome)[1].lower() in _EXCLUIR_EXT:
                        continue
                    if rel_raiz == "." and nome in _EXCLUIR_ARQS:
                        continue
                    caminho = os.path.join(raiz, nome)
                    rel = os.path.relpath(caminho, base)
                    zf.write(caminho, rel)
            zf.writestr("_snapshot.json", json.dumps({
                "versao": versao,
                "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
                "motivo": motivo,
            }, ensure_ascii=False, indent=2))
        os.replace(tmp, destino)
        return True, destino
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def listar_versoes(base_dir=None):
    """
    Lista os snapshots locais disponiveis, da versao mais nova para a mais velha.

    Returns:
        list[dict]: {"versao", "arquivo", "data", "tamanho_kb", "atual": bool}
    """
    base  = base_dir or BASE_DIR
    pasta = os.path.join(base, "dados", "_versoes")
    atual = _ler_versao(base)
    saida = []
    if not os.path.isdir(pasta):
        return saida
    for nome in os.listdir(pasta):
        if not (nome.startswith("v") and nome.endswith(".zip")):
            continue
        caminho = os.path.join(pasta, nome)
        versao  = nome[1:-4]
        try:
            st = os.stat(caminho)
            data = time.strftime("%d/%m/%Y %H:%M", time.localtime(st.st_mtime))
            kb   = round(st.st_size / 1024)
        except OSError:
            data, kb = "", 0
        saida.append({
            "versao"    : versao,
            "arquivo"   : nome,
            "data"      : data,
            "tamanho_kb": kb,
            "atual"     : versao == atual,
        })

    def _chave(item):
        try:
            return tuple(int(x) for x in item["versao"].split("."))
        except ValueError:
            return (0, 0, 0)

    saida.sort(key=_chave, reverse=True)
    return saida


def sinalizar_restauracao(versao, base_dir=None):
    """
    Agenda a restauracao para a proxima abertura do sistema (via launcher).

    Raises:
        ValueError: se a versao e invalida ou nao existe snapshot local dela.
    """
    base = base_dir or BASE_DIR
    versao = str(versao).strip()
    if not _RE_VERSAO_OK.match(versao):
        raise ValueError(f"Versao invalida: {versao!r}")
    zip_local = _caminho_snapshot(versao, base)
    if not os.path.exists(zip_local):
        raise ValueError(
            f"Nao ha snapshot local da versao {versao}. "
            f"Versoes disponiveis: "
            + ", ".join(v["versao"] for v in listar_versoes(base)) )
    pasta = os.path.join(base, "dados", "_restore_pendente")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "info.json"), "w", encoding="utf-8") as f:
        json.dump({"versao": versao, "arquivo": zip_local,
                   "sinalizado_em": time.strftime("%Y-%m-%d %H:%M:%S")},
                  f, ensure_ascii=False, indent=2)


def restauracao_pendente(base_dir=None):
    """Retorna o dict da restauracao agendada, ou None."""
    base = base_dir or BASE_DIR
    info = os.path.join(base, "dados", "_restore_pendente", "info.json")
    if not os.path.exists(info):
        return None
    try:
        with open(info, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def cancelar_restauracao(base_dir=None):
    base = base_dir or BASE_DIR
    pasta = os.path.join(base, "dados", "_restore_pendente")
    if os.path.isdir(pasta):
        shutil.rmtree(pasta, ignore_errors=True)


def _pausar_auto_update(versao, base_dir=None):
    """Desliga o auto-update no config.json e registra o motivo da pausa."""
    base = base_dir or BASE_DIR
    cfg_path = os.path.join(base, "config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["auto_update"] = False
        tmp = cfg_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cfg_path)
    except Exception:
        pass  # sem config nao ha auto-update para pausar
    try:
        with open(os.path.join(base, "dados", "_update_pausado.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"versao_restaurada": versao,
                       "em": time.strftime("%Y-%m-%d %H:%M:%S")},
                      f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def update_pausado(base_dir=None):
    """Retorna o dict {'versao_restaurada', 'em'} se o auto-update esta pausado
    por causa de uma restauracao, senao None."""
    base = base_dir or BASE_DIR
    arq = os.path.join(base, "dados", "_update_pausado.json")
    if not os.path.exists(arq):
        return None
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def reativar_auto_update(base_dir=None):
    """Religa o auto-update (config.json) e remove o marcador de pausa."""
    base = base_dir or BASE_DIR
    cfg_path = os.path.join(base, "config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["auto_update"] = True
        tmp = cfg_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cfg_path)
    except Exception:
        pass
    try:
        os.remove(os.path.join(base, "dados", "_update_pausado.json"))
    except OSError:
        pass


def aplicar_restauracao_pendente(base_dir=None, callback=None):
    """
    Chamada pelo launcher na inicializacao, ANTES do auto-update.
    Se ha restauracao agendada: snapshot da versao atual, extrai o zip da
    versao alvo (preservando config.json e dados/), grava VERSION e pausa o
    auto-update.

    Returns:
        (houve_restauracao: bool, mensagem: str)
    """
    base = base_dir or BASE_DIR

    def log(msg):
        if callback:
            callback(msg)

    info = restauracao_pendente(base)
    if not info:
        return False, "Nenhuma restauracao pendente."

    versao  = info.get("versao", "")
    arquivo = info.get("arquivo", "")
    if not versao or not arquivo or not os.path.exists(arquivo):
        cancelar_restauracao(base)
        return False, "Restauracao pendente invalida (snapshot nao encontrado)."
    if not zipfile.is_zipfile(arquivo):
        cancelar_restauracao(base)
        return False, f"Snapshot corrompido: {arquivo}"

    log(f"Restaurando versao {versao}...")

    # 1. Garante snapshot da versao ATUAL (para poder voltar para frente e
    # para o rollback do passo 3 em caso de falha no meio da copia).
    versao_atual = _ler_versao(base)
    try:
        criar_snapshot(motivo=f"antes de restaurar {versao}", base_dir=base)
    except Exception as e:
        log(f"Aviso: falha ao criar snapshot da versao atual: {e}")

    from updater import _e_caminho_preservado

    def _extrair_para(zip_path, destino_dir):
        """Extrai um snapshot para um diretorio, ja filtrando preservados."""
        pares = []   # (origem_temp, rel)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for membro in zf.namelist():
                rel = membro
                if not rel or rel.endswith("/") or rel == "_snapshot.json":
                    continue
                if _e_caminho_preservado(rel):
                    continue
                alvo = os.path.join(destino_dir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(alvo), exist_ok=True)
                with zf.open(membro) as src, open(alvo, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                pares.append((alvo, rel))
        return pares

    def _copiar_sobre_base(pares):
        for origem, rel in pares:
            destino = os.path.join(base, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy2(origem, destino)

    # 2. Fase de STAGING: extrai o zip inteiro para uma pasta temporaria.
    # Qualquer falha aqui nao toca o codigo instalado.
    staging = tempfile.mkdtemp(prefix="pcp_restore_")
    try:
        try:
            pares = _extrair_para(arquivo, staging)
        except Exception as e:
            cancelar_restauracao(base)   # nao repetir meia-restauracao a cada boot
            return False, f"Falha ao extrair snapshot (nada foi alterado): {e}"

        # 3. Fase de COPIA sobre a base. Janela de falha minima; se algo der
        # errado no meio, tenta voltar a versao atual pelo snapshot dela.
        try:
            _copiar_sobre_base(pares)
        except Exception as e:
            log(f"Falha na copia ({e}); tentando voltar para {versao_atual}...")
            try:
                zip_atual = _caminho_snapshot(versao_atual, base)
                staging2 = tempfile.mkdtemp(prefix="pcp_restore_rb_")
                try:
                    _copiar_sobre_base(_extrair_para(zip_atual, staging2))
                finally:
                    shutil.rmtree(staging2, ignore_errors=True)
                cancelar_restauracao(base)
                return False, (f"Falha ao restaurar {versao}: {e}. "
                               f"Versao {versao_atual} foi recolocada.")
            except Exception as e2:
                cancelar_restauracao(base)
                return False, (f"Falha ao restaurar {versao} ({e}) e o retorno "
                               f"para {versao_atual} tambem falhou ({e2}). "
                               f"Reinstale a partir de dados/_versoes/.")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # 4. VERSION da versao restaurada.
    try:
        with open(os.path.join(base, "VERSION"), "w", encoding="utf-8") as f:
            f.write(versao + "\n")
    except OSError as e:
        return False, f"Falha ao gravar VERSION: {e}"

    # 5. Pausa o auto-update (senao a proxima abertura desfaz a restauracao) e
    # INVALIDA qualquer update pendente agendado antes da restauracao (um
    # pendente obsoleto aplicaria a versao nova por cima da restaurada).
    _pausar_auto_update(versao, base)
    try:
        pend_update = os.path.join(base, "dados", "_update_pendente")
        if os.path.isdir(pend_update):
            shutil.rmtree(pend_update, ignore_errors=True)
            log("Update pendente obsoleto descartado (a restauracao prevalece).")
    except OSError:
        pass

    # 6. Limpa a sinalizacao.
    cancelar_restauracao(base)

    log(f"Versao {versao} restaurada. Auto-update pausado ate ser reativado.")
    return True, f"Versao {versao} restaurada."
