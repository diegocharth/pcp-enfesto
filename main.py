#!/usr/bin/env python3
"""
PCP Enfestos v2.8.0
Changelog:
  v2.8.0 - Alocador de rolos (FFD adaptado, margem por sub-enfesto, ponta como estoque).
           Import do controle de rolos do ERP Vexta (PDF) com mapeamento de cor.
           Auto-update via GitHub Releases.
  v2.7.0 - Multi-ref: testa TODOS os agrupamentos possÃ­veis (pares, trios, todos juntos).
           Avalia todos os particionamentos e exibe a combinaÃ§Ã£o Ã³tima com tabela comparativa.
           Timeout individual max=180s; agrupamento = min(360, tÃ—n_refs).
  v2.6.1 - Multi-ref: cada ref recebe timeout completo; combinado usa timeout/3.
  v2.6.0 - Zombie fix (netstat+taskkill). Cor salva sem prefixo REF| (split|[-1]).
  v2.4.0 - Solver: premissa principal = menos enfestos. hi=0 via check_viavel.
  v2.3.1 - Solver corrigido. PersistÃªncia de parÃ¢metros e cores. Progresso real.
  v2.3.0 - Shutdown via botÃ£o, VBS robusto
  v2.1.0 - MÃºltiplas refs, upload, cores salvas
  v2.0.0 - Interface HTML, solver otimizado
"""

import json, os, sys, threading, webbrowser, base64, time, signal, subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

VERSION      = "2.8.1"
CORES_FILE        = os.path.join(BASE_DIR, "dados", "cores_salvas.json")
PARAMS_FILE       = os.path.join(BASE_DIR, "dados", "parametros_salvos.json")
PID_FILE          = os.path.join(BASE_DIR, "dados", "servidor.pid")
MAPA_CORES_FILE   = os.path.join(BASE_DIR, "dados", "mapa_cores.json")
HISTORICO_FILE    = os.path.join(BASE_DIR, "dados", "historico_solucoes.json")

# ImportaÃ§Ãµes lazy para evitar erro de startup
def _importar():
    global resolver, calcular_limites_grade, exportar_xlsx, parse_arquivo, extrair_grade_de_imagem
    global resolver_multiref, exportar_multiref_xlsx
    global alocar_rolos_fn, exportar_alocacao_xlsx
    global obter_fonte_rolos, aplicar_mapa_cores, resolver_cor_fn, adicionar_mapeamento_fn
    global carregar_mapa_cores, salvar_mapa_cores_fn
    global checar_atualizacao_fn, sinalizar_update_fn
    from engine.solver              import resolver
    from engine.tolerancia          import calcular_limites_grade
    from exportar.export_xlsx       import exportar as exportar_xlsx
    from exportar.export_xlsx       import exportar_multiref as exportar_multiref_xlsx
    from exportar.export_xlsx       import exportar_alocacao as exportar_alocacao_xlsx
    from exportar.upload_parser     import parse_arquivo
    from exportar.upload_parser_img import extrair_grade_de_imagem
    from engine.solver_multiref     import resolver_multiref
    from engine.alocador_rolos      import alocar_rolos as alocar_rolos_fn
    from engine.import_rolos.registry   import obter_fonte as obter_fonte_rolos
    from engine.import_rolos.mapa_cores import (
        aplicar_mapa  as aplicar_mapa_cores,
        resolver_cor  as resolver_cor_fn,
        adicionar_mapeamento as adicionar_mapeamento_fn,
        carregar_mapa as carregar_mapa_cores,
        salvar_mapa   as salvar_mapa_cores_fn,
    )
    from updater import checar_atualizacao as checar_atualizacao_fn
    from updater import sinalizar_update_pendente as sinalizar_update_fn

_importar()


def _ensure_dados():
    os.makedirs(os.path.join(BASE_DIR, "dados"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "dados", "resultados"), exist_ok=True)

def carregar_config():
    with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)

def carregar_cores_salvas():
    if os.path.exists(CORES_FILE):
        with open(CORES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar_cores_arquivo(cores):
    _ensure_dados()
    with open(CORES_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(set(c.upper() for c in cores if c)), f,
                  ensure_ascii=False, indent=2)

def carregar_params_salvos():
    if os.path.exists(PARAMS_FILE):
        with open(PARAMS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_params(params):
    _ensure_dados()
    with open(PARAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)

def gravar_pid():
    _ensure_dados()
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


# â”€â”€ Aprendizado histÃ³rico â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _fingerprint_grade(grade_total: dict, tamanhos: list) -> str:
    """Identifica uma grade pela distribuiÃ§Ã£o proporcional de tamanhos (Â±5%)."""
    total = sum(grade_total.get(t, 0) for t in tamanhos)
    if total == 0:
        return "vazio"
    partes = []
    for t in tamanhos:
        pct = round(grade_total.get(t, 0) / total * 20) * 5  # arredonda para mÃºltiplo de 5%
        if pct > 0:
            partes.append(f"{t}={pct}")
    return ",".join(partes)

def carregar_historico(fingerprint: str) -> list:
    """Retorna os mapas histÃ³ricos da melhor soluÃ§Ã£o para esta grade."""
    if not os.path.exists(HISTORICO_FILE):
        return []
    try:
        with open(HISTORICO_FILE, encoding="utf-8") as f:
            historico = json.load(f)
        entrada = historico.get(fingerprint)
        if not entrada:
            return []
        return entrada.get("mapas", [])
    except Exception:
        return []

def salvar_historico(fingerprint: str, mapas_vencedores: list, desvio: int):
    """Salva ou atualiza a melhor soluÃ§Ã£o para esta grade no histÃ³rico."""
    _ensure_dados()
    historico = {}
    if os.path.exists(HISTORICO_FILE):
        try:
            with open(HISTORICO_FILE, encoding="utf-8") as f:
                historico = json.load(f)
        except Exception:
            historico = {}

    entrada_atual = historico.get(fingerprint, {})
    desvio_atual = entrada_atual.get("desvio", 9999)

    # SÃ³ atualiza se esta soluÃ§Ã£o for melhor (menor desvio)
    if desvio < desvio_atual:
        historico[fingerprint] = {
            "mapas": mapas_vencedores,
            "desvio": desvio,
            "n_mapas": len(mapas_vencedores),
        }
        with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def remover_pid():
    try: os.remove(PID_FILE)
    except: pass


# Fila de progresso para o cÃ¡lculo em andamento
_progresso_fila = []
_progresso_lock = threading.Lock()

def _add_progresso(msg):
    with _progresso_lock:
        _progresso_fila.append(msg)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(BASE_DIR, "interface.html"), "rb") as f:
                self._send_html(f.read())
        elif path == "/versao":
            self._send(200, {"versao": VERSION})
        elif path == "/cores":
            self._send(200, {"cores": carregar_cores_salvas()})
        elif path == "/params":
            self._send(200, carregar_params_salvos())
        elif path == "/config_pub":
            cfg = carregar_config()
            self._send(200, {"tem_api_key": bool(cfg.get("anthropic_api_key","").strip())})
        elif path == "/progresso":
            with _progresso_lock:
                msgs = list(_progresso_fila)
                _progresso_fila.clear()
            self._send(200, {"msgs": msgs})
        elif path == "/encerrar":
            self._send(200, {"ok": True})
            threading.Thread(target=_encerrar_servidor, daemon=True).start()
        elif path == "/mapa_cores":
            self._send(200, {"mapa": carregar_mapa_cores(MAPA_CORES_FILE)})
        elif path == "/checar_update":
            self._checar_update()
        elif path == "/versao_completa":
            self._send(200, {"versao": VERSION, "versao_local": VERSION})
        elif path == "/baixar":
            self._baixar_arquivo()
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        path   = urlparse(self.path).path
        try:
            if   path == "/calcular":           self._calcular(json.loads(body))
            elif path == "/calcular_grupo":     self._calcular_grupo(json.loads(body))
            elif path == "/exportar":           self._exportar(json.loads(body))
            elif path == "/exportar_multiref":  self._exportar_multiref(json.loads(body))
            elif path == "/salvar_cores":       self._salvar_cores(json.loads(body))
            elif path == "/salvar_params":      self._salvar_params(json.loads(body))
            elif path == "/upload":             self._upload(json.loads(body))
            elif path == "/upload_imagem":      self._upload_imagem(json.loads(body))
            elif path == "/alocar_rolos":       self._alocar_rolos(json.loads(body))
            elif path == "/exportar_alocacao":  self._exportar_alocacao(json.loads(body))
            elif path == "/importar_rolos":     self._importar_rolos(json.loads(body))
            elif path == "/salvar_mapa_cor":    self._salvar_mapa_cor(json.loads(body))
            elif path == "/sinalizar_update":   self._sinalizar_update(json.loads(body))
            else: self._send(404, {"erro": "Rota nao encontrada"})
        except Exception as e:
            import traceback
            self._send(500, {"erro": str(e), "trace": traceback.format_exc()})

    def _calcular(self, p):
        cfg = carregar_config()
        cfg["consumo_peca_m"]              = float(p.get("consumo", 1.0645))
        cfg["mesa_comprimento_m"]          = float(p.get("mesa", 10.0))
        cfg["limite_folhas_padrao"]        = int(p.get("max_folhas", 70))
        cfg["num_opcoes_saida"]            = int(p.get("num_opcoes", 2))
        cfg["desvio_absoluto_padrao"]      = int(p.get("tol_abs", 4))
        cfg["desvio_percentual_padrao"]    = int(p.get("tol_pct", 20))
        cfg["criterio_combinacao"]         = p.get("criterio", "MIN")
        cfg["peso_eficiencia_encaixe"]     = float(p.get("peso_enc", 6)) / 10.0
        cfg["peso_eficiencia_operacional"] = float(p.get("peso_op", 4)) / 10.0

        tamanhos   = p.get("tamanhos", ["PP","P","M","G"])
        grade      = {cor: {t: int(v) for t,v in tms.items()}
                      for cor, tms in p.get("grade", {}).items()}
        regras     = p.get("regras_especiais", {})
        referencia = p.get("referencia", "REF")
        timeout    = int(p.get("timeout", 120))

        # Salvar parÃ¢metros usados para prÃ³xima sessÃ£o
        salvar_params({
            "consumo": p.get("consumo", 1.0645),
            "mesa": p.get("mesa", 10.0),
            "max_folhas": p.get("max_folhas", 70),
            "num_opcoes": p.get("num_opcoes", 2),
            "tol_abs": p.get("tol_abs", 4),
            "tol_pct": p.get("tol_pct", 20),
            "criterio": p.get("criterio", "MIN"),
            "peso_enc": p.get("peso_enc", 6),
            "peso_op": p.get("peso_op", 4),
            "timeout": timeout,
            "tamanhos": tamanhos,
            "regras_especiais": regras,
        })

        # Salvar cores usadas (extrair sÃ³ a cor, sem prefixo de referÃªncia "Ref|Cor")
        cores_brutas = list(grade.keys())
        cores_limpas = list({c.split("|")[-1] for c in cores_brutas})
        cores_usadas = cores_limpas + carregar_cores_salvas()
        salvar_cores_arquivo(cores_usadas)

        limites  = calcular_limites_grade(grade, tamanhos, cfg, regras)

        # Calcular grade total e fingerprint para o histÃ³rico
        grade_total = {t: sum(grade[c].get(t, 0) for c in grade) for t in tamanhos}
        fp = _fingerprint_grade(grade_total, tamanhos)

        # Injetar mapas histÃ³ricos no inÃ­cio da lista de prioridades
        from engine import mapas as _mapas_mod
        historicos = carregar_historico(fp)
        _mapas_mod._mapas_historicos_injetar = historicos

        with _progresso_lock:
            _progresso_fila.clear()

        logs     = []
        def cb(msg):
            logs.append(msg)
            _add_progresso(msg)

        try:
            solucoes = resolver(grade, tamanhos, limites, cfg,
                                callback_progresso=cb, timeout_s=timeout)
        finally:
            _mapas_mod._mapas_historicos_injetar = []  # sempre limpar apÃ³s uso

        if not solucoes:
            self._send(200, {"erro": "Nenhuma soluÃ§Ã£o encontrada. Tente aumentar tolerÃ¢ncia ou timeout."})
            return

        # Salvar melhor soluÃ§Ã£o no histÃ³rico (aprendizado)
        melhor = solucoes[0]
        try:
            mapas_vencedores = melhor.get("mapas") or []
            # mapas pode ser lista de dicts ou lista de dicts com valores int
            desvio_melhor    = int(melhor.get("resumo", {}).get("desvio_total", 9999))
            if mapas_vencedores:
                salvar_historico(fp, mapas_vencedores, desvio_melhor)
        except Exception:
            pass  # nunca bloquear o resultado por falha no histÃ³rico

        def ser(o):
            if isinstance(o, dict): return {k: ser(v) for k,v in o.items()}
            if isinstance(o, list): return [ser(x) for x in o]
            if hasattr(o, "tolist"): return o.tolist()
            return o

        self._send(200, {
            "solucoes"  : ser(solucoes),
            "log"       : logs,
            "tamanhos"  : tamanhos,
            "grade"     : grade,
            "limites"   : {c: {t: list(l) for t,l in ts.items()} for c,ts in limites.items()},
            "referencia": referencia,
            "config"    : cfg,
            "versao"    : VERSION,
        })

    def _exportar(self, p):
        cfg      = p.get("config", carregar_config())
        solucoes = p.get("solucoes", [])
        grade    = p.get("grade", {})
        tamanhos = p.get("tamanhos", [])
        ref      = p.get("referencia", "REF")
        lims_raw = p.get("limites", {})
        limites  = {c: {t: tuple(l) for t,l in ts.items()} for c,ts in lims_raw.items()}
        consumo  = float(cfg.get("consumo_peca_m", 1.0645))
        for s in solucoes: s["consumo"] = consumo
        pasta   = os.path.join(BASE_DIR, "dados", "resultados")
        caminho = exportar_xlsx(solucoes, grade, tamanhos, limites, cfg, ref, pasta)
        self._send(200, {"caminho": caminho})

    def _salvar_cores(self, p):
        salvar_cores_arquivo(p.get("cores", []))
        self._send(200, {"ok": True})

    def _salvar_params(self, p):
        # Salva apenas parÃ¢metros da UI (nÃ£o grade)
        params_atuais = carregar_params_salvos()
        params_atuais.update(p)
        salvar_params(params_atuais)
        self._send(200, {"ok": True})

    def _upload(self, p):
        nome     = p.get("nome", "arquivo.xlsx")
        conteudo = base64.b64decode(p.get("dados", ""))
        self._send(200, parse_arquivo(nome, conteudo))

    def _upload_imagem(self, p):
        cfg     = carregar_config()
        api_key = cfg.get("anthropic_api_key", "").strip()
        b64data = p.get("dados", "")
        mime    = p.get("mime", "image/jpeg")
        self._send(200, extrair_grade_de_imagem(b64data, mime, api_key))

    def _calcular_grupo(self, p):
        """Solver multi-ref: cada ref tem sua prÃ³pria composiÃ§Ã£o no enfesto combinado."""
        cfg = carregar_config()
        cfg["mesa_comprimento_m"]          = float(p.get("mesa", 10.0))
        cfg["limite_folhas_padrao"]        = int(p.get("max_folhas", 70))
        cfg["num_opcoes_saida"]            = int(p.get("num_opcoes", 2))
        cfg["desvio_absoluto_padrao"]      = int(p.get("tol_abs", 4))
        cfg["desvio_percentual_padrao"]    = int(p.get("tol_pct", 20))
        cfg["criterio_combinacao"]         = p.get("criterio", "MIN")
        cfg["peso_eficiencia_encaixe"]     = float(p.get("peso_enc", 6)) / 10.0
        cfg["peso_eficiencia_operacional"] = float(p.get("peso_op", 4)) / 10.0

        tamanhos   = p.get("tamanhos", ["PP","P","M","G"])
        timeout    = int(p.get("timeout", 120))
        refs_raw   = p.get("refs", [])
        referencia = p.get("referencia", "Grupo")
        regras     = p.get("regras_especiais", {})

        # Calcula limites para cada ref com seu prÃ³prio consumo
        refs_data = []
        for r in refs_raw:
            consumo = float(r.get("consumo", 1.0645))
            grade   = {cor: {t: int(v) for t, v in tms.items()}
                       for cor, tms in r.get("grade", {}).items()}
            cfg_r = dict(cfg)
            cfg_r["consumo_peca_m"] = consumo
            limites = calcular_limites_grade(grade, tamanhos, cfg_r, regras)
            refs_data.append({
                "nome"   : r.get("nome", "Ref"),
                "grade"  : grade,
                "consumo": consumo,
                "limites": limites,
            })

        # Salvar cores usadas
        todas_cores = list({c for r in refs_data for c in r["grade"]})
        salvar_cores_arquivo(todas_cores + carregar_cores_salvas())

        with _progresso_lock:
            _progresso_fila.clear()

        logs = []
        def cb(msg):
            logs.append(msg)
            _add_progresso(msg)

        solucoes = resolver_multiref(refs_data, tamanhos, cfg,
                                     callback=cb, timeout_s=timeout)

        if not solucoes:
            self._send(200, {"erro": "Nenhuma soluÃ§Ã£o combinada encontrada. Tente aumentar timeout ou tolerÃ¢ncia."})
            return

        def ser(o):
            if isinstance(o, dict): return {k: ser(v) for k, v in o.items()}
            if isinstance(o, list): return [ser(x) for x in o]
            if hasattr(o, "tolist"): return o.tolist()
            return o

        self._send(200, {
            "tipo"      : "multiref",
            "solucoes"  : ser(solucoes),
            "tamanhos"  : tamanhos,
            "referencia": referencia,
            "config"    : cfg,
            "versao"    : VERSION,
            "log"       : logs,
        })

    def _exportar_multiref(self, p):
        """Exporta resultado multi-ref combinado para Excel."""
        solucoes   = p.get("solucoes", [])
        tamanhos   = p.get("tamanhos", [])
        referencia = p.get("referencia", "Grupo")
        config     = p.get("config", carregar_config())
        pasta      = os.path.join(BASE_DIR, "dados", "resultados")
        caminho    = exportar_multiref_xlsx(solucoes, tamanhos, referencia, config, pasta)
        self._send(200, {"caminho": caminho})


    def _alocar_rolos(self, p):
        """Aloca rolos de tecido para um plano de corte."""
        cfg    = carregar_config()
        # ParÃ¢metros de alocaÃ§Ã£o (podem vir do frontend ou usar defaults do config)
        cfg["margem_seguranca_enfesto_m"] = float(p.get("margem", cfg.get("margem_seguranca_enfesto_m", 0.10)))
        cfg["folga_incerteza_pct"]        = float(p.get("folga_pct", cfg.get("folga_incerteza_pct", 0.03)))
        cfg["folga_incerteza_m"]          = float(p.get("folga_m",   cfg.get("folga_incerteza_m", 0.0)))
        cfg["ponta_minima_util_m"]        = float(p.get("ponta_min", cfg.get("ponta_minima_util_m", 0.5)))

        plano = p.get("plano", {})
        rolos = p.get("rolos", {})

        if not plano.get("mapas") or not plano.get("camadas"):
            self._send(400, {"erro": "Plano invalido: faltam campos 'mapas' ou 'camadas'."})
            return
        if not rolos:
            self._send(400, {"erro": "Nenhum rolo informado. Preencha os rolos por cor."})
            return

        resultado = alocar_rolos_fn(plano, rolos, cfg)
        self._send(200, resultado)

    def _baixar_arquivo(self):
        """Serve um arquivo de dados/resultados para download direto no browser."""
        from urllib.parse import parse_qs, urlparse as _up
        qs = parse_qs(_up(self.path).query)
        nome = (qs.get("arquivo") or [""])[0]
        # SeguranÃ§a: sÃ³ arquivos diretos em dados/resultados/ (sem path traversal)
        if not nome or "/" in nome or "\\" in nome or ".." in nome:
            self.send_response(400); self.end_headers(); return
        caminho = os.path.join(BASE_DIR, "dados", "resultados", nome)
        if not os.path.isfile(caminho):
            self.send_response(404); self.end_headers(); return
        with open(caminho, "rb") as f:
            data = f.read()
        ext = os.path.splitext(nome)[1].lower()
        ct = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == ".xlsx" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _exportar_alocacao(self, p):
        """Exporta resultado de alocacao de rolos para Excel."""
        resultado  = p.get("resultado", {})
        referencia = p.get("referencia", "REF")
        pasta      = os.path.join(BASE_DIR, "dados", "resultados")
        try:
            caminho = exportar_alocacao_xlsx(resultado, referencia, pasta)
            self._send(200, {"caminho": caminho})
        except Exception as e:
            self._send(500, {"erro": str(e)})

    def _importar_rolos(self, p):
        """Le PDF do ERP, extrai rolos e aplica mapeamento de cores."""
        import tempfile
        nome_arquivo  = p.get("nome", "arquivo.pdf")
        conteudo_b64  = p.get("dados", "")
        tipo_fonte    = p.get("tipo", None)

        if not conteudo_b64:
            self._send(400, {"erro": "Nenhum arquivo recebido."})
            return

        # Salva temporariamente para o parser
        import base64
        conteudo = base64.b64decode(conteudo_b64)
        ext = os.path.splitext(nome_arquivo)[1].lower() or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(conteudo)
            tmp_path = tmp.name

        try:
            fonte = obter_fonte_rolos(tipo=tipo_fonte, caminho_arquivo=tmp_path)
            registros, linhas_nao_parseadas = fonte.extrair(tmp_path)
        except ImportError as e:
            self._send(500, {"erro": str(e)})
            return
        except Exception as e:
            import traceback
            self._send(500, {"erro": str(e), "trace": traceback.format_exc()})
            return
        finally:
            try: os.unlink(tmp_path)
            except OSError: pass

        rolos_por_cor, cores_nao_reconhecidas = aplicar_mapa_cores(registros, MAPA_CORES_FILE)

        self._send(200, {
            "rolos_por_cor_comercial": rolos_por_cor,
            "cores_nao_reconhecidas" : cores_nao_reconhecidas,
            "linhas_nao_parseadas"   : linhas_nao_parseadas,
            "total_rolos"            : len(registros),
        })

    def _salvar_mapa_cor(self, p):
        """Grava associacao cor_fornecedor -> cor_comercial no mapa_cores.json."""
        cor_forn   = p.get("cor_fornecedor", "").strip()
        cor_com    = p.get("cor_comercial", "").strip()

        if not cor_forn or not cor_com:
            self._send(400, {"erro": "cor_fornecedor e cor_comercial sao obrigatorios."})
            return

        try:
            novo = adicionar_mapeamento_fn(cor_forn, cor_com, MAPA_CORES_FILE)
            self._send(200, {"ok": True, "novo": novo})
        except ValueError as e:
            self._send(409, {"erro": str(e)})

    def _checar_update(self):
        """Consulta GitHub Releases e retorna info de update disponivel."""
        cfg  = carregar_config()
        repo = cfg.get("github_repo", "")
        canal = cfg.get("update_canal", "estavel")

        if not repo or repo == "SEU_USUARIO/pcp-enfestos":
            self._send(200, {
                "versao_atual"        : VERSION,
                "versao_mais_recente" : None,
                "ha_update"           : False,
                "notas"               : "",
                "erro"                : "github_repo nao configurado em config.json.",
            })
            return

        resultado = checar_atualizacao_fn(repo, canal=canal)
        self._send(200, resultado)

    def _sinalizar_update(self, p):
        """Sinaliza update para ser aplicado na proxima abertura."""
        asset_url   = p.get("asset_url", "")
        versao_nova = p.get("versao_nova", "")
        notas       = p.get("notas", "")

        if not asset_url or not versao_nova:
            self._send(400, {"erro": "asset_url e versao_nova sao obrigatorios."})
            return

        try:
            sinalizar_update_fn(asset_url, versao_nova, notas)
            self._send(200, {"ok": True, "mensagem": f"Update {versao_nova} sera aplicado na proxima abertura."})
        except Exception as e:
            self._send(500, {"erro": str(e)})


_servidor_ref = None

def _encerrar_servidor():
    time.sleep(0.5)
    remover_pid()
    if _servidor_ref:
        _servidor_ref.shutdown()
    os._exit(0)


def _servidor_respondendo(porta):
    """Retorna True se hÃ¡ um servidor HTTP ativo respondendo na porta."""
    try:
        urllib.request.urlopen(f"http://localhost:{porta}/versao", timeout=2)
        return True
    except Exception:
        return False

def _matar_zumbi_porta(porta):
    """Encerra processos zumbi que estÃ£o bloqueando a porta."""
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for linha in r.stdout.splitlines():
            if f"127.0.0.1:{porta}" in linha and "LISTENING" in linha:
                partes = linha.split()
                pid = partes[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(["taskkill", "/f", "/pid", pid],
                                   capture_output=True, timeout=3)
                    print(f"Processo zumbi {pid} encerrado.")
    except Exception:
        pass

def main():
    global _servidor_ref
    _ensure_dados()
    porta = 5050
    try:
        servidor = HTTPServer(("localhost", porta), Handler)
    except OSError:
        if _servidor_respondendo(porta):
            # Servidor ativo â€” apenas abrir o browser
            webbrowser.open(f"http://localhost:{porta}")
        else:
            # Processo zumbi na porta â€” matar e tentar novamente
            _matar_zumbi_porta(porta)
            time.sleep(1)
            try:
                servidor = HTTPServer(("localhost", porta), Handler)
            except OSError:
                # Ainda em uso â€” abrir browser e sair
                webbrowser.open(f"http://localhost:{porta}")
                sys.exit(0)
            gravar_pid()
            _servidor_ref = servidor
            print(f"PCP Enfestos v{VERSION} â€” http://localhost:{porta} (retomado apos zumbi)")
            try:
                servidor.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                remover_pid()
            return
        sys.exit(0)
    gravar_pid()
    _servidor_ref = servidor
    print(f"PCP Enfestos v{VERSION} â€” http://localhost:{porta}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        remover_pid()

if __name__ == "__main__":
    main()

