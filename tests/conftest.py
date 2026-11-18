from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from bocadelobo.config import ROOT, Regras, Settings

AGORA = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)  # 06:00 em Brasília
HOJE = date(2026, 11, 17)
AMOSTRAS = ROOT / "data" / "samples"


@pytest.fixture
def regras() -> Regras:
    return Regras.carregar(ROOT / "config" / "regras.json")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=ROOT / "data",
        output_dir=tmp_path / "output",
        log_dir=tmp_path / "logs",
        regras_path=ROOT / "config" / "regras.json",
        latitude=-23.56,
        longitude=-46.60,
        utc_offset_horas=-3,
        webhook_url=None,
    )
