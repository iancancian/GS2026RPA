"""Etapa 2: leitura e validação dos dados de entrada (cadastro, áreas de risco, inspeções)."""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

from .errors import InputDataError
from .models import AreaRisco, Bueiro, Inspecao, Rejeicao

log = logging.getLogger(__name__)

COLUNAS_BUEIROS = {"bueiro_id", "bairro", "logradouro", "latitude", "longitude"}
COLUNAS_AREAS = {"bairro", "nivel_risco", "alagamentos_ultimo_ano", "equipamento_sensivel"}
COLUNAS_INSPECOES = {"bueiro_id", "data_inspecao", "entupimento_pct", "tipo_residuo", "origem"}
AREA_PADRAO_RISCO = 3


def _ler_csv(caminho: Path, colunas: set[str]) -> list[dict[str, str]]:
    try:
        with open(caminho, newline="", encoding="utf-8-sig") as f:
            leitor = csv.DictReader(f)
            faltando = colunas - set(leitor.fieldnames or [])
            if faltando:
                raise InputDataError(f"{caminho.name}: colunas ausentes {sorted(faltando)}")
            return list(leitor)
    except OSError as exc:
        raise InputDataError(f"Arquivo de entrada indisponível: {caminho.name} ({exc.strerror})") from exc


def carregar_bueiros(caminho: Path) -> dict[str, Bueiro]:
    bueiros: dict[str, Bueiro] = {}
    for n, linha in enumerate(_ler_csv(caminho, COLUNAS_BUEIROS), start=2):
        try:
            b = Bueiro(
                linha["bueiro_id"].strip(),
                linha["bairro"].strip(),
                linha["logradouro"].strip(),
                float(linha["latitude"]),
                float(linha["longitude"]),
            )
        except ValueError:
            log.warning("Cadastro: linha %d ignorada (coordenadas inválidas).", n)
            continue
        if b.bueiro_id and b.bueiro_id not in bueiros:
            bueiros[b.bueiro_id] = b
    if not bueiros:
        raise InputDataError(f"{caminho.name}: nenhum bueiro válido cadastrado.")
    return bueiros


def carregar_areas(caminho: Path) -> dict[str, AreaRisco]:
    areas: dict[str, AreaRisco] = {}
    for n, linha in enumerate(_ler_csv(caminho, COLUNAS_AREAS), start=2):
        try:
            nome = linha["bairro"].strip()
            areas[nome] = AreaRisco(
                nome,
                int(linha["nivel_risco"]),
                int(linha["alagamentos_ultimo_ano"]),
                linha["equipamento_sensivel"].strip().lower() in {"sim", "true", "1"},
            )
        except ValueError:
            log.warning("Áreas de risco: linha %d ignorada (valores inválidos).", n)
    return areas


def _validar_linha(linha: dict[str, str], bueiros: dict[str, Bueiro], hoje: date) -> Inspecao:
    """Levanta ValueError com o motivo da rejeição."""
    bueiro_id = (linha["bueiro_id"] or "").strip()
    if not bueiro_id:
        raise ValueError("bueiro_id vazio")
    if bueiro_id not in bueiros:
        raise ValueError("bueiro não cadastrado")
    try:
        data = date.fromisoformat((linha["data_inspecao"] or "").strip())
    except ValueError:
        raise ValueError("data de inspeção inválida") from None
    if data > hoje:
        raise ValueError("data de inspeção no futuro")
    try:
        pct = float(linha["entupimento_pct"])
    except (TypeError, ValueError):
        raise ValueError("entupimento_pct não numérico") from None
    if not 0 <= pct <= 100:
        raise ValueError("entupimento_pct fora de 0-100")
    return Inspecao(bueiro_id, data, pct, (linha["tipo_residuo"] or "").strip(), (linha["origem"] or "").strip())


def carregar_inspecoes(
    caminho: Path, bueiros: dict[str, Bueiro], hoje: date
) -> tuple[dict[str, Inspecao], list[Rejeicao]]:
    """Valida linha a linha, isola rejeitadas e mantém a inspeção mais recente por bueiro."""
    validas: dict[str, Inspecao] = {}
    rejeitadas: list[Rejeicao] = []
    for n, linha in enumerate(_ler_csv(caminho, COLUNAS_INSPECOES), start=2):
        try:
            insp = _validar_linha(linha, bueiros, hoje)
        except ValueError as exc:
            rejeitadas.append(Rejeicao(n, (linha.get("bueiro_id") or "").strip(), str(exc)))
            continue
        atual = validas.get(insp.bueiro_id)
        if atual and atual.data_inspecao > insp.data_inspecao:
            rejeitadas.append(Rejeicao(n, insp.bueiro_id, "duplicada: inspeção mais antiga descartada"))
            continue
        if atual:
            rejeitadas.append(Rejeicao(n, insp.bueiro_id, "duplicada: substitui inspeção anterior"))
        validas[insp.bueiro_id] = insp
    return validas, rejeitadas
