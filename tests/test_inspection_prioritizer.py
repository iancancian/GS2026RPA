import csv
from pathlib import Path

import pytest

from bocadelobo import inspection, prioritizer
from bocadelobo.errors import InputDataError
from bocadelobo.models import AreaRisco

from conftest import HOJE


def _csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> Path:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecalho)
        w.writerows(linhas)
    return caminho


@pytest.fixture
def bueiros(tmp_path):
    arq = _csv(tmp_path / "b.csv", ["bueiro_id", "bairro", "logradouro", "latitude", "longitude"], [
        ["A", "Mooca", "Rua 1", -23.5, -46.6], ["B", "Mooca", "Rua 2", -23.5, -46.6],
        ["C", "Penha", "Rua 3", -23.5, -46.5], ["D", "Penha", "Rua 4", -23.5, -46.5],
    ])
    return inspection.carregar_bueiros(arq)


CAB = ["bueiro_id", "data_inspecao", "entupimento_pct", "tipo_residuo", "origem"]


def test_validacao_rejeita_linhas_invalidas_sem_interromper(tmp_path, bueiros):
    arq = _csv(tmp_path / "i.csv", CAB, [
        ["A", "2026-11-16", 80, "lixo", "visao"],
        ["B", "2026-11-16", "xx", "lixo", "visao"],
        ["B", "2026-11-16", 101, "lixo", "visao"],
        ["Z", "2026-11-16", 50, "lixo", "visao"],
        ["C", "16/11/2026", 50, "lixo", "visao"],
        ["C", "2027-01-01", 50, "lixo", "visao"],
        ["", "2026-11-16", 50, "lixo", "visao"],
    ])
    validas, rejeitadas = inspection.carregar_inspecoes(arq, bueiros, HOJE)
    assert list(validas) == ["A"]
    assert [r.motivo for r in rejeitadas] == [
        "entupimento_pct não numérico", "entupimento_pct fora de 0-100", "bueiro não cadastrado",
        "data de inspeção inválida", "data de inspeção no futuro", "bueiro_id vazio",
    ]


def test_duplicadas_mantem_a_mais_recente(tmp_path, bueiros):
    arq = _csv(tmp_path / "i.csv", CAB, [
        ["A", "2026-11-10", 20, "lixo", "v"], ["A", "2026-11-15", 90, "lixo", "v"], ["A", "2026-11-12", 30, "lixo", "v"],
    ])
    validas, rejeitadas = inspection.carregar_inspecoes(arq, bueiros, HOJE)
    assert validas["A"].entupimento_pct == 90
    assert len(rejeitadas) == 2


def test_arquivo_ausente_e_colunas_faltando(tmp_path, bueiros):
    with pytest.raises(InputDataError):
        inspection.carregar_inspecoes(tmp_path / "nao_existe.csv", bueiros, HOJE)
    ruim = _csv(tmp_path / "ruim.csv", ["bueiro_id"], [["A"]])
    with pytest.raises(InputDataError):
        inspection.carregar_inspecoes(ruim, bueiros, HOJE)


def test_classificacao_e_score(regras):
    assert prioritizer.classificar_entupimento(9, regras) == prioritizer.LIVRE
    assert prioritizer.classificar_entupimento(10, regras) == prioritizer.PARCIAL
    assert prioritizer.classificar_entupimento(80, regras) == prioritizer.CRITICO
    area = AreaRisco("X", 5, 10, True)
    assert prioritizer.calcular_score(100, area, regras) == 100.0  # 50+30+20+10 limitado a 100
    assert prioritizer.calcular_score(50, AreaRisco("X", 1, 0, False), regras) == 31.0


def test_lista_ordenada_capacidade_e_sem_inspecao(tmp_path, bueiros, regras):
    arq = _csv(tmp_path / "i.csv", CAB, [
        ["A", "2026-11-16", 75, "lixo", "v"],   # crítico em área de alto risco
        ["B", "2026-11-01", 45, "folhas", "v"],  # parcial e desatualizada
        ["C", "2026-11-16", 90, "lixo", "v"],   # crítico em área de risco menor
    ])
    inspecoes, _ = inspection.carregar_inspecoes(arq, bueiros, HOJE)
    areas = {"Mooca": AreaRisco("Mooca", 5, 9, True), "Penha": AreaRisco("Penha", 2, 1, False)}
    lista, sem = prioritizer.montar_lista(bueiros, inspecoes, areas, regras, HOJE)

    # B (parcial, mas em área de alto risco com hospital/escola) supera C (crítico em área de baixo risco)
    assert [p.bueiro_id for p in lista] == ["A", "B", "C"]
    assert [p.posicao for p in lista] == [1, 2, 3]
    assert lista[1].inspecao_desatualizada and not lista[0].inspecao_desatualizada
    assert sem == ["D"]
    assert all(p.dentro_da_capacidade for p in lista)
    assert [p.equipe for p in lista] == [1, 2, 1]


def test_capacidade_limita_bueiros_acionados(bueiros, regras, tmp_path):
    from dataclasses import replace

    pequena = replace(regras, capacidade=replace(regras.capacidade, equipes=1, bueiros_por_equipe_dia=1))
    arq = _csv(tmp_path / "i.csv", CAB, [["A", "2026-11-16", 80, "x", "v"], ["C", "2026-11-16", 90, "x", "v"]])
    inspecoes, _ = inspection.carregar_inspecoes(arq, bueiros, HOJE)
    lista, _ = prioritizer.montar_lista(bueiros, inspecoes, {}, pequena, HOJE)
    assert [p.dentro_da_capacidade for p in lista] == [True, False]
    assert lista[1].equipe is None
