import json
from pathlib import Path

import pytest

from bocadelobo import pipeline
from bocadelobo.errors import InputDataError
from bocadelobo.vision_input import carregar_fila_visao

from conftest import AGORA, AMOSTRAS, HOJE

FILA = AMOSTRAS / "vision_action_queue.json"
AREAS = AMOSTRAS / "areas_risco_visao.csv"


def test_contrato_real_da_visao_e_convertido_para_domínio_rpa():
    bueiros, inspecoes, areas, rejeitadas = carregar_fila_visao(FILA, AREAS, HOJE)

    assert len(bueiros) == 12
    assert len(inspecoes) == 9
    assert len(rejeitadas) == 4  # preserva os itens rejeitados pela própria Visão
    assert set(areas) == {
        "Setor baixo A (simulado)",
        "Setor medio B (simulado)",
        "Setor periferico C (simulado)",
    }
    assert areas["Setor periferico C (simulado)"].nivel_risco == 5
    assert areas["Setor medio B (simulado)"].nivel_risco == 2


def test_cobertura_visual_preserva_limites_da_visao():
    bueiros, inspecoes, _, _ = carregar_fila_visao(FILA, AREAS, HOJE)

    assert bueiros["BUEIRO-008"].bairro == "Setor periferico C (simulado)"
    assert inspecoes["BUEIRO-008"].entupimento_pct == 41.3
    assert inspecoes["BUEIRO-008"].origem == "visao_computacional"
    assert bueiros["BUEIRO-002"].bueiro_id not in inspecoes  # sem detecção: revisão manual


def test_fila_visao_malformada_falha_explicitamente(tmp_path: Path):
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"schema_version": "9.0", "items": []}), encoding="utf-8")
    with pytest.raises(InputDataError, match="schema_version"):
        carregar_fila_visao(queue, AREAS, HOJE)


def test_pipeline_consume_visao_e_emite_rascunhos_sem_endereco_ficticio(settings, regras):
    r = pipeline.executar(
        settings,
        regras,
        AGORA,
        AMOSTRAS / "previsao_tempestade.json",
        visao_action_queue=FILA,
        visao_areas=AREAS,
    )
    assert r.status == pipeline.STATUS_ACAO
    assert r.total_bueiros == 12
    assert r.rejeitados == 4
    assert r.sem_inspecao == 3

    saida = json.loads((settings.output_dir / "prioridades.json").read_text(encoding="utf-8"))
    assert all(p["logradouro"].startswith("Referência da inspeção:") for p in saida["prioridades"])
    assert all(p["human_approval_required"] is True for p in saida["prioridades"])
    alertas = [json.loads(l) for l in (settings.output_dir / pipeline.OUTBOX_NOME).read_text(encoding="utf-8").splitlines()]
    moradores = [a for a in alertas if a["audiencia"] == "moradores"]
    assert moradores
    assert all("RASCUNHO - NÃO PUBLICADO" in a["mensagem"] for a in moradores)
    assert all("localização exata não está disponível" in a["mensagem"] for a in moradores)
    assert all("Rua da Mooca" not in a["mensagem"] for a in moradores)


def test_areas_incompativeis_sao_rejeitadas_com_erro_claro(tmp_path: Path):
    fila = json.loads(FILA.read_text(encoding="utf-8"))
    caminho = tmp_path / "fila.json"
    caminho.write_text(json.dumps(fila), encoding="utf-8")
    area_ruim = tmp_path / "areas.csv"
    area_ruim.write_text("bairro,nivel_risco\n", encoding="utf-8")
    with pytest.raises(InputDataError, match="colunas ausentes"):
        carregar_fila_visao(caminho, area_ruim, HOJE)
