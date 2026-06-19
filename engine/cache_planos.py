"""
PCP Enfestos -- Cache de Planos + Aprendizado de Tempos
========================================================

Dois objetivos, um modulo:

1. CACHE DE RESULTADOS
   Um calculo de plano de corte e deterministico: a mesma grade, com os mesmos
   parametros, sempre produz o mesmo resultado. Recalcular do zero e desperdicio.
   Guardamos o resultado indexado por uma ASSINATURA (hash estavel da entrada).
   Recalculo identico -> resposta instantanea.

2. APRENDIZADO DE TEMPOS (ETA realista)
   O tempo que um solve leva depende da maquina e da complexidade do problema.
   Em vez de estimar o pior caso (que assusta o operador), registramos quanto
   cada classe de problema realmente levou e usamos a MEDIANA das ultimas
   medicoes como estimativa. A previsao melhora sozinha com o uso -- o sistema
   "aprende" o ritmo da maquina onde esta rodando.

Persistencia: arquivos JSON simples (sem banco). O acesso e serializado pelo
_calc_lock do servidor, entao nao ha concorrencia real de escrita.
"""

import os
import json
import hashlib


def assinatura(payload):
    """
    Hash estavel e independente da ordem das chaves para um payload de calculo.

    Serializa o payload como JSON canonico (chaves ordenadas) e aplica SHA-1.
    Dois payloads logicamente identicos -- ainda que com as chaves em ordem
    diferente -- produzem a mesma assinatura.
    """
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


def _carregar_json(caminho, padrao):
    """Le um JSON; devolve `padrao` se o arquivo nao existe ou esta corrompido."""
    if not caminho or not os.path.isfile(caminho):
        return padrao
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return padrao


def _salvar_json(caminho, dados):
    """Grava JSON de forma atomica (escreve em .tmp e renomeia)."""
    if not caminho:
        return
    pasta = os.path.dirname(caminho)
    if pasta and not os.path.isdir(pasta):
        os.makedirs(pasta, exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def _mediana(valores):
    n = len(valores)
    if n == 0:
        return None
    s = sorted(valores)
    m = n // 2
    if n % 2:
        return s[m]
    return (s[m - 1] + s[m]) / 2.0


class CachePlanos:
    """
    Cache persistente de resultados + tabela de tempos aprendidos.

    Args:
        caminho_cache:  arquivo JSON dos resultados (assinatura -> resultado).
        caminho_tempos: arquivo JSON das medicoes de tempo (chave -> [tempos]).
        max_tempos:     quantas medicoes recentes manter por chave (janela rolante).
    """

    def __init__(self, caminho_cache, caminho_tempos, max_tempos=20):
        self.caminho_cache = caminho_cache
        self.caminho_tempos = caminho_tempos
        self.max_tempos = max_tempos
        self._cache = _carregar_json(caminho_cache, {})
        self._tempos = _carregar_json(caminho_tempos, {})

    # ── Cache de resultados ────────────────────────────────────────────────
    def obter(self, assin):
        """Resultado guardado para esta assinatura, ou None se nunca calculado."""
        entrada = self._cache.get(assin)
        if entrada is None:
            return None
        return entrada.get("resultado")

    def guardar(self, assin, resultado, tempo_s=0.0):
        """Guarda o resultado de um calculo sob sua assinatura."""
        self._cache[assin] = {"resultado": resultado, "tempo_s": round(float(tempo_s), 3)}
        _salvar_json(self.caminho_cache, self._cache)

    # ── Aprendizado de tempos ──────────────────────────────────────────────
    def registrar_tempo(self, chave, tempo_s):
        """Registra quanto um solve da classe `chave` levou (janela rolante)."""
        lista = self._tempos.get(chave, [])
        lista.append(round(float(tempo_s), 3))
        if len(lista) > self.max_tempos:
            lista = lista[-self.max_tempos:]
        self._tempos[chave] = lista
        _salvar_json(self.caminho_tempos, self._tempos)

    def estimar_tempo(self, chave):
        """Mediana das medicoes recentes da classe `chave`, ou None se sem dados."""
        lista = self._tempos.get(chave)
        if not lista:
            return None
        return _mediana(lista)

    def estimativas(self):
        """Mapa {chave: mediana} de todas as classes ja medidas (para a ETA)."""
        return {k: _mediana(v) for k, v in self._tempos.items() if v}
