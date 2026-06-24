"""A3: o cabecalho das planilhas deve conter todos os parametros do calculo."""
import openpyxl
from exportar.export_xlsx import _resumo_parametros_txt, _aba_resumo_multiref


def _cfg():
    return {
        "consumo_peca_m": 1.0645,
        "mesa_comprimento_m": 10,
        "limite_folhas_padrao": 70,
        "desvio_absoluto_padrao": 4,
        "desvio_percentual_padrao": 20,
        "criterio_combinacao": "MIN",
        "num_opcoes_saida": 2,
        "timeout": 120,
        "tempo_processamento_s": 12.3,
        "versao": "2.10.1",
        "regras_especiais": {"G": {"hi": 0}},
    }


def test_resumo_parametros_txt_tem_todos_os_campos():
    s = _resumo_parametros_txt(_cfg())
    for marca in ["Consumo", "Mesa", "Folhas", "Tol. abs", "Tol. %",
                  "Criterio", "Opcoes", "Timeout", "Tempo real",
                  "Limites especiais", "Versao"]:
        assert marca in s, f"faltou '{marca}' em: {s}"
    assert "1.0645" in s
    assert "MIN" in s
    assert "120" in s
    assert "2.10.1" in s
    assert "G" in s  # limite especial


def test_resumo_parametros_txt_sem_campos_opcionais():
    """Sem timeout/tempo/regras nao deve quebrar."""
    s = _resumo_parametros_txt({"consumo_peca_m": 1.0, "mesa_comprimento_m": 10,
                                "limite_folhas_padrao": 70})
    assert "Consumo" in s
    assert "Timeout" in s          # mostra "—"
    assert "Limites especiais" in s  # mostra "nenhum"


def test_aba_resumo_multiref_cabecalho_tem_params():
    sol = {
        "n_mapas": 1,
        "refs_sol": [{"nome": "REF1", "mapas": []}],
        "comprimentos": [],
        "resumo": {"total_folhas": 10, "desvio_total": 2,
                   "comprimento_total": 50.0, "media_pecas_mapa": 6.0},
    }
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _aba_resumo_multiref(wb, [sol], "GrupoX", _cfg())
    a2 = wb["Resumo"]["A2"].value
    assert "Tol. abs" in a2 and "Criterio" in a2 and "Versao" in a2
