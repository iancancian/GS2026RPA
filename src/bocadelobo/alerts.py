"""Etapa 4: monta e despacha alertas para a equipe de limpeza e para os moradores."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import requests

from .config import Regras
from .forecast import ALERTA, ATENCAO, EMERGENCIA
from .models import Alerta, AreaRisco, Previsao, Prioridade
from .prioritizer import CRITICO
from .storage import Storage

log = logging.getLogger(__name__)

ROTULO_NIVEL = {ATENCAO: "ATENÇÃO", ALERTA: "ALERTA", EMERGENCIA: "EMERGÊNCIA"}
CONTATOS = "Emergências: Defesa Civil 199 | Bombeiros 193."


def bairros_afetados(
    prioridades: list[Prioridade], areas: dict[str, AreaRisco], regras: Regras
) -> list[str]:
    """Bairro avisa moradores se tem bueiro crítico ou área de alto risco com bueiro entupido."""
    minimo = regras.nivel_risco_minimo_moradores
    afetados: set[str] = set()
    for p in prioridades:
        area = areas.get(p.bairro)
        if p.classe == CRITICO or (area and area.nivel_risco >= minimo):
            afetados.add(p.bairro)
    return sorted(afetados)


def gerar_alertas(
    data_ref: date,
    nivel: str,
    previsao: Previsao,
    prioridades: list[Prioridade],
    areas: dict[str, AreaRisco],
    regras: Regras,
) -> list[Alerta]:
    rotulo = ROTULO_NIVEL[nivel]
    resumo = f"{previsao.chuva_mm:.0f} mm em {previsao.horas}h, pico de {previsao.pico_horario_mm:.0f} mm/h"
    alertas: list[Alerta] = []

    acionados = [p for p in prioridades if p.dentro_da_capacidade]
    adiados = len(prioridades) - len(acionados)
    linhas = [
        f"{p.posicao}. [{p.classe} {p.entupimento_pct:.0f}%] {p.bueiro_id} - {p.logradouro} ({p.bairro})"
        f" - equipe {p.equipe}"
        for p in acionados
    ]
    texto = (
        f"[RASCUNHO - REVISÃO HUMANA | BOCA DE LOBO - {rotulo}] "
        f"Chuva prevista: {resumo}. Validar em campo antes de qualquer ação:\n"
        + "\n".join(linhas)
    )
    if adiados:
        texto += f"\n+ {adiados} bueiro(s) acima da capacidade diária: reavaliar reforço de equipe."
    alertas.append(Alerta(f"{data_ref}|equipe|TODOS|{nivel}", "equipe_limpeza", "TODOS", nivel, texto))

    for bairro in bairros_afetados(prioridades, areas, regras):
        do_bairro = [p for p in prioridades if p.bairro == bairro]
        criticos = [p for p in do_bairro if p.classe == CRITICO]
        ativos = sorted({p.bueiro_id for p in (criticos or do_bairro)})
        texto = (
            f"[RASCUNHO - NÃO PUBLICADO | {rotulo}] {bairro}: chuva prevista, {resumo}. "
            f"Inspeções que requerem avaliação: {', '.join(ativos)}. "
            "A localização exata não está disponível neste protótipo. Confirme o local e aprove antes de divulgar; "
            f"não atravesse áreas alagadas. {CONTATOS}"
        )
        alertas.append(Alerta(f"{data_ref}|moradores|{bairro}|{nivel}", "moradores", bairro, nivel, texto))
    return alertas


class Canal(Protocol):
    nome: str

    def enviar(self, alerta: Alerta) -> None: ...


class CanalArquivo:
    """Caixa de saída em JSONL: consumida pelo app/mural do MVP e usada como evidência de auditoria."""

    nome = "arquivo"

    def __init__(self, caminho: Path):
        self.caminho = caminho

    def enviar(self, alerta: Alerta) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        registro = {**asdict(alerta), "gerado_em": datetime.now().isoformat(timespec="seconds")}
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


class CanalWebhook:
    """POST JSON para um webhook (ex.: Teams, Slack, Zapier). URL via ambiente; o log mostra só o host."""

    nome = "webhook"

    def __init__(self, url: str, tentativas: int = 3, sleep=time.sleep):
        self.url = url
        self.host = urlparse(url).netloc
        self.tentativas = tentativas
        self.sleep = sleep

    def enviar(self, alerta: Alerta) -> None:
        corpo = {k: v for k, v in asdict(alerta).items() if k != "chave"}
        corpo["text"] = alerta.mensagem
        ultimo: Exception | None = None
        for tentativa in range(1, self.tentativas + 1):
            try:
                requests.post(self.url, json=corpo, timeout=10).raise_for_status()
                return
            except requests.RequestException as exc:
                ultimo = exc
                log.warning("Webhook %s: tentativa %d/%d falhou (%s)", self.host, tentativa, self.tentativas, type(exc).__name__)
                if tentativa < self.tentativas:
                    self.sleep(2**tentativa)
        raise RuntimeError(f"webhook {self.host} indisponível") from ultimo


@dataclass
class ResumoEnvio:
    enviados: int = 0
    duplicados: int = 0
    falhas: int = 0


def despachar(
    alertas: list[Alerta],
    canais: list[Canal],
    storage: Storage,
    agora: datetime,
    dry_run: bool = False,
) -> ResumoEnvio:
    """Envia cada alerta por cada canal, uma única vez (idempotente) e sem falha silenciosa."""
    resumo = ResumoEnvio()
    for alerta in alertas:
        for canal in canais:
            if storage.alerta_ja_enviado(alerta.chave, canal.nome):
                resumo.duplicados += 1
                log.info("Alerta já enviado, ignorado: %s via %s", alerta.chave, canal.nome)
                continue
            if dry_run:
                log.info("[dry-run] enviaria %s via %s", alerta.chave, canal.nome)
                continue
            try:
                canal.enviar(alerta)
            except Exception as exc:  # um canal fora do ar não pode impedir os demais
                resumo.falhas += 1
                log.error("Falha ao enviar %s via %s: %s", alerta.chave, canal.nome, exc)
                continue
            storage.registrar_alerta(alerta, canal.nome, agora)
            resumo.enviados += 1
            if canal.nome == "arquivo":
                log.info("Rascunho gravado na outbox: %s", alerta.chave)
            else:
                log.info("Alerta aprovado enviado: %s via %s", alerta.chave, canal.nome)
    return resumo
