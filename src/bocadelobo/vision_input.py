"""Adaptador do contrato de saída da disciplina Applied Computer Vision."""

from __future__ import annotations

import csv
import json
import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .errors import InputDataError
from .models import AreaRisco, Bueiro, Inspecao, Rejeicao

log = logging.getLogger(__name__)

COLUNAS_AREAS_VISAO = {"area_id", "area_name", "high_risk", "latitude", "longitude"}
VERDADEIRO = {"true", "1", "sim", "yes"}
FALSO = {"false", "0", "nao", "não", "no"}
SCHEMA_VISAO = "1.0"
NIVEL_ALTO = 5
NIVEL_PADRAO = 2
COBERTURA_PARCIAL_MINIMA = 10.0


def carregar_areas_visao(caminho: Path) -> tuple[dict[str, AreaRisco], dict[str, tuple[float, float]]]:
    """Converte o contrato de áreas da Visão em risco e coordenadas consumidos pelo RPA.

    O contrato atual só fornece risco binário; alto risco vira nível 5 e demais áreas,
    nível 2. Histórico de alagamento e equipamento sensível não são inferidos.
    """
    areas: dict[str, AreaRisco] = {}
    coordenadas: dict[str, tuple[float, float]] = {}
    try:
        with open(caminho, newline="", encoding="utf-8-sig") as arquivo:
            leitor = csv.DictReader(arquivo)
            faltando = COLUNAS_AREAS_VISAO - set(leitor.fieldnames or [])
            if faltando:
                raise InputDataError(f"{caminho.name}: colunas ausentes {sorted(faltando)}")
            for linha_num, linha in enumerate(leitor, start=2):
                area_id = (linha.get("area_id") or "").strip()
                risco = (linha.get("high_risk") or "").strip().lower()
                try:
                    lat, lon = float(linha["latitude"]), float(linha["longitude"])
                except (TypeError, ValueError):
                    log.warning("Área da Visão linha %d ignorada: coordenadas inválidas.", linha_num)
                    continue
                if (
                    not area_id
                    or risco not in VERDADEIRO | FALSO
                    or not math.isfinite(lat)
                    or not math.isfinite(lon)
                    or not -90 <= lat <= 90
                    or not -180 <= lon <= 180
                ):
                    log.warning("Área da Visão linha %d ignorada: registro inválido.", linha_num)
                    continue
                if area_id in areas:
                    log.warning("Área da Visão linha %d ignorada: id duplicado %s.", linha_num, area_id)
                    continue
                alto_risco = risco in VERDADEIRO
                nome = (linha.get("area_name") or area_id).strip()
                areas[area_id] = AreaRisco(nome, NIVEL_ALTO if alto_risco else NIVEL_PADRAO, 0, False)
                coordenadas[area_id] = (lat, lon)
    except InputDataError:
        raise
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        raise InputDataError(f"Arquivo de áreas da Visão indisponível: {caminho.name} ({exc})") from exc
    if not areas:
        raise InputDataError(f"{caminho.name}: nenhuma área válida.")
    return areas, coordenadas


def carregar_fila_visao(
    caminho: Path,
    caminho_areas: Path,
    hoje: date,
) -> tuple[dict[str, Bueiro], dict[str, Inspecao], dict[str, AreaRisco], list[Rejeicao]]:
    """Lê action_queue.json da Visão e converte inspeções válidas para o domínio do RPA."""
    areas_por_id, coordenadas = carregar_areas_visao(caminho_areas)
    try:
        payload: Any = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"Fila da Visão ilegível: {caminho.name} ({exc})") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VISAO:
        raise InputDataError(f"{caminho.name}: schema_version da Visão ausente ou incompatível.")
    if not isinstance(payload.get("items"), list):
        raise InputDataError(f"{caminho.name}: campo items deve ser uma lista.")

    bueiros: dict[str, Bueiro] = {}
    inspecoes: dict[str, Inspecao] = {}
    rejeitadas: list[Rejeicao] = []
    rejeicoes_anteriores = payload.get("rejected", [])
    if isinstance(rejeicoes_anteriores, list):
        for item in rejeicoes_anteriores:
            if not isinstance(item, dict):
                continue
            try:
                linha = int(item.get("line", 0))
            except (TypeError, ValueError):
                linha = 0
            motivo = str(item.get("reason") or "rejeitada pelo componente de Visão")
            detalhe = str(item.get("detail") or "")
            rejeitadas.append(
                Rejeicao(linha, str(item.get("asset_id") or ""), f"Visão: {motivo}{': ' + detalhe if detalhe else ''}")
            )

    for posicao, item in enumerate(payload["items"], start=1):
        if not isinstance(item, dict):
            rejeitadas.append(Rejeicao(posicao, "", "Visão: item não é um objeto"))
            continue
        asset_id = str(item.get("asset_id") or "").strip()
        area_id = str(item.get("area_id") or "").strip()
        imagem = str(item.get("image_file") or "").strip()
        assessment = item.get("assessment")
        if not asset_id or not area_id or area_id not in areas_por_id or not isinstance(assessment, dict):
            rejeitadas.append(Rejeicao(posicao, asset_id, "Visão: identificador, área ou assessment inválido"))
            continue
        if assessment.get("human_approval_required") is not True:
            rejeitadas.append(Rejeicao(posicao, asset_id, "Visão: inspeção sem aprovação humana obrigatória"))
            continue
        if asset_id in bueiros:
            rejeitadas.append(Rejeicao(posicao, asset_id, "Visão: ativo duplicado na fila"))
            continue

        lat, lon = coordenadas[area_id]
        area = areas_por_id[area_id]
        bueiros[asset_id] = Bueiro(
            asset_id,
            area.bairro,
            f"Referência da inspeção: {imagem or asset_id}",
            lat,
            lon,
        )

        drains = assessment.get("drains")
        if not isinstance(drains, list) or not drains:
            # Sem bueiro detectado, o classificador não pode concluir que está livre.
            continue
        validadas: list[tuple[float, dict]] = []
        for drain in drains:
            if not isinstance(drain, dict):
                continue
            try:
                cobertura = float(drain["obstruction_coverage"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(cobertura) and 0 <= cobertura <= 1:
                validadas.append((cobertura, drain))
        if not validadas:
            rejeitadas.append(Rejeicao(posicao, asset_id, "Visão: cobertura de obstrução inválida"))
            continue

        cobertura, pior = max(validadas, key=lambda par: par[0])
        fora_do_bueiro = assessment.get("obstruction_outside_drain_count", 0)
        if isinstance(fora_do_bueiro, int) and fora_do_bueiro > 0:
            cobertura = max(cobertura, COBERTURA_PARCIAL_MINIMA / 100)
        materiais = "|".join(str(m) for m in (pior.get("materials") or []))
        inspecoes[asset_id] = Inspecao(
            asset_id,
            hoje,
            round(cobertura * 100, 1),
            materiais,
            "visao_computacional",
        )

    if not bueiros:
        raise InputDataError(f"{caminho.name}: nenhum item de inspeção válido.")
    log.info(
        "Entrada Visão: %d itens, %d rejeitados, %d sem bueiro detectado.",
        len(payload["items"]),
        len(rejeitadas),
        len(bueiros) - len(inspecoes),
    )
    areas_por_nome = {area.bairro: area for area in areas_por_id.values()}
    return bueiros, inspecoes, areas_por_nome, rejeitadas
