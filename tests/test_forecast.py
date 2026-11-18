import json
from datetime import timedelta

import pytest
import requests

from bocadelobo import forecast
from bocadelobo.errors import ForecastUnavailable

from conftest import AGORA, AMOSTRAS


def _payload(nome: str) -> dict:
    return json.loads((AMOSTRAS / f"previsao_{nome}.json").read_text(encoding="utf-8"))


def test_resumir_tempestade():
    p = forecast.resumir(_payload("tempestade"), None, "teste")
    assert p.chuva_mm == 73.0 and p.pico_horario_mm == 21.0 and p.prob_max_pct == 92


def test_classificar_niveis(regras):
    base = forecast.resumir(_payload("tempestade"), None, "t")
    assert forecast.classificar_chuva(base, regras) == forecast.ALERTA
    assert forecast.classificar_chuva(base.__class__(**{**base.__dict__, "chuva_mm": 120}), regras) == forecast.EMERGENCIA
    assert forecast.classificar_chuva(base.__class__(**{**base.__dict__, "chuva_mm": 35}), regras) == forecast.ATENCAO


def test_pico_horario_aciona_mesmo_com_total_baixo(regras):
    base = forecast.resumir(_payload("seco"), None, "t")
    pico = base.__class__(**{**base.__dict__, "pico_horario_mm": 25.0, "prob_max_pct": 80})
    assert forecast.classificar_chuva(pico, regras) == forecast.ATENCAO


def test_chuva_baixa_ou_improvavel_nao_aciona(regras):
    seco = forecast.resumir(_payload("seco"), None, "t")
    assert forecast.classificar_chuva(seco, regras) == forecast.NENHUM
    improvavel = seco.__class__(**{**seco.__dict__, "chuva_mm": 80, "prob_max_pct": 30})
    assert forecast.classificar_chuva(improvavel, regras) == forecast.NENHUM


def test_janela_insuficiente_falha():
    payload = _payload("tempestade")
    payload["hourly"] = {k: v[:5] for k, v in payload["hourly"].items()}
    with pytest.raises(ForecastUnavailable):
        forecast.resumir(payload, None, "t")


def test_inicio_local_aplica_fuso():
    inicio = forecast.inicio_local(_payload("seco"), AGORA)
    assert inicio.hour == 6 and inicio.day == 17


def test_api_com_retentativas_e_falha_final(monkeypatch):
    chamadas = []

    def falha(*a, **k):
        chamadas.append(1)
        raise requests.ConnectionError("fora do ar")

    monkeypatch.setattr(forecast.requests, "get", falha)
    with pytest.raises(ForecastUnavailable):
        forecast.buscar_api(0, 0, tentativas=3, sleep=lambda s: None)
    assert len(chamadas) == 3


def test_fallback_para_cache_e_falha_quando_expirado(settings, regras):
    ok = lambda lat, lon: _payload("tempestade")
    fora = lambda lat, lon: (_ for _ in ()).throw(ForecastUnavailable("fora"))

    forecast.obter_previsao(settings, regras, AGORA, buscar=ok)
    # o payload de amostra começa às 00:00 local; 3h depois ainda há >12h na janela
    p = forecast.obter_previsao(settings, regras, AGORA + timedelta(hours=1), buscar=fora)
    assert p.fonte == "cache"

    with pytest.raises(ForecastUnavailable):
        forecast.obter_previsao(settings, regras, AGORA + timedelta(hours=7), buscar=fora)
