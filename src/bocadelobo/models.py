"""Estruturas de dados do domínio."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Bueiro:
    bueiro_id: str
    bairro: str
    logradouro: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Inspecao:
    bueiro_id: str
    data_inspecao: date
    entupimento_pct: float
    tipo_residuo: str
    origem: str


@dataclass(frozen=True)
class AreaRisco:
    bairro: str
    nivel_risco: int
    alagamentos_ultimo_ano: int
    equipamento_sensivel: bool


@dataclass(frozen=True)
class Rejeicao:
    linha: int
    bueiro_id: str
    motivo: str


@dataclass(frozen=True)
class Previsao:
    inicio: datetime
    horas: int
    chuva_mm: float
    pico_horario_mm: float
    prob_max_pct: int
    fonte: str


@dataclass(frozen=True)
class Prioridade:
    posicao: int
    bueiro_id: str
    bairro: str
    logradouro: str
    latitude: float
    longitude: float
    entupimento_pct: float
    classe: str
    score: float
    tipo_residuo: str
    inspecao_desatualizada: bool
    dentro_da_capacidade: bool
    equipe: int | None


@dataclass(frozen=True)
class Alerta:
    chave: str
    audiencia: str
    bairro: str
    nivel: str
    mensagem: str
