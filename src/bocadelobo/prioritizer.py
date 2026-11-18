"""Etapa 3: cruza entupimento x áreas de risco e gera a lista priorizada de limpeza."""

from __future__ import annotations

from datetime import date

from .config import Regras
from .inspection import AREA_PADRAO_RISCO
from .models import AreaRisco, Bueiro, Inspecao, Prioridade

LIVRE, PARCIAL, CRITICO = "LIVRE", "PARCIAL", "CRITICO"


def classificar_entupimento(pct: float, regras: Regras) -> str:
    if pct >= regras.entupimento.critico_pct:
        return CRITICO
    if pct >= regras.entupimento.parcial_pct:
        return PARCIAL
    return LIVRE


def calcular_score(pct: float, area: AreaRisco, regras: Regras) -> float:
    """Score 0-100: entupimento + risco da área + histórico de alagamentos + bônus (hospital/escola)."""
    p = regras.pesos
    score = (
        p.entupimento * pct
        + p.risco_area * (area.nivel_risco / 5 * 100)
        + p.historico * (min(area.alagamentos_ultimo_ano / 10, 1) * 100)
        + (p.bonus_equipamento_sensivel if area.equipamento_sensivel else 0)
    )
    return round(min(score, 100.0), 1)


def montar_lista(
    bueiros: dict[str, Bueiro],
    inspecoes: dict[str, Inspecao],
    areas: dict[str, AreaRisco],
    regras: Regras,
    hoje: date,
) -> tuple[list[Prioridade], list[str]]:
    """Retorna (lista priorizada, ids de bueiros sem inspeção que exigem vistoria)."""
    candidatos: list[tuple[float, float, Bueiro, Inspecao, str]] = []
    sem_inspecao: list[str] = []

    for bueiro in bueiros.values():
        insp = inspecoes.get(bueiro.bueiro_id)
        if insp is None:
            sem_inspecao.append(bueiro.bueiro_id)
            continue
        classe = classificar_entupimento(insp.entupimento_pct, regras)
        if classe == LIVRE:
            continue
        area = areas.get(bueiro.bairro) or AreaRisco(bueiro.bairro, AREA_PADRAO_RISCO, 0, False)
        candidatos.append((calcular_score(insp.entupimento_pct, area, regras), insp.entupimento_pct, bueiro, insp, classe))

    candidatos.sort(key=lambda c: (-c[0], -c[1], c[2].bueiro_id))

    capacidade = regras.capacidade
    lista: list[Prioridade] = []
    for posicao, (score, pct, bueiro, insp, classe) in enumerate(candidatos, start=1):
        dentro = posicao <= capacidade.total
        lista.append(
            Prioridade(
                posicao=posicao,
                bueiro_id=bueiro.bueiro_id,
                bairro=bueiro.bairro,
                logradouro=bueiro.logradouro,
                latitude=bueiro.latitude,
                longitude=bueiro.longitude,
                entupimento_pct=pct,
                classe=classe,
                score=score,
                tipo_residuo=insp.tipo_residuo,
                inspecao_desatualizada=(hoje - insp.data_inspecao).days > regras.entupimento.validade_inspecao_dias,
                dentro_da_capacidade=dentro,
                equipe=((posicao - 1) % capacidade.equipes) + 1 if dentro else None,
            )
        )
    return lista, sorted(sem_inspecao)
