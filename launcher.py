"""
PCP Enfestos -- Launcher com auto-update silencioso.

Sequencia de inicializacao:
  1. Verifica update no GitHub e aplica automaticamente (sem interação do usuário).
  2. Sobe o servidor HTTP (main.py).
  3. Se o servidor nao subir em N segundos apos um update -> rollback automatico.

Este arquivo e chamado pelo PCP_Enfestos.vbs no lugar de main.py.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def _servidor_respondendo(porta=5050, timeout=2):
    try:
        urllib.request.urlopen(f"http://localhost:{porta}/versao", timeout=timeout)
        return True
    except Exception:
        return False


def _verificar_e_atualizar():
    """
    Verifica GitHub e aplica update automaticamente se houver versão nova.
    Retorna True se houve update aplicado.
    """
    try:
        from updater import checar_atualizacao, baixar_e_aplicar, aplicar_update_pendente

        def log(msg):
            print(f"[UPDATE] {msg}")

        # Primeiro: aplica update já baixado em sessão anterior (mais rápido)
        houve, msg = aplicar_update_pendente(callback=log)
        if houve:
            print(f"[UPDATE] {msg}")
            return True

        # Segundo: verifica GitHub por versão nova
        cfg_path = os.path.join(BASE_DIR, "config.json")
        if not os.path.exists(cfg_path):
            return False
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)

        repo  = cfg.get("github_repo", "")
        canal = cfg.get("update_canal", "estavel")
        auto  = cfg.get("auto_update", True)

        placeholder = not repo or "SEU_USUARIO" in repo
        if not auto or placeholder:
            return False

        print("[UPDATE] Verificando atualizações...")
        info = checar_atualizacao(repo, canal, timeout=8)

        if info.get("erro"):
            print(f"[UPDATE] {info['erro']}")
            return False

        if not info.get("ha_update"):
            print(f"[UPDATE] Sistema atualizado (v{info.get('versao_atual', '?')}).")
            return False

        versao_nova = info["versao_mais_recente"]
        asset_url   = info.get("asset_url")
        if not asset_url:
            print(f"[UPDATE] Versão {versao_nova} disponível mas sem arquivo .zip na release.")
            return False

        print(f"[UPDATE] Nova versão: {versao_nova}. Baixando e aplicando...")
        ok, msg = baixar_e_aplicar(asset_url, versao_nova, callback=log)
        if ok:
            print(f"[UPDATE] {msg}")
        else:
            print(f"[UPDATE] Falha: {msg}. Continuando com versão atual.")
        return ok

    except Exception as e:
        print(f"[UPDATE] Aviso: {e}. Continuando sem atualizar.")
        return False


def main():
    houve_update = _verificar_e_atualizar()

    # --- Subir o servidor ---
    python_exe = sys.executable
    servidor_py = os.path.join(BASE_DIR, "main.py")

    print("[LAUNCHER] Iniciando servidor PCP Enfestos...")
    proc = subprocess.Popen([python_exe, servidor_py])

    # Aguarda o servidor responder (até 15 segundos)
    for _ in range(30):
        time.sleep(0.5)
        if _servidor_respondendo():
            print("[LAUNCHER] Servidor iniciado com sucesso.")
            break
    else:
        # Rollback se o update quebrou o servidor
        if houve_update:
            print("[LAUNCHER] ATENCAO: servidor nao subiu apos update. Executando rollback...")
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                from updater import rollback
                ok, msg = rollback()
                print(f"[LAUNCHER] {msg}")
                if ok:
                    proc = subprocess.Popen([python_exe, servidor_py])
                    for _ in range(20):
                        time.sleep(0.5)
                        if _servidor_respondendo():
                            print("[LAUNCHER] Servidor restaurado apos rollback.")
                            break
                    else:
                        print("[LAUNCHER] ERRO: servidor nao subiu mesmo apos rollback.")
            except Exception as e:
                print(f"[LAUNCHER] Falha no rollback: {e}")
        else:
            print("[LAUNCHER] Servidor nao respondeu em 15s. Verifique erros em main.py.")

    # Mantém o launcher vivo enquanto o servidor roda
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
