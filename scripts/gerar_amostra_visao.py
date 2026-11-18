"""Snapshot sanitizado da fila JSON exportada pelo componente de Visão Computacional do grupo.

Uso: python scripts/gerar_amostra_visao.py [--raiz-visao CAMINHO]
As imagens e as caixas detalhadas de detecção não são copiadas para este snapshot.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raiz-visao",
        type=Path,
        default=ROOT.parent / "ACV",
        help="raiz local do projeto Applied Computer Vision (padrão: ../ACV)",
    )
    args = parser.parse_args()
    fonte = args.raiz_visao / "output" / "action_queue.json"
    areas = args.raiz_visao / "data" / "areas_risco.csv"
    payload = json.loads(fonte.read_text(encoding="utf-8"))
    campos = ("asset_id", "area_id", "image_file", "forecast_status", "assessment")
    snapshot = {
        "schema_version": payload["schema_version"],
        "run_id": payload["run_id"],
        "generated_at": payload["generated_at"],
        "summary": payload["summary"],
        "items": [{k: item[k] for k in campos} for item in payload["items"]],
        "rejected": payload.get("rejected", []),
    }

    destino = ROOT / "data" / "samples"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "vision_action_queue.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with open(areas, newline="", encoding="utf-8-sig") as entrada:
        linhas = list(csv.reader(entrada))
    with open(destino / "areas_risco_visao.csv", "w", newline="", encoding="utf-8") as saida:
        csv.writer(saida, lineterminator="\n").writerows(linhas)
    print(
        f"Snapshot salvo: {len(snapshot['items'])} itens, "
        f"{len(snapshot['rejected'])} rejeições em {destino}"
    )


if __name__ == "__main__":
    main()
