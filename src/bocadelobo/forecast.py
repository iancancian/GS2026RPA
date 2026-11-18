"""Etapa 1: obtém e interpreta a previsão de chuva (Open-Meteo, sem chave de API)."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .config import Regras, Settings
from .errors import ForecastUnavailable
from .models import Previsao

log = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"
HORAS_JANELA = 24
MIN_HORAS_VALIDAS = 12
CACHE_NOME = "cache_previsao.json"

NENHUM, ATENCAO, ALERTA, EMERGENCIA = "NENHUM", "ATENCAO", "ALERTA", "EMERGENCIA"


def buscar_api(lat: float, lon: float, tentativas: int = 3, espera_base: float = 2.0, sleep=time.sleep) -> dict:
    """Consulta a API com retentativas e backoff exponencial."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation,precipitation_probability",
        "forecast_days": 2,
        "timezone": "auto",
    }
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            payload["hourly"]["time"]
            payload["hourly"]["precipitation"]
            return payload
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            ultimo_erro = exc
            log.warning("Previsão: tentativa %d/%d falhou (%s)", tentativa, tentativas, type(exc).__name__)
            if tentativa < tentativas:
                sleep(espera_base**tentativa)
    raise ForecastUnavailable("API de previsão indisponível após retentativas.") from ultimo_erro


def inicio_local(payload: dict, agora_utc: datetime) -> datetime:
    """Hora cheia local (no fuso da previsão) correspondente a `agora_utc`."""
    deslocamento = timedelta(seconds=payload.get("utc_offset_seconds", 0))
    return (agora_utc + deslocamento).replace(tzinfo=None, minute=0, second=0, microsecond=0)


def resumir(payload: dict, inicio: datetime | None, fonte: str, horas: int = HORAS_JANELA) -> Previsao:
    """Resume a janela de `horas` a partir de `inicio` (None = primeira hora do payload)."""
    try:
        tempos = [datetime.fromisoformat(t) for t in payload["hourly"]["time"]]
        chuva = payload["hourly"]["precipitation"]
        probs = payload["hourly"].get("precipitation_probability") or [0] * len(tempos)
    except (KeyError, TypeError, ValueError) as exc:
        raise ForecastUnavailable(f"Formato de previsão inválido: {exc}") from exc

    inicio = inicio or tempos[0]
    fim = inicio + timedelta(hours=horas)
    janela = [
        (c or 0.0, p or 0)
        for t, c, p in zip(tempos, chuva, probs)
        if inicio <= t < fim and c is not None
    ]
    if len(janela) < MIN_HORAS_VALIDAS:
        raise ForecastUnavailable(f"Previsão cobre apenas {len(janela)}h da janela de {horas}h.")
    return Previsao(
        inicio=inicio,
        horas=horas,
        chuva_mm=round(sum(c for c, _ in janela), 1),
        pico_horario_mm=round(max(c for c, _ in janela), 1),
        prob_max_pct=int(max(p for _, p in janela)),
        fonte=fonte,
    )


def classificar_chuva(previsao: Previsao, regras: Regras) -> str:
    """Regra de decisão central: a chuva prevista justifica acionar o fluxo?"""
    r = regras.chuva
    if previsao.prob_max_pct < r.prob_minima_pct:
        return NENHUM
    if previsao.chuva_mm >= r.emergencia_mm_24h:
        return EMERGENCIA
    if previsao.chuva_mm >= r.alerta_mm_24h:
        return ALERTA
    if previsao.chuva_mm >= r.limiar_mm_24h or previsao.pico_horario_mm >= r.pico_horario_mm:
        return ATENCAO
    return NENHUM


def _ler_cache(caminho: Path, agora_utc: datetime, max_horas: int) -> dict | None:
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
        buscado = datetime.fromisoformat(bruto["buscado_em"])
        if agora_utc - buscado <= timedelta(hours=max_horas):
            return bruto["payload"]
        log.warning("Cache de previsão expirado (%s).", bruto["buscado_em"])
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("Cache de previsão ausente ou inválido.")
    return None


def obter_previsao(
    settings: Settings,
    regras: Regras,
    agora_utc: datetime,
    arquivo: Path | None = None,
    buscar=buscar_api,
) -> Previsao:
    """API -> cache recente -> falha explícita. `arquivo` força uma previsão local (demo/testes)."""
    if arquivo:
        payload = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        return resumir(payload, None, f"arquivo:{Path(arquivo).name}")

    cache = settings.output_dir / CACHE_NOME
    try:
        payload = buscar(settings.latitude, settings.longitude)
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"buscado_em": agora_utc.isoformat(), "payload": payload}), encoding="utf-8"
        )
        return resumir(payload, inicio_local(payload, agora_utc), "open-meteo")
    except ForecastUnavailable:
        payload = _ler_cache(cache, agora_utc, regras.chuva.cache_max_horas)
        if payload is None:
            raise
        log.warning("Usando previsão em cache (degradação controlada).")
        return resumir(payload, inicio_local(payload, agora_utc), "cache")
