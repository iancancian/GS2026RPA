"""Persistência em SQLite: contrato de integração com o MVP e controle de idempotência dos alertas."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import Alerta, Prioridade

SCHEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    executado_em TEXT NOT NULL,
    data_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    nivel_chuva TEXT,
    chuva_mm REAL,
    pico_horario_mm REAL,
    prob_max_pct INTEGER,
    fonte_previsao TEXT,
    total_bueiros INTEGER,
    total_prioridades INTEGER,
    rejeitados INTEGER,
    alertas_enviados INTEGER,
    falhas_envio INTEGER
);
CREATE TABLE IF NOT EXISTS prioridades (
    execucao_id INTEGER NOT NULL REFERENCES execucoes(id),
    posicao INTEGER, bueiro_id TEXT, bairro TEXT, logradouro TEXT,
    latitude REAL, longitude REAL, entupimento_pct REAL, classe TEXT, score REAL,
    tipo_residuo TEXT, inspecao_desatualizada INTEGER, dentro_da_capacidade INTEGER, equipe INTEGER
);
CREATE TABLE IF NOT EXISTS alertas_enviados (
    chave TEXT NOT NULL, canal TEXT NOT NULL, enviado_em TEXT NOT NULL,
    audiencia TEXT, bairro TEXT, nivel TEXT, mensagem TEXT,
    PRIMARY KEY (chave, canal)
);
"""


class Storage:
    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(caminho)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def alerta_ja_enviado(self, chave: str, canal: str) -> bool:
        linha = self.conn.execute(
            "SELECT 1 FROM alertas_enviados WHERE chave = ? AND canal = ?", (chave, canal)
        ).fetchone()
        return linha is not None

    def registrar_alerta(self, alerta: Alerta, canal: str, quando: datetime) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO alertas_enviados VALUES (?,?,?,?,?,?,?)",
                (alerta.chave, canal, quando.isoformat(), alerta.audiencia, alerta.bairro, alerta.nivel, alerta.mensagem),
            )

    def registrar_execucao(self, dados: dict, prioridades: list[Prioridade]) -> int:
        colunas = ", ".join(dados)
        marcadores = ", ".join("?" for _ in dados)
        with self.conn:
            cur = self.conn.execute(f"INSERT INTO execucoes ({colunas}) VALUES ({marcadores})", tuple(dados.values()))
            execucao_id = cur.lastrowid
            for p in prioridades:
                d = asdict(p)
                self.conn.execute(
                    "INSERT INTO prioridades VALUES (:execucao_id, :posicao, :bueiro_id, :bairro, :logradouro,"
                    " :latitude, :longitude, :entupimento_pct, :classe, :score, :tipo_residuo,"
                    " :inspecao_desatualizada, :dentro_da_capacidade, :equipe)",
                    {**d, "execucao_id": execucao_id},
                )
        return execucao_id

    def ultima_execucao(self) -> dict | None:
        with closing(self.conn.execute("SELECT * FROM execucoes ORDER BY id DESC LIMIT 1")) as cur:
            linha = cur.fetchone()
        return dict(linha) if linha else None

    def prioridades(self, execucao_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM prioridades WHERE execucao_id = ? ORDER BY posicao", (execucao_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    def alertas_do_dia(self, data_ref: str) -> list[dict]:
        cur = self.conn.execute(
            "SELECT chave, canal, enviado_em, audiencia, bairro, nivel, mensagem FROM alertas_enviados"
            " WHERE chave LIKE ? ORDER BY enviado_em",
            (f"{data_ref}|%",),
        )
        return [dict(r) for r in cur.fetchall()]
