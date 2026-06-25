#!/usr/bin/env python3
"""
PCP Enfestos v2.10.1
Changelog:
  v2.10.1 - FIX CRITICO do auto-update: o PCP_Enfestos.vbs chamava main.py direto,
            pulando o launcher.py (onde mora o auto-update) -> a fabrica nunca
            atualizava sozinha. Agora o VBS chama launcher.py. Esta versao precisa
            chegar a fabrica UMA vez manualmente (recopiar a pasta / re-rodar INSTALAR
            ou editar a linha do VBS); dai em diante as atualizacoes fluem sozinhas.
  v2.10.0 - Multi-ref MUITO mais rapido (branch-and-bound): calcula individuais
            primeiro e limita a busca de cada grupo combinado a n_mapas < baseline
            (combinar so vale se reduzir enfestos). Caso real: 30min -> ~3min, mesma
            solucao otima. Export "todas as partes" num unico .zip (/exportar_particao)
            -- antes o navegador descartava downloads simultaneos e so 1 parte baixava.
            Alocacao de rolos agora abre apos calculo multi-ref e agrega TODOS os grupos
            (comp_camada_m explicito por mapa para enfestos combinados).
  v2.9.0 - Multi-ref: corrigido crash do solver combinado (total_pecas somava dict_values).
           Cache persistente de resultados (recalculo identico instantaneo) + aprendizado
           de tempos (ETA realista, melhora com o uso). Tetos de tempo adaptativos por
           complexidade (mantem 240xn como teto so ate aprender). Rota GET /aprendizado.
           Alocacao de rolos: parse unico de comprimentos (corrige deficit inflado) e
           reset que fecha o painel (fix no frontend interface.html).
  v2.8.0 - Alocador de rolos (FFD adaptado, margem por sub-enfesto, ponta como estoque).
           Import do controle de rolos do ERP Vexta (PDF) com mapeamento de cor.
           Auto-update via GitHub Releases.
  v2.7.0 - Multi-ref: testa TODOS os agrupamentos possíveis (pares, trios, todos juntos).
           Avalia todos os particionamentos e exibe a combinação ótima com tabela comparativa.
           Timeout individual max=180s; agrupamento = min(360, t×n_refs).
  v2.6.1 - Multi-ref: cada ref recebe timeout completo; combinado usa timeout/3.
  v2.6.0 - Zombie fix (netstat+taskkill). Cor salva sem prefixo REF| (split|[-1]).
  v2.4.0 - Solver: premissa principal = menos enfestos. hi=0 via check_viavel.
  v2.3.1 - Solver corrigido. Persistência de parâmetros e cores. Progresso real.
  v2.3.0 - Shutdown via botão, VBS robusto
  v2.1.0 - Múltiplas refs, upload, cores salvas
  v2.0.0 - Interface HTML, solver otimizado
"""

import json, os, sys, threading, webbrowser, base64, time, signal, subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

VERSION      = "2.10.1"
CORES_FILE        = os.path.join(BASE_DIR, "dados", "cores_salvas.json")
PARAMS_FILE       = os.path.join(BASE_DIR, "dados", "parametros_salvos.json")
PID_FILE          = os.path.join(BASE_DIR, "dados", "servidor.pid")
MAPA_CORES_FILE   = os.path.join(BASE_DIR, "dados", "mapa_cores.json")
HISTORICO_FILE    = os.path.join(BASE_DIR, "dados", "historico_solucoes.json")
CACHE_FILE        = os.path.join(BASE_DIR, "dados", "cache_planos.json")
TEMPOS_FILE       = os.path.join(BASE_DIR, "dados", "tempos_aprendidos.json")

# Importações lazy para evitar erro de startup
def _importar():
    global resolver, calcular_limites_grade, exportar_xlsx, parse_arquivo, extrair_grade_de_imagem
    global resolver_multiref, exportar_multiref_xlsx
    global alocar_rolos_fn, exportar_alocacao_xlsx
    global obter_fonte_rolos, aplicar_mapa_cores, resolver_cor_fn, adicionar_mapeamento_fn
    global carregar_mapa_cores, salvar_mapa_cores_fn
    global checar_atualizacao_fn, sinalizar_update_fn
    global CachePlanos, assinatura_calc
    from engine.solver              import resolver
    from engine.cache_planos        import CachePlanos, assinatura as assinatura_calc
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

# Cache persistente de resultados + tempos aprendidos (ETA realista).
# Recalculo identico -> instantaneo; previsao de tempo melhora com o uso.
_CACHE = CachePlanos(CACHE_FILE, TEMPOS_FILE)


def _bucket_single(grade):
    """Chave de complexidade para aprender o tempo de um calculo de 1 referencia."""
    return f"indiv:{len(grade)}c"


def _bucket_grupo(n_refs, n_cores):
    """Chave de complexidade para aprender o tempo de um calculo combinado."""
    return f"grupo:{n_refs}r:{n_cores}c"


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


# ── Aprendizado histórico ──────────────────────────────────────────────────

def _fingerprint_grade(grade_total: dict, tamanhos: list) -> str:
    """Identifica uma grade pela distribuição proporcional de tamanhos (±5%)."""
    total = sum(grade_total.get(t, 0) for t in tamanhos)
    if total == 0:
        return "vazio"
    partes = []
    for t in tamanhos:
        pct = round(grade_total.get(t, 0) / total * 20) * 5  # arredonda para múltiplo de 5%
        if pct > 0:
            partes.append(f"{t}={pct}")
    return ",".join(partes)

def carregar_historico(fingerprint: str) -> list:
    """Retorna os mapas históricos da melhor solução para esta grade."""
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
    """Salva ou atualiza a melhor solução para esta grade no histórico."""
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

    # Só atualiza se esta solução for melhor (menor desvio)
    if desvio < desvio_atual:
        historico[fingerprint] = {
            "mapas": mapas_vencedores,
            "desvio": desvio,
            "n_mapas": len(mapas_vencedores),
        }
        with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)

# ──────────────────────────────────────────────────────────────────────────

def remover_pid():
    try: os.remove(PID_FILE)
    except: pass


# Progresso por job: cada aba (page load) tem seu JOB_ID; mensagens nao se misturam.
_progressos = {}                 # job_id -> list[str]
_progresso_lock = threading.Lock()
_PROGRESSO_MAX_JOBS = 50          # teto p/ nao crescer sem limite (GC simples)

# Serializa cálculos: o solver usa estado global compartilhado (mapas históricos
# injetados + atributos de retomada na função resolver). ThreadingHTTPServer atende
# requisições concorrentes, então sem este lock dois cálculos simultâneos corromperiam
# o estado um do outro. Mantido durante todo o cálculo (single-user desktop).
_calc_lock = threading.Lock()

def _reset_job(job_id):
    with _progresso_lock:
        _progressos[job_id] = []
        if len(_progressos) > _PROGRESSO_MAX_JOBS:
            for k in list(_progressos.keys())[:-_PROGRESSO_MAX_JOBS]:
                _progressos.pop(k, None)

def _add_progresso(job_id, msg):
    with _progresso_lock:
        _progressos.setdefault(job_id, []).append(msg)

def _drain_job(job_id):
    with _progresso_lock:
        msgs = _progressos.get(job_id, [])
        _progressos[job_id] = []
        return msgs


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
            from urllib.parse import parse_qs
            job = (parse_qs(urlparse(self.path).query).get("job") or [""])[0]
            self._send(200, {"msgs": _drain_job(job) if job else []})
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
        elif path == "/aprendizado":
            # Tempos medianos aprendidos por classe de problema (para a ETA realista).
            self._send(200, {"tempos": _CACHE.estimativas()})
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
            elif path == "/exportar_particao":  self._exportar_particao(json.loads(body))
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

        tamanhos   = p.get("tamanhos", ["PP","P","M","G"])
        grade      = {cor: {t: int(v) for t,v in tms.items()}
                      for cor, tms in p.get("grade", {}).items()}
        regras      = p.get("regras_especiais", {})
        referencia  = p.get("referencia", "REF")
        timeout     = int(p.get("timeout", 120))
        min_n_mapas = int(p.get("min_n_mapas", 1))
        skip_combos = int(p.get("skip_combos", 0))
        job_id      = p.get("job_id", "default")

        # Salvar parâmetros usados para próxima sessão
        salvar_params({
            "consumo": p.get("consumo", 1.0645),
            "mesa": p.get("mesa", 10.0),
            "max_folhas": p.get("max_folhas", 70),
            "num_opcoes": p.get("num_opcoes", 2),
            "tol_abs": p.get("tol_abs", 4),
            "tol_pct": p.get("tol_pct", 20),
            "criterio": p.get("criterio", "MIN"),
            "timeout": timeout,
            "tamanhos": tamanhos,
            "regras_especiais": regras,
        })

        # Salvar cores usadas (extrair só a cor, sem prefixo de referência "Ref|Cor")
        cores_brutas = list(grade.keys())
        cores_limpas = list({c.split("|")[-1] for c in cores_brutas})
        cores_usadas = cores_limpas + carregar_cores_salvas()
        salvar_cores_arquivo(cores_usadas)

        limites  = calcular_limites_grade(grade, tamanhos, cfg, regras)

        # ── Cache: recalculo identico e instantaneo ──────────────────────────
        # Assinatura = definicao do problema (sem timeout, que so muda o orcamento
        # de busca). So usa cache em calculo fresco (nao em retomada via "Continuar").
        usa_cache = (min_n_mapas == 1 and skip_combos == 0)
        sig = assinatura_calc({
            "tipo": "single", "grade": grade, "consumo": cfg["consumo_peca_m"],
            "mesa": cfg["mesa_comprimento_m"], "max_folhas": cfg["limite_folhas_padrao"],
            "num_opcoes": cfg["num_opcoes_saida"], "tol_abs": cfg["desvio_absoluto_padrao"],
            "tol_pct": cfg["desvio_percentual_padrao"], "criterio": cfg["criterio_combinacao"],
            "tamanhos": tamanhos, "regras": regras,
        })
        if usa_cache:
            hit = _CACHE.obter(sig)
            if hit is not None:
                self._send(200, {**hit, "referencia": referencia, "cache": True,
                                 "log": ["Cache: resultado identico reaproveitado (instantaneo)."]})
                return

        # Calcular grade total e fingerprint para o histórico
        grade_total = {t: sum(grade[c].get(t, 0) for c in grade) for t in tamanhos}
        fp = _fingerprint_grade(grade_total, tamanhos)

        from engine import mapas as _mapas_mod
        historicos = carregar_historico(fp)

        _reset_job(job_id)

        logs     = []
        def cb(msg):
            logs.append(msg)
            _add_progresso(job_id, msg)

        # Cálculo sob lock: injeção de históricos + resolver + leitura dos atributos
        # de retomada formam uma seção crítica (estado global compartilhado).
        _t0 = time.time()
        if not _calc_lock.acquire(blocking=False):
            _add_progresso(job_id, "Aguardando outro calculo terminar (na fila)...")
            _calc_lock.acquire()
        try:
            _mapas_mod._mapas_historicos_injetar = historicos
            try:
                solucoes = resolver(grade, tamanhos, limites, cfg,
                                    callback_progresso=cb, timeout_s=timeout,
                                    min_n_mapas=min_n_mapas, skip_combos=skip_combos)
            finally:
                _mapas_mod._mapas_historicos_injetar = []  # sempre limpar após uso
            r_niveis = getattr(resolver, '_niveis_esgotados', [])
            r_prox   = getattr(resolver, '_proximo_n', 1)
            r_skip   = getattr(resolver, '_skip_combos', 0)
        finally:
            _calc_lock.release()
        _elapsed = time.time() - _t0
        # Aprende o tempo real SO de buscas que terminaram (r_skip==0 = nao cortada
        # por timeout). Tempo de busca cortada enviesaria a mediana para baixo e o
        # teto adaptativo passaria a cortar buscas boas antes da hora.
        if usa_cache and r_skip == 0:
            _CACHE.registrar_tempo(_bucket_single(grade), _elapsed)

        if not solucoes:
            self._send(200, {
                "erro": "Nenhuma solução encontrada. Tente aumentar tolerância ou timeout.",
                "niveis_esgotados": r_niveis,
                "proximo_n": r_prox,
                "skip_combos": r_skip,
                "log": logs,
            })
            return

        # Salvar melhor solução no histórico (aprendizado)
        melhor = solucoes[0]
        try:
            mapas_vencedores = melhor.get("mapas") or []
            # mapas pode ser lista de dicts ou lista de dicts com valores int
            desvio_melhor    = int(melhor.get("resumo", {}).get("desvio_total", 9999))
            if mapas_vencedores:
                salvar_historico(fp, mapas_vencedores, desvio_melhor)
        except Exception:
            pass  # nunca bloquear o resultado por falha no histórico

        def ser(o):
            if isinstance(o, dict): return {k: ser(v) for k,v in o.items()}
            if isinstance(o, list): return [ser(x) for x in o]
            if hasattr(o, "tolist"): return o.tolist()
            return o

        resp = {
            "solucoes"  : ser(solucoes),
            "tamanhos"  : tamanhos,
            "grade"     : grade,
            "limites"   : {c: {t: list(l) for t,l in ts.items()} for c,ts in limites.items()},
            "config"    : cfg,
            "versao"    : VERSION,
            "regras_especiais": regras,
        }
        # Guarda no cache apenas se a busca foi completa (r_skip==0 = nao cortada
        # por timeout no meio de um nivel). Resultado parcial nunca e cacheado,
        # para que "Continuar" com mais tempo possa melhora-lo.
        if usa_cache and r_skip == 0:
            _CACHE.guardar(sig, resp, _elapsed)
        self._send(200, {**resp, "referencia": referencia, "log": logs, "tempo_s": round(_elapsed, 2)})

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
        cfg["versao"]                = VERSION
        cfg["timeout"]               = p.get("timeout")
        cfg["tempo_processamento_s"] = p.get("tempo_s")
        cfg["regras_especiais"]      = p.get("regras_especiais", cfg.get("regras_especiais"))
        caminho = exportar_xlsx(solucoes, grade, tamanhos, limites, cfg, ref, pasta)
        self._send(200, {"caminho": caminho, "nome": os.path.basename(caminho)})

    def _salvar_cores(self, p):
        salvar_cores_arquivo(p.get("cores", []))
        self._send(200, {"ok": True})

    def _salvar_params(self, p):
        # Salva apenas parâmetros da UI (não grade)
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
        """Solver multi-ref: cada ref tem sua própria composição no enfesto combinado."""
        cfg = carregar_config()
        cfg["mesa_comprimento_m"]          = float(p.get("mesa", 10.0))
        cfg["limite_folhas_padrao"]        = int(p.get("max_folhas", 70))
        cfg["num_opcoes_saida"]            = int(p.get("num_opcoes", 2))
        cfg["desvio_absoluto_padrao"]      = int(p.get("tol_abs", 4))
        cfg["desvio_percentual_padrao"]    = int(p.get("tol_pct", 20))
        cfg["criterio_combinacao"]         = p.get("criterio", "MIN")

        tamanhos    = p.get("tamanhos", ["PP","P","M","G"])
        timeout     = int(p.get("timeout", 120))
        n_mapas_max = int(p.get("n_mapas_max", 7))   # branch-and-bound: teto de enfestos
        refs_raw    = p.get("refs", [])
        referencia  = p.get("referencia", "Grupo")
        regras      = p.get("regras_especiais", {})
        job_id      = p.get("job_id", "default")

        # Calcula limites para cada ref com seu próprio consumo
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

        # ── Cache: agrupamento identico e instantaneo ───────────────────────
        sig = assinatura_calc({
            "tipo": "multiref",
            "refs": [{"grade": r["grade"], "consumo": r["consumo"]} for r in refs_data],
            "mesa": cfg["mesa_comprimento_m"], "max_folhas": cfg["limite_folhas_padrao"],
            "num_opcoes": cfg["num_opcoes_saida"], "tol_abs": cfg["desvio_absoluto_padrao"],
            "tol_pct": cfg["desvio_percentual_padrao"], "criterio": cfg["criterio_combinacao"],
            "tamanhos": tamanhos, "regras": regras, "n_mapas_max": n_mapas_max,
        })
        hit = _CACHE.obter(sig)
        if hit is not None:
            self._send(200, {**hit, "referencia": referencia, "cache": True,
                             "log": ["Cache: agrupamento identico reaproveitado (instantaneo)."]})
            return
        n_cores = sum(len(r["grade"]) for r in refs_data)

        _reset_job(job_id)

        logs = []
        def cb(msg):
            logs.append(msg)
            _add_progresso(job_id, msg)

        # Mesmo lock do cálculo single-ref: serializa para não interleavar progresso
        # nem competir pelo estado global compartilhado do solver.
        _t0 = time.time()
        if not _calc_lock.acquire(blocking=False):
            _add_progresso(job_id, "Aguardando outro calculo terminar (na fila)...")
            _calc_lock.acquire()
        try:
            solucoes = resolver_multiref(refs_data, tamanhos, cfg,
                                         callback=cb, timeout_s=timeout,
                                         n_mapas_max=n_mapas_max)
            # Sinal exato do solver: a busca convergiu ou foi cortada pelo timeout?
            # (mesma estrategia do single-ref, que usa r_skip==0 -- evita vies na ETA)
            _convergiu = getattr(resolver_multiref, '_convergiu', True)
        finally:
            _calc_lock.release()
        _elapsed = time.time() - _t0
        if _convergiu:
            _CACHE.registrar_tempo(_bucket_grupo(len(refs_data), n_cores), _elapsed)

        if not solucoes:
            self._send(200, {"erro": "Nenhuma solução combinada encontrada. Tente aumentar timeout ou tolerância.",
                             "tempo_s": round(_elapsed, 2)})
            return

        def ser(o):
            if isinstance(o, dict): return {k: ser(v) for k, v in o.items()}
            if isinstance(o, list): return [ser(x) for x in o]
            if hasattr(o, "tolist"): return o.tolist()
            return o

        resp = {
            "tipo"      : "multiref",
            "solucoes"  : ser(solucoes),
            "tamanhos"  : tamanhos,
            "config"    : cfg,
            "regras_especiais": regras,
            "versao"    : VERSION,
        }
        # Cacheia apenas quando convergiu antes do teto de tempo. Se usou quase
        # todo o orcamento, a busca pode ter sido cortada -> nao congela parcial.
        if _convergiu:
            _CACHE.guardar(sig, resp, _elapsed)
        self._send(200, {**resp, "referencia": referencia, "log": logs, "tempo_s": round(_elapsed, 2)})

    def _exportar_particao(self, p):
        """Exporta TODAS as partes do melhor agrupamento num unico .zip.

        Evita o problema do navegador descartar downloads simultaneos: gera uma
        planilha por grupo (single ou combinado) e empacota tudo em um zip so.
        """
        import zipfile
        grupos     = p.get("grupos", [])
        referencia = p.get("referencia", "plano_completo")
        pasta      = os.path.join(BASE_DIR, "dados", "resultados")
        os.makedirs(pasta, exist_ok=True)

        arquivos = []
        for g in grupos:
            data = g.get("data", {})
            cfg  = data.get("config", carregar_config())
            cfg["versao"]                = VERSION
            cfg["timeout"]               = data.get("timeout")
            cfg["tempo_processamento_s"] = data.get("tempo_s")
            cfg["regras_especiais"]      = data.get("regras_especiais", cfg.get("regras_especiais"))
            sols = data.get("solucoes", [])
            tams = data.get("tamanhos", [])
            ref  = data.get("referencia", referencia)
            if not sols:
                continue
            if g.get("tipo") == "multiref":
                arquivos.append(exportar_multiref_xlsx(sols, tams, ref, cfg, pasta))
            else:
                grade    = data.get("grade", {})
                lims_raw = data.get("limites", {})
                limites  = {c: {t: tuple(l) for t, l in ts.items()} for c, ts in lims_raw.items()}
                consumo  = float(cfg.get("consumo_peca_m", 1.0645))
                for s in sols:
                    s["consumo"] = consumo
                arquivos.append(exportar_xlsx(sols, grade, tams, limites, cfg, ref, pasta))

        if not arquivos:
            self._send(200, {"erro": "Nenhuma parte para exportar."})
            return

        # Uma unica parte -> devolve o proprio xlsx (sem zipar).
        if len(arquivos) == 1:
            self._send(200, {"caminho": arquivos[0], "nome": os.path.basename(arquivos[0])})
            return

        ts       = time.strftime("%Y%m%d_%H%M%S")
        zip_nome = f"plano_completo_{referencia.replace(' ', '_').replace('/', '-')[:40]}_{ts}.zip"
        zip_cam  = os.path.join(pasta, zip_nome)
        with zipfile.ZipFile(zip_cam, "w", zipfile.ZIP_DEFLATED) as z:
            for a in arquivos:
                z.write(a, os.path.basename(a))
        self._send(200, {"caminho": zip_cam, "nome": zip_nome})

    def _exportar_multiref(self, p):
        """Exporta resultado multi-ref combinado para Excel."""
        solucoes   = p.get("solucoes", [])
        tamanhos   = p.get("tamanhos", [])
        referencia = p.get("referencia", "Grupo")
        config     = p.get("config", carregar_config())
        pasta      = os.path.join(BASE_DIR, "dados", "resultados")
        config["versao"]                = VERSION
        config["timeout"]               = p.get("timeout")
        config["tempo_processamento_s"] = p.get("tempo_s")
        caminho    = exportar_multiref_xlsx(solucoes, tamanhos, referencia, config, pasta)
        self._send(200, {"caminho": caminho, "nome": os.path.basename(caminho)})


    def _alocar_rolos(self, p):
        """Aloca rolos de tecido para um plano de corte."""
        cfg    = carregar_config()
        # Parâmetros de alocação (podem vir do frontend ou usar defaults do config)
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
        # Segurança: só arquivos diretos em dados/resultados/ (sem path traversal)
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
            params  = {**(resultado.get("params") or {}), "versao": VERSION}
            caminho = exportar_alocacao_xlsx(resultado, referencia, pasta, params)
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
    """Retorna True se há um servidor HTTP ativo respondendo na porta."""
    try:
        urllib.request.urlopen(f"http://localhost:{porta}/versao", timeout=2)
        return True
    except Exception:
        return False

def _matar_zumbi_porta(porta):
    """Encerra processos zumbi que estão bloqueando a porta."""
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
        servidor = ThreadingHTTPServer(("localhost", porta), Handler)
    except OSError:
        if _servidor_respondendo(porta):
            # Servidor ativo — apenas abrir o browser
            webbrowser.open(f"http://localhost:{porta}")
        else:
            # Processo zumbi na porta — matar e tentar novamente
            _matar_zumbi_porta(porta)
            time.sleep(1)
            try:
                servidor = ThreadingHTTPServer(("localhost", porta), Handler)
            except OSError:
                # Ainda em uso — abrir browser e sair
                webbrowser.open(f"http://localhost:{porta}")
                sys.exit(0)
            gravar_pid()
            _servidor_ref = servidor
            print(f"PCP Enfestos v{VERSION} — http://localhost:{porta} (retomado apos zumbi)")
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
    print(f"PCP Enfestos v{VERSION} — http://localhost:{porta}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        remover_pid()

if __name__ == "__main__":
    main()
