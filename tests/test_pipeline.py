import json
import sqlite3
import threading
import urllib.request
from dataclasses import replace

import pytest

from bocadelobo import pipeline
from bocadelobo.alerts import CanalArquivo
from bocadelobo.errors import ForecastUnavailable, InputDataError
from bocadelobo.mvp_api import criar_servidor

from conftest import AGORA, AMOSTRAS

TEMPESTADE = AMOSTRAS / "previsao_tempestade.json"
SECO = AMOSTRAS / "previsao_seco.json"


def _linhas_outbox(settings):
    caminho = settings.output_dir / pipeline.OUTBOX_NOME
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines()] if caminho.exists() else []


def test_tempestade_gera_lista_alertas_e_exportacoes(settings, regras):
    r = pipeline.executar(settings, regras, AGORA, TEMPESTADE)
    assert r.status == pipeline.STATUS_ACAO and r.nivel_chuva == "ALERTA"
    assert r.prioridades > 0 and r.rejeitados == 6 and r.sem_inspecao == 1
    assert r.envio.enviados > 0 and r.envio.falhas == 0

    dados = json.loads((settings.output_dir / "prioridades.json").read_text(encoding="utf-8"))
    scores = [p["score"] for p in dados["prioridades"]]
    assert scores == sorted(scores, reverse=True)
    assert all(p["human_approval_required"] is True for p in dados["prioridades"])
    audiencias = {a["audiencia"] for a in _linhas_outbox(settings)}
    assert audiencias == {"equipe_limpeza", "moradores"}
    assert (settings.output_dir / "lista_limpeza.csv").exists()
    assert (settings.output_dir / "rejeitados.csv").exists()


def test_dia_seco_nao_dispara_alertas(settings, regras):
    r = pipeline.executar(settings, regras, AGORA, SECO)
    assert r.status == pipeline.STATUS_SEM_ACAO and r.prioridades == 0
    assert _linhas_outbox(settings) == []
    dados = json.loads((settings.output_dir / "prioridades.json").read_text(encoding="utf-8"))
    assert dados["prioridades"] == []


def test_segunda_execucao_nao_duplica_alertas(settings, regras):
    primeira = pipeline.executar(settings, regras, AGORA, TEMPESTADE)
    n = len(_linhas_outbox(settings))
    segunda = pipeline.executar(settings, regras, AGORA, TEMPESTADE)
    assert segunda.envio.enviados == 0 and segunda.envio.duplicados == primeira.envio.enviados
    assert len(_linhas_outbox(settings)) == n


def test_dry_run_nao_grava_nem_envia(settings, regras):
    r = pipeline.executar(settings, regras, AGORA, TEMPESTADE, dry_run=True)
    assert r.execucao_id is None
    assert _linhas_outbox(settings) == []
    assert not (settings.output_dir / "prioridades.json").exists()


def test_webhook_exige_aprovacao_humana_explicita(settings):
    settings_com_webhook = replace(settings, webhook_url="https://webhook.example.test/secret")
    canais_padrao = pipeline.montar_canais(settings_com_webhook)
    canais_aprovados = pipeline.montar_canais(settings_com_webhook, aprovar_alertas=True)

    assert [canal.nome for canal in canais_padrao] == ["arquivo"]
    assert [canal.nome for canal in canais_aprovados] == ["arquivo", "webhook"]


def test_falha_de_canal_nao_impede_outros_e_nao_marca_como_enviado(settings, regras):
    class Quebrado:
        nome = "quebrado"

        def enviar(self, alerta):
            raise RuntimeError("canal fora")

    canais = [Quebrado(), CanalArquivo(settings.output_dir / pipeline.OUTBOX_NOME)]
    r = pipeline.executar(settings, regras, AGORA, TEMPESTADE, canais=canais)
    assert r.envio.falhas > 0 and r.envio.enviados > 0
    # na próxima execução somente o canal quebrado é reenviado
    r2 = pipeline.executar(settings, regras, AGORA, TEMPESTADE, canais=canais)
    assert r2.envio.falhas == r.envio.falhas and r2.envio.enviados == 0


def test_api_fora_sem_cache_registra_falha_e_avisa_operacao(settings, regras):
    def fora(lat, lon):
        raise ForecastUnavailable("fora")

    with pytest.raises(ForecastUnavailable):
        pipeline.executar(settings, regras, AGORA, buscar=fora)
    with sqlite3.connect(settings.output_dir / pipeline.DB_NOME) as conn:
        assert conn.execute("SELECT status FROM execucoes").fetchone()[0] == "FALHA_PREVISAO"
    assert [a["audiencia"] for a in _linhas_outbox(settings)] == ["operacao"]


def test_arquivo_de_inspecoes_ausente_e_falha_explicita(settings, regras, tmp_path):
    from dataclasses import replace

    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(InputDataError):
        pipeline.executar(replace(settings, data_dir=vazio), regras, AGORA, TEMPESTADE)
    with sqlite3.connect(settings.output_dir / pipeline.DB_NOME) as conn:
        assert conn.execute("SELECT status FROM execucoes").fetchone()[0] == "FALHA_DADOS"


def test_api_do_mvp_serve_resultado_do_robo(settings, regras):
    pipeline.executar(settings, regras, AGORA, TEMPESTADE)
    servidor = criar_servidor(settings.output_dir / pipeline.DB_NOME, porta=0)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{servidor.server_address[1]}"
        with urllib.request.urlopen(f"{base}/api/prioridades") as resp:
            corpo = json.load(resp)
        assert corpo["execucao"]["status"] == pipeline.STATUS_ACAO
        assert corpo["prioridades"][0]["posicao"] == 1
        assert corpo["prioridades"][0]["human_approval_required"] is True
        with urllib.request.urlopen(f"{base}/api/alertas") as resp:
            assert json.load(resp)["alertas"]
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(f"{base}/api/inexistente")
        assert erro.value.code == 404
    finally:
        servidor.shutdown()
        servidor.server_close()
