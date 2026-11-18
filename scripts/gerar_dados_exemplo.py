"""Gera os dados SIMULADOS de exemplo (determinístico, seed fixa).

Justificativa: o cadastro oficial de bocas de lobo e as inspeções por visão computacional (componente
"Visão" do MVP) ainda não são abertos ao projeto. Os dados reproduzem o contrato esperado e incluem
linhas inválidas de propósito para exercitar o tratamento de exceções do robô.

Uso: python scripts/gerar_dados_exemplo.py
"""

from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
SAMPLES = DATA / "samples"
REFERENCIA = date(2026, 11, 17)
SEED = 42

# bairro: (lat, lon, ruas, nivel_risco, alagamentos_ultimo_ano, equipamento_sensivel)
BAIRROS = {
    "Mooca": (-23.5606, -46.5975, ["Rua da Mooca", "Av. Paes de Barros", "Rua Taquari"], 4, 6, "sim"),
    "Ipiranga": (-23.5886, -46.6097, ["Av. Nazaré", "Rua Bom Pastor", "Rua Silva Bueno"], 5, 9, "nao"),
    "Vila Prudente": (-23.5876, -46.5805, ["Av. Anhaia Mello", "Rua do Orfanato", "Rua Oratório"], 5, 8, "sim"),
    "Penha": (-23.5290, -46.5420, ["Av. Penha de França", "Rua Dr. João Ribeiro", "Rua Candapuí"], 3, 3, "nao"),
    "Tatuapé": (-23.5405, -46.5760, ["Rua Tuiuti", "Av. Radial Leste", "Rua Serra de Botucatu"], 2, 2, "nao"),
    "Cambuci": (-23.5668, -46.6230, ["Rua Lavapés", "Av. Lacerda Franco", "Rua Independência"], 4, 5, "sim"),
}
RESIDUOS = ["folhas", "lixo plástico", "sedimento", "entulho", "folhas e lixo"]


def escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecalho)
        w.writerows(linhas)


def gerar_cadastro(rng: random.Random) -> list[list]:
    linhas, n = [], 1
    for bairro, (lat, lon, ruas, *_rest) in BAIRROS.items():
        for i in range(6):
            linhas.append([
                f"BL-{n:03d}", bairro, f"{ruas[i % 3]}, {100 + 40 * i}",
                round(lat + rng.uniform(-0.004, 0.004), 6), round(lon + rng.uniform(-0.004, 0.004), 6),
            ])
            n += 1
    return linhas


def gerar_inspecoes(rng: random.Random, cadastro: list[list]) -> list[list]:
    linhas = []
    for idx, (bueiro_id, *_rest) in enumerate(cadastro):
        if idx == 35:  # último bueiro nunca foi inspecionado
            continue
        antiguidade = rng.choice([0, 0, 1, 2, 3, 5]) if idx not in (7, 20) else rng.randint(10, 20)
        pct = rng.choice([rng.randint(5, 35), rng.randint(40, 69), rng.randint(70, 98)])
        linhas.append([
            bueiro_id, (REFERENCIA - timedelta(days=antiguidade)).isoformat(), pct,
            rng.choice(RESIDUOS), "visao_computacional" if idx % 4 else "vistoria_equipe",
        ])
    ontem = (REFERENCIA - timedelta(days=1)).isoformat()
    # linhas sujas propositais: duplicada, texto, fora da faixa, id inexistente, data inválida, id vazio
    linhas += [
        [linhas[0][0], (REFERENCIA - timedelta(days=9)).isoformat(), 20, "folhas", "vistoria_equipe"],
        ["BL-004", ontem, "abc", "lixo plástico", "visao_computacional"],
        ["BL-005", ontem, 150, "entulho", "visao_computacional"],
        ["BL-999", ontem, 55, "folhas", "visao_computacional"],
        ["BL-006", "31/02/2026", 60, "sedimento", "vistoria_equipe"],
        ["", ontem, 40, "folhas", "visao_computacional"],
    ]
    return linhas


def gerar_previsao(chuva_por_hora: dict[int, float], prob: int, base_prob: int) -> dict:
    inicio = datetime(REFERENCIA.year, REFERENCIA.month, REFERENCIA.day)
    tempos = [(inicio + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
    return {
        "latitude": -23.56, "longitude": -46.6, "utc_offset_seconds": -10800, "timezone": "America/Sao_Paulo",
        "hourly": {
            "time": tempos,
            "precipitation": [chuva_por_hora.get(h, 0.0) for h in range(48)],
            "precipitation_probability": [prob if h in chuva_por_hora else base_prob for h in range(48)],
        },
    }


def main() -> None:
    rng = random.Random(SEED)
    SAMPLES.mkdir(parents=True, exist_ok=True)
    cadastro = gerar_cadastro(rng)
    escrever_csv(DATA / "bueiros.csv", ["bueiro_id", "bairro", "logradouro", "latitude", "longitude"], cadastro)
    escrever_csv(DATA / "inspecoes.csv", ["bueiro_id", "data_inspecao", "entupimento_pct", "tipo_residuo", "origem"],
                 gerar_inspecoes(rng, cadastro))
    escrever_csv(DATA / "areas_risco.csv", ["bairro", "nivel_risco", "alagamentos_ultimo_ano", "equipamento_sensivel"],
                 [[b, v[3], v[4], v[5]] for b, v in BAIRROS.items()])

    tempestade = {14: 4.0, 15: 9.0, 16: 15.0, 17: 21.0, 18: 14.0, 19: 7.0, 20: 3.0}
    garoa = {15: 1.2, 16: 2.0, 17: 1.5, 18: 0.8}
    for nome, chuva, prob, base in (("tempestade", tempestade, 92, 20), ("seco", garoa, 35, 10)):
        (SAMPLES / f"previsao_{nome}.json").write_text(
            json.dumps(gerar_previsao(chuva, prob, base), indent=1), encoding="utf-8"
        )
    print("Dados de exemplo gerados em", DATA)


if __name__ == "__main__":
    main()
