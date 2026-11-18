"""Configuração: regras de negócio (JSON versionado) e ambiente (variáveis de ambiente)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RegrasChuva:
    limiar_mm_24h: float
    alerta_mm_24h: float
    emergencia_mm_24h: float
    pico_horario_mm: float
    prob_minima_pct: int
    cache_max_horas: int


@dataclass(frozen=True)
class RegrasEntupimento:
    parcial_pct: float
    critico_pct: float
    validade_inspecao_dias: int


@dataclass(frozen=True)
class Pesos:
    entupimento: float
    risco_area: float
    historico: float
    bonus_equipamento_sensivel: float


@dataclass(frozen=True)
class Capacidade:
    equipes: int
    bueiros_por_equipe_dia: int

    @property
    def total(self) -> int:
        return self.equipes * self.bueiros_por_equipe_dia


@dataclass(frozen=True)
class Regras:
    versao: str
    chuva: RegrasChuva
    entupimento: RegrasEntupimento
    pesos: Pesos
    capacidade: Capacidade
    nivel_risco_minimo_moradores: int

    @classmethod
    def carregar(cls, caminho: Path) -> "Regras":
        try:
            bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
            regras = cls(
                versao=bruto["versao"],
                chuva=RegrasChuva(**bruto["chuva"]),
                entupimento=RegrasEntupimento(**bruto["entupimento"]),
                pesos=Pesos(**bruto["pesos"]),
                capacidade=Capacidade(**bruto["capacidade"]),
                nivel_risco_minimo_moradores=bruto["alerta_moradores"]["nivel_risco_minimo_area"],
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigError(f"Regras de negócio inválidas em {caminho}: {exc}") from exc
        regras._validar()
        return regras

    def _validar(self) -> None:
        c = self.chuva
        if not 0 < c.limiar_mm_24h <= c.alerta_mm_24h <= c.emergencia_mm_24h:
            raise ConfigError("Limiares de chuva devem ser crescentes (limiar <= alerta <= emergência).")
        e = self.entupimento
        if not 0 < e.parcial_pct < e.critico_pct <= 100:
            raise ConfigError("Faixas de entupimento inválidas (0 < parcial < crítico <= 100).")
        if self.capacidade.total <= 0:
            raise ConfigError("Capacidade diária de limpeza deve ser positiva.")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    output_dir: Path
    log_dir: Path
    regras_path: Path
    latitude: float
    longitude: float
    utc_offset_horas: int
    webhook_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        """Segredos (webhook) vêm apenas do ambiente; nunca do código ou do repositório."""
        env = os.environ
        try:
            return cls(
                data_dir=Path(env.get("BL_DATA_DIR", ROOT / "data")),
                output_dir=Path(env.get("BL_OUTPUT_DIR", ROOT / "output")),
                log_dir=Path(env.get("BL_LOG_DIR", ROOT / "logs")),
                regras_path=Path(env.get("BL_REGRAS", ROOT / "config" / "regras.json")),
                latitude=float(env.get("BL_LATITUDE", "-23.56")),
                longitude=float(env.get("BL_LONGITUDE", "-46.60")),
                utc_offset_horas=int(env.get("BL_UTC_OFFSET", "-3")),
                webhook_url=env.get("BL_WEBHOOK_URL") or None,
            )
        except ValueError as exc:
            raise ConfigError(f"Variável de ambiente numérica inválida: {exc}") from exc
