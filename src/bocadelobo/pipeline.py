"""Orquestra o fluxo de ponta a ponta: previsão -> decisão -> dados -> prioridades -> alertas -> MVP."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import alerts, forecast, inspection, prioritizer
from .alerts import Canal, CanalArquivo, CanalWebhook, ResumoEnvio
from .config import Regras, Settings
from .errors import BocaDeLoboError, ForecastUnavailable, InputDataError
from .models import Alerta, Prioridade, Rejeicao
from .storage import Storage
from .vision_input import carregar_fila_visao

log = logging.getLogger(__name__)

DB_NOME = "mvp.db"
OUTBOX_NOME = "outbox_alertas.jsonl"
STATUS_ACAO, STATUS_SEM_ACAO = "RASCUNHOS_GERADOS", "SEM_ACAO"
STATUS_FALHA = {ForecastUnavailable: "FALHA_PREVISAO", InputDataError: "FALHA_DADOS"}


@dataclass
class ResumoExecucao:
    execucao_id: int | None
    data_ref: str
    status: str
    nivel_chuva: str
    chuva_mm: float
    total_bueiros: int = 0
    prioridades: int = 0
    criticos: int = 0
    rejeitados: int = 0
    sem_inspecao: int = 0
    envio: ResumoEnvio = field(default_factory=ResumoEnvio)


def montar_canais(settings: Settings, aprovar_alertas: bool = False) -> list[Canal]:
    canais: list[Canal] = [CanalArquivo(settings.output_dir / OUTBOX_NOME)]
    if settings.webhook_url:
        if aprovar_alertas:
            canais.append(CanalWebhook(settings.webhook_url))
        else:
            log.warning("Webhook bloqueado: revise os rascunhos e use --aprovar-envio nesta execução.")
    return canais


def executar(
    settings: Settings,
    regras: Regras,
    agora_utc: datetime | None = None,
    previsao_arquivo: Path | None = None,
    dry_run: bool = False,
    canais: list[Canal] | None = None,
    buscar=forecast.buscar_api,
    visao_action_queue: Path | None = None,
    visao_areas: Path | None = None,
    aprovar_alertas: bool = False,
) -> ResumoExecucao:
    if bool(visao_action_queue) != bool(visao_areas):
        raise InputDataError("Informe juntos --visao-action-queue e --visao-areas.")
    agora_utc = agora_utc or datetime.now(timezone.utc)
    hoje = (agora_utc + timedelta(hours=settings.utc_offset_horas)).date()
    canais = canais if canais is not None else montar_canais(settings, aprovar_alertas)
    log.info("=== Execução Boca de Lobo | data_ref=%s | regras v%s | dry_run=%s ===", hoje, regras.versao, dry_run)

    with Storage(settings.output_dir / DB_NOME) as storage:
        try:
            return _fluxo(
                settings, regras, agora_utc, hoje, previsao_arquivo, dry_run, canais, buscar,
                storage, visao_action_queue, visao_areas,
            )
        except BocaDeLoboError as exc:
            status = STATUS_FALHA.get(type(exc), "FALHA")
            log.error("Execução interrompida (%s): %s", status, exc)
            if not dry_run:
                _registrar_falha(storage, canais, agora_utc, hoje, status, str(exc))
            raise


def _fluxo(
    settings, regras, agora_utc, hoje, previsao_arquivo, dry_run, canais, buscar, storage,
    visao_action_queue, visao_areas,
) -> ResumoExecucao:
    log.info("[1/5] Obtendo previsão de chuva")
    previsao = forecast.obter_previsao(settings, regras, agora_utc, previsao_arquivo, buscar)
    nivel = forecast.classificar_chuva(previsao, regras)
    log.info(
        "Previsão (%s): %.1f mm/%dh, pico %.1f mm/h, prob. %d%% -> nível %s",
        previsao.fonte, previsao.chuva_mm, previsao.horas, previsao.pico_horario_mm, previsao.prob_max_pct, nivel,
    )

    resumo = ResumoExecucao(None, hoje.isoformat(), STATUS_SEM_ACAO, nivel, previsao.chuva_mm)
    prioridades: list[Prioridade] = []
    rejeitadas: list[Rejeicao] = []
    sem_inspecao: list[str] = []
    alertas: list[Alerta] = []

    if nivel == forecast.NENHUM:
        log.info("Chuva abaixo do limite: nenhuma ação necessária hoje.")
    else:
        resumo.status = STATUS_ACAO
        log.info("[2/5] Carregando e validando dados")
        if visao_action_queue:
            bueiros, inspecoes, areas, rejeitadas = carregar_fila_visao(
                visao_action_queue, visao_areas, hoje
            )
        else:
            log.warning("Usando dados CSV simulados; alertas são apenas demonstração, não publicar.")
            bueiros = inspection.carregar_bueiros(settings.data_dir / "bueiros.csv")
            areas = inspection.carregar_areas(settings.data_dir / "areas_risco.csv")
            inspecoes, rejeitadas = inspection.carregar_inspecoes(settings.data_dir / "inspecoes.csv", bueiros, hoje)
        for r in rejeitadas:
            log.warning("Inspeção rejeitada (linha %d, %s): %s", r.linha, r.bueiro_id or "sem id", r.motivo)

        log.info("[3/5] Priorizando bueiros")
        prioridades, sem_inspecao = prioritizer.montar_lista(bueiros, inspecoes, areas, regras, hoje)
        if sem_inspecao:
            log.warning("%d bueiro(s) sem inspeção válida: vistoria necessária (%s)", len(sem_inspecao), ", ".join(sem_inspecao))
        resumo.total_bueiros = len(bueiros)

        log.info("[4/5] Gerando e despachando alertas")
        alertas = alerts.gerar_alertas(hoje, nivel, previsao, prioridades, areas, regras)
        resumo.envio = alerts.despachar(alertas, canais, storage, agora_utc, dry_run)

    resumo.prioridades = len(prioridades)
    resumo.criticos = sum(p.classe == prioritizer.CRITICO for p in prioridades)
    resumo.rejeitados = len(rejeitadas)
    resumo.sem_inspecao = len(sem_inspecao)

    if dry_run:
        log.info("[dry-run] persistência e exportação ignoradas.")
        return resumo

    log.info("[5/5] Persistindo e exportando para o MVP")
    resumo.execucao_id = storage.registrar_execucao(
        {
            "executado_em": agora_utc.isoformat(timespec="seconds"),
            "data_ref": resumo.data_ref,
            "status": resumo.status,
            "nivel_chuva": nivel,
            "chuva_mm": previsao.chuva_mm,
            "pico_horario_mm": previsao.pico_horario_mm,
            "prob_max_pct": previsao.prob_max_pct,
            "fonte_previsao": previsao.fonte,
            "total_bueiros": resumo.total_bueiros,
            "total_prioridades": resumo.prioridades,
            "rejeitados": resumo.rejeitados,
            "alertas_enviados": resumo.envio.enviados,
            "falhas_envio": resumo.envio.falhas,
        },
        prioridades,
    )
    _exportar(settings.output_dir, resumo, previsao, prioridades, alertas, rejeitadas, sem_inspecao)
    log.info(
        "Concluído: status=%s prioridades=%d (críticos=%d) rejeições=%d rascunhos/entregas=%d duplicados=%d falhas=%d",
        resumo.status, resumo.prioridades, resumo.criticos, resumo.rejeitados,
        resumo.envio.enviados, resumo.envio.duplicados, resumo.envio.falhas,
    )
    return resumo


def _registrar_falha(storage: Storage, canais: list[Canal], agora_utc: datetime, hoje, status: str, detalhe: str) -> None:
    storage.registrar_execucao(
        {"executado_em": agora_utc.isoformat(timespec="seconds"), "data_ref": hoje.isoformat(), "status": status},
        [],
    )
    aviso = Alerta(
        f"{hoje}|operacao|{status}|-",
        "operacao",
        "TODOS",
        status,
        f"[BOCA DE LOBO] O robô não conseguiu concluir a execução ({status}). Verificar manualmente a previsão e as "
        f"bocas de lobo de maior risco. Detalhe: {detalhe}",
    )
    alerts.despachar([aviso], canais, storage, agora_utc)


def _exportar(saida: Path, resumo, previsao, prioridades, alertas, rejeitadas, sem_inspecao) -> None:
    """Arquivos estruturados consumidos pelo dashboard/app do MVP e pela equipe de limpeza."""
    saida.mkdir(parents=True, exist_ok=True)
    payload = {
        "execucao_id": resumo.execucao_id,
        "data_ref": resumo.data_ref,
        "status": resumo.status,
        "nivel_chuva": resumo.nivel_chuva,
        "previsao": {**asdict(previsao), "inicio": previsao.inicio.isoformat()},
        "prioridades": [
            {**asdict(p), "human_approval_required": True}
            for p in prioridades
        ],
        "bueiros_sem_inspecao": sem_inspecao,
        "alertas": [asdict(a) for a in alertas],
    }
    (saida / "prioridades.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(saida / "lista_limpeza.csv", "w", newline="", encoding="utf-8") as f:
        campos = [
            "posicao", "bueiro_id", "bairro", "logradouro", "entupimento_pct",
            "classe", "score", "equipe", "dentro_da_capacidade", "human_approval_required",
        ]
        escritor = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows({**asdict(p), "human_approval_required": True} for p in prioridades)

    with open(saida / "rejeitados.csv", "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["linha", "bueiro_id", "motivo"])
        escritor.writerows((r.linha, r.bueiro_id, r.motivo) for r in rejeitadas)
