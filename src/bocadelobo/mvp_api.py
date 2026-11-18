"""API somente leitura que expõe o resultado do robô ao MVP (dashboard/app) - apenas biblioteca padrão."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .storage import Storage

log = logging.getLogger(__name__)


def _consultar(db: Path, rota: str) -> tuple[int, dict]:
    with Storage(db) as storage:
        execucao = storage.ultima_execucao()
        if rota == "/api/saude":
            return 200, {"status": "ok", "ultima_execucao": execucao}
        if execucao is None:
            return 404, {"erro": "nenhuma execução registrada"}
        if rota == "/api/prioridades":
            prioridades = [
                {**p, "human_approval_required": True}
                for p in storage.prioridades(execucao["id"])
            ]
            return 200, {"execucao": execucao, "prioridades": prioridades}
        if rota == "/api/alertas":
            return 200, {"data_ref": execucao["data_ref"], "alertas": storage.alertas_do_dia(execucao["data_ref"])}
    return 404, {"erro": "rota inexistente"}


def criar_servidor(db: Path, host: str = "127.0.0.1", porta: int = 8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            try:
                codigo, corpo = _consultar(db, urlparse(self.path).path)
            except Exception:
                log.exception("Erro ao atender %s", self.path)
                codigo, corpo = 500, {"erro": "erro interno"}
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, fmt: str, *args) -> None:
            log.info("API %s", fmt % args)

    return ThreadingHTTPServer((host, porta), Handler)
