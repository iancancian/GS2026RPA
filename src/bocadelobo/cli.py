"""Interface de linha de comando: `python -m bocadelobo executar|servir`."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import pipeline
from .config import Regras, Settings
from .errors import BocaDeLoboError
from .mvp_api import criar_servidor


def configurar_logs(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # consoles Windows usam cp1252 por padrão
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    arquivo = RotatingFileHandler(log_dir / "bocadelobo.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    console = logging.StreamHandler()
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    for h in (arquivo, console):
        h.setFormatter(formato)
        raiz.addHandler(h)


def _agora(valor: str) -> datetime:
    dt = datetime.fromisoformat(valor)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bocadelobo", description="RPA Boca de Lobo")
    sub = parser.add_subparsers(dest="comando", required=True)

    ex = sub.add_parser("executar", help="roda o fluxo diário")
    ex.add_argument("--previsao-arquivo", type=Path, help="usa previsão local (formato Open-Meteo) em vez da API")
    ex.add_argument("--visao-action-queue", type=Path, help="consome action_queue.json exportado pelo componente de Visão")
    ex.add_argument("--visao-areas", type=Path, help="CSV de áreas usado pelo componente de Visão")
    ex.add_argument(
        "--aprovar-envio",
        action="store_true",
        help="após revisão humana, permite enviar os alertas para o webhook configurado nesta execução",
    )
    ex.add_argument("--agora", type=_agora, help="data/hora ISO (UTC) da execução, para reprodutibilidade")
    ex.add_argument("--dry-run", action="store_true", help="simula sem enviar alertas nem gravar resultados")

    sv = sub.add_parser("servir", help="sobe a API somente leitura para o MVP")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--porta", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        configurar_logs(settings.log_dir)
        log = logging.getLogger("bocadelobo")
        if args.comando == "servir":
            servidor = criar_servidor(settings.output_dir / pipeline.DB_NOME, args.host, args.porta)
            log.info("API do MVP em http://%s:%d/api/prioridades (Ctrl+C para parar)", args.host, args.porta)
            try:
                servidor.serve_forever()
            except KeyboardInterrupt:
                servidor.server_close()
            return 0
        regras = Regras.carregar(settings.regras_path)
        pipeline.executar(
            settings,
            regras,
            args.agora,
            args.previsao_arquivo,
            args.dry_run,
            visao_action_queue=args.visao_action_queue,
            visao_areas=args.visao_areas,
            aprovar_alertas=args.aprovar_envio,
        )
        return 0
    except BocaDeLoboError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception:
        logging.getLogger("bocadelobo").exception("Erro inesperado")
        return 1


if __name__ == "__main__":
    sys.exit(main())
