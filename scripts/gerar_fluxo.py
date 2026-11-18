"""Gera docs/fluxo.bpmn (BPMN 2.0 com diagrama) e docs/fluxo.png a partir de uma única definição do processo.

Uso: python scripts/gerar_fluxo.py
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

DOCS = Path(__file__).resolve().parents[1] / "docs"

COL, X0 = 190, 90
Y = {"fim": 60, "ramo": 190, "main": 340, "ret": 490, "skip": 585}
TAREFA, GW, EVT = (150, 64), 60, 40
ROTULO_ACIMA = {"e_f1", "e_sem", "e_f2"}  # a seta chega por baixo, então o rótulo vai acima

# id: (tipo, rótulo, coluna, linha, extra)
NOS = {
    "ini": ("inicio", "Agendador\n06h", 0, "main", ""),
    "t_prev": ("tarefa", "Consultar previsão\n(API, retry, cache)", 1, "main", ""),
    "g_prev": ("gateway", "Previsão\nobtida?", 2, "main", ""),
    "t_cls": ("tarefa", "Classificar chuva\n(limiar e prob.)", 3, "main", ""),
    "g_chuva": ("gateway", "Chuva acima\ndo limite?", 4, "main", ""),
    "t_dados": ("tarefa", "Ler e validar\nCSVs de entrada", 5, "main", ""),
    "g_dados": ("gateway", "Arquivos\nválidos?", 6, "main", ""),
    "t_f1": ("tarefa", "Registrar\nFALHA_PREVISAO\ne avisar operação", 2, "ramo", ""),
    "e_f1": ("fim_erro", "Falha\n(exit 2)", 2, "fim", ""),
    "t_sem": ("tarefa", "Registrar SEM_ACAO\ne exportar ao MVP", 4, "ramo", ""),
    "e_sem": ("fim", "Fim\n(sem ação)", 4, "fim", ""),
    "t_f2": ("tarefa", "Registrar\nFALHA_DADOS\ne avisar operação", 6, "ramo", ""),
    "e_f2": ("fim_erro", "Falha\n(exit 3)", 6, "fim", ""),
    "t_insp": ("tarefa", "Isolar inspeções\ninválidas/duplicadas", 6, "ret", "loop"),
    "t_prio": ("tarefa", "Classificar, pontuar\ne ordenar bueiros", 5, "ret", "loop"),
    "t_alert": ("tarefa", "Gerar alertas\n(equipe e bairros)", 4, "ret", "loop"),
    "g_env": ("gateway", "Já\nenviado?", 3, "ret", ""),
    "t_env": ("tarefa", "Enviar por canal\n(arquivo/webhook)", 2, "ret", "loop"),
    "t_pers": ("tarefa", "Persistir SQLite e\nexportar JSON/CSV", 1, "ret", ""),
    "e_fim": ("fim", "MVP consome\nresultados", 0, "ret", ""),
}

# (origem, destino, rótulo, lado_saida, lado_entrada, pontos_intermediarios)
FLUXOS = [
    ("ini", "t_prev", "", "r", "l", []),
    ("t_prev", "g_prev", "", "r", "l", []),
    ("g_prev", "t_cls", "sim", "r", "l", []),
    ("g_prev", "t_f1", "não", "t", "b", []),
    ("t_f1", "e_f1", "", "t", "b", []),
    ("t_cls", "g_chuva", "", "r", "l", []),
    ("g_chuva", "t_dados", "sim", "r", "l", []),
    ("g_chuva", "t_sem", "não", "t", "b", []),
    ("t_sem", "e_sem", "", "t", "b", []),
    ("t_dados", "g_dados", "", "r", "l", []),
    ("g_dados", "t_f2", "não", "t", "b", []),
    ("t_f2", "e_f2", "", "t", "b", []),
    ("g_dados", "t_insp", "sim", "b", "t", []),
    ("t_insp", "t_prio", "", "l", "r", []),
    ("t_prio", "t_alert", "", "l", "r", []),
    ("t_alert", "g_env", "", "l", "r", []),
    ("g_env", "t_env", "não", "l", "r", []),
    ("g_env", "t_pers", "sim", "b", "b", [(3, "skip"), (1, "skip")]),
    ("t_env", "t_pers", "", "l", "r", []),
    ("t_pers", "e_fim", "", "l", "r", []),
]


def centro(no: str) -> tuple[float, float]:
    _, _, c, linha, _ = NOS[no]
    return X0 + c * COL, Y[linha]


def tamanho(no: str) -> tuple[float, float]:
    tipo = NOS[no][0]
    if tipo == "tarefa":
        return TAREFA
    return (GW, GW) if tipo == "gateway" else (EVT, EVT)


def ancora(no: str, lado: str) -> tuple[float, float]:
    x, y = centro(no)
    w, h = tamanho(no)
    return {"r": (x + w / 2, y), "l": (x - w / 2, y), "t": (x, y - h / 2), "b": (x, y + h / 2)}[lado]


def pontos(f) -> list[tuple[float, float]]:
    origem, destino, _, so, si, via = f
    intermediarios = [(X0 + c * COL, Y[linha]) for c, linha in via]
    return [ancora(origem, so), *intermediarios, ancora(destino, si)]


def gerar_bpmn() -> str:
    tipo_tag = {"inicio": "startEvent", "tarefa": "task", "gateway": "exclusiveGateway", "fim": "endEvent", "fim_erro": "endEvent"}
    el, sh, ed = [], [], []
    for nid, (tipo, rotulo, *_r, extra) in NOS.items():
        nome = escape(rotulo.replace("\n", " "))
        filho = ""
        if tipo == "fim_erro":
            filho = '<errorEventDefinition id="err_%s"/>' % nid
        if extra == "loop":
            filho = '<multiInstanceLoopCharacteristics isSequential="true"/>'
        el.append(f'    <{tipo_tag[tipo]} id="{nid}" name="{nome}">{filho}</{tipo_tag[tipo]}>')
        x, y = centro(nid)
        w, h = tamanho(nid)
        marcador = ' isMarkerVisible="true"' if tipo == "gateway" else ""
        sh.append(
            f'      <bpmndi:BPMNShape id="shape_{nid}" bpmnElement="{nid}"{marcador}>'
            f'<dc:Bounds x="{x - w / 2:.0f}" y="{y - h / 2:.0f}" width="{w}" height="{h}"/></bpmndi:BPMNShape>'
        )
    for i, f in enumerate(FLUXOS, start=1):
        fid = f"fluxo_{i}"
        nome = f' name="{escape(f[2])}"' if f[2] else ""
        el.append(f'    <sequenceFlow id="{fid}"{nome} sourceRef="{f[0]}" targetRef="{f[1]}"/>')
        wps = "".join(f'<di:waypoint x="{x:.0f}" y="{y:.0f}"/>' for x, y in pontos(f))
        ed.append(f'      <bpmndi:BPMNEdge id="edge_{fid}" bpmnElement="{fid}">{wps}</bpmndi:BPMNEdge>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"'
        ' xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"'
        ' xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"'
        ' xmlns:di="http://www.omg.org/spec/DD/20100524/DI"'
        ' targetNamespace="https://fiap.com.br/citizentech/boca-de-lobo" id="defs_boca_de_lobo">\n'
        '  <process id="processo_boca_de_lobo" name="Boca de Lobo - fluxo diário" isExecutable="false">\n'
        + "\n".join(el)
        + '\n  </process>\n  <bpmndi:BPMNDiagram id="diagrama_1">\n'
        '    <bpmndi:BPMNPlane id="plano_1" bpmnElement="processo_boca_de_lobo">\n'
        + "\n".join(sh + ed)
        + "\n    </bpmndi:BPMNPlane>\n  </bpmndi:BPMNDiagram>\n</definitions>\n"
    )


def gerar_png(caminho: Path) -> None:
    fig, ax = plt.subplots(figsize=(15.5, 7.6), dpi=130)
    ax.set_xlim(0, X0 + 6 * COL + 90)
    ax.set_ylim(640, -25)
    ax.axis("off")
    cores = {"tarefa": "#E8F0FE", "gateway": "#FFF4CC", "inicio": "#D7F5DD", "fim": "#D7F5DD", "fim_erro": "#FADBD8"}

    for f in FLUXOS:
        pts = pontos(f)
        xs, ys = zip(*pts)
        ax.plot(xs[:-1], ys[:-1], color="#444", lw=1.4, zorder=1)
        ax.annotate("", xy=pts[-1], xytext=pts[-2], arrowprops=dict(arrowstyle="-|>", color="#444", lw=1.4), zorder=1)
        if f[2]:
            (x1, y1), (x2, y2) = pts[0], pts[1]
            ax.text(x1 + (x2 - x1) * 0.35 + (8 if x1 == x2 else 0), y1 + (y2 - y1) * 0.35 - (0 if x1 == x2 else 6),
                    f[2], fontsize=8.5, color="#B03A2E" if f[2] == "não" else "#1E8449", fontweight="bold", zorder=5)

    for nid, (tipo, rotulo, *_r, extra) in NOS.items():
        x, y = centro(nid)
        w, h = tamanho(nid)
        cor = cores[tipo]
        if tipo == "tarefa":
            ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=8",
                                        fc=cor, ec="#1A5276", lw=1.4, zorder=3))
            if extra == "loop":
                ax.text(x, y + h / 2 - 7, "≡", ha="center", va="center", fontsize=11, color="#1A5276", zorder=4)
        elif tipo == "gateway":
            ax.add_patch(Polygon([(x, y - h / 2), (x + w / 2, y), (x, y + h / 2), (x - w / 2, y)],
                                 fc=cor, ec="#9A7D0A", lw=1.4, zorder=3))
            if nid == "g_dados":
                ax.text(x + h / 2 + 6, y + 22, rotulo, ha="left", va="center", fontsize=7.8, zorder=4)
            else:
                ax.text(x, y - h / 2 - 16 if nid == "g_env" else y + h / 2 + 16, rotulo, ha="center", va="center", fontsize=7.8, zorder=4)
            ax.text(x, y, "×", ha="center", va="center", fontsize=14, color="#9A7D0A", zorder=4)
            continue
        else:
            ax.add_patch(Circle((x, y), w / 2, fc=cor, ec="#B03A2E" if tipo == "fim_erro" else "#1E8449",
                                lw=3 if tipo != "inicio" else 1.6, zorder=3))
            acima = nid in ROTULO_ACIMA
            ax.text(x, y - (w / 2 + 16) if acima else y + w / 2 + 16, rotulo, ha="center", va="center", fontsize=7.8, zorder=4)
            continue
        ax.text(x, y + (3 if extra == "loop" else 0), rotulo, ha="center", va="center", fontsize=8, zorder=4)

    ax.text(10, 630, "Boca de Lobo - fluxo diário (BPMN simplificado)   |   ≡ = repetição sobre coleção de itens",
            fontsize=10, fontweight="bold", color="#1B2631")
    fig.savefig(caminho, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    (DOCS / "fluxo.bpmn").write_text(gerar_bpmn(), encoding="utf-8")
    gerar_png(DOCS / "fluxo.png")
    print("Gerados docs/fluxo.bpmn e docs/fluxo.png")
