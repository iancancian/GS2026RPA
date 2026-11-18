"""Gera docs/relatorio_tecnico.pdf com os itens exigidos pela atividade de RPA.

Edite LINK_VIDEO abaixo quando o vídeo estiver publicado e execute: python scripts/gerar_relatorio.py
"""

from __future__ import annotations

import csv
import json
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

RAIZ = Path(__file__).resolve().parents[1]

INTEGRANTES = [
    ("Açussena Macedo Mautone", "552568"),
    ("Felipe Heilmann Marques", "551026"),
    ("Felipe Voidela Toledo", "98595"),
    ("Carlos Eduardo Caramante Ribeiro", "552159"),
    ("Ian Cancian Nachtergaele", "98387"),
]
LINK_GITHUB = "https://github.com/iancancian/GS2026ACV"
LINK_VIDEO = "Será publicado antes da entrega final"

AZUL = colors.HexColor("#1A5276")
estilos = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=estilos["Heading1"], textColor=AZUL, fontSize=15, spaceBefore=10, spaceAfter=6, keepWithNext=True)
CORPO = ParagraphStyle("Corpo", parent=estilos["BodyText"], fontSize=9.5, leading=13)
CODIGO = ParagraphStyle("Codigo", parent=estilos["Code"], fontSize=6.6, leading=8.2, backColor=colors.HexColor("#F4F6F7"), borderPadding=4)
CELULA = ParagraphStyle("Celula", parent=CORPO, fontSize=8.2, leading=10)


def p(texto: str) -> Paragraph:
    return Paragraph(texto, CORPO)


def tabela(linhas: list[list[str]], larguras: list[float]) -> Table:
    dados = [[Paragraph(str(c), CELULA) for c in l] for l in linhas]
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D6EAF8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def trecho_log(nome: str, linhas: int = 14) -> Preformatted:
    texto = (RAIZ / "logs" / nome).read_text(encoding="utf-8").splitlines()
    return Preformatted("\n".join(l for r in texto[:linhas] for l in textwrap.wrap(r, 112, subsequent_indent="    ")), CODIGO)


def main() -> None:
    saida = json.loads((RAIZ / "assets/exemplo_saida/prioridades.json").read_text(encoding="utf-8"))
    with open(RAIZ / "assets/exemplo_saida/lista_limpeza.csv", encoding="utf-8") as f:
        top = list(csv.DictReader(f))[:8]
    alerta_equipe = next(a for a in saida["alertas"] if a["audiencia"] == "equipe_limpeza")["mensagem"].splitlines()[:6]
    alerta_morador = next(a for a in saida["alertas"] if a["audiencia"] == "moradores")["mensagem"]

    s: list = [
        Paragraph("Boca de Lobo - Relatório Técnico", estilos["Title"]),
        p("<b>FIAP Global Solution 2026.2 · CitizenTech · Robotic Process Automation</b><br/>"
          "Atividade: Do Processo Manual à Automação Inteligente"),
        Spacer(1, 6),
        Paragraph("1. Integrantes", H1),
        tabela([["Nome completo", "RM"], *[list(i) for i in INTEGRANTES]], [12 * cm, 4 * cm]),
        Paragraph("2. CitizenTech e problema resolvido", H1),
        p("<b>Boca de Lobo</b> apoia moradores de áreas sujeitas a alagamento e equipes de zeladoria. "
          "<b>Problema:</b> a triagem de inspeções antes de chuva forte requer cruzar resultados visuais, previsão "
          "e risco territorial. Fontes: previsão real (Open-Meteo), imagens de teste do Drainage Dataset (CC BY 4.0) "
          "e áreas/inventário simulados. A integração de entrada consome o contrato da Visão Computacional. "
          "ODS: 11, 13 e 10."),
        Paragraph("3. Objetivo da automação e benefício ao cidadão", H1),
        p("O RPA lê a previsão, consome a fila do componente de Visão e, se a chuva passar do limite, gera uma lista "
          "priorizada e rascunhos de alerta para revisão humana. O MVP web ainda não está publicado; a integração "
          "foi verificada localmente por contrato de arquivo e teste. O tempo de execução medido no protótipo não "
          "representa uma comparação validada com processo manual. <b>Benefício esperado:</b> apoiar a equipe a "
          "priorizar vistorias e preparar avisos sem automatizar decisões de campo."),
        Paragraph("4. Descrição do processo e fluxo", H1),
        p("O fluxo tem 11 etapas (PDD em <i>docs/PDD.md</i>; BPMN 2.0 em <i>docs/fluxo.bpmn</i>): agendamento, previsão, "
          "decisão de chuva, leitura e validação, priorização, distribuição de capacidade, geração de alertas, despacho, "
          "persistência e exportação ao MVP."),
        Image(str(RAIZ / "docs/fluxo.png"), width=17 * cm, height=17 * cm * 0.5),
        Paragraph("5. Tecnologias e justificativa", H1),
        tabela([
            ["Tecnologia", "Justificativa"],
            ["Python 3.12 (biblioteca padrão + requests)", "Legível, testável e versionável; poucas dependências facilitam reprodução."],
            ["Open-Meteo", "API pública, gratuita e sem chave: dado real, sem segredo para proteger."],
            ["SQLite + JSON/CSV", "Contrato simples e verificável com o MVP; SQLite também guarda o estado de idempotência."],
            ["http.server (stdlib)", "API read-only mínima para o MVP, sem framework."],
            ["pytest + GitHub Actions", "28 testes automáticos; CI e workflow agendado, condicionado ao feed atualizado da Visão."],
        ], [5.5 * cm, 11.5 * cm]),
        Paragraph("6. Regras de negócio, decisões e processamento", H1),
        tabela([
            ["Regra", "Definição (config/regras.json)"],
            ["Acionamento (decisão)", "prob. ≥ 60% e (chuva ≥ 30 mm/24h ou pico ≥ 20 mm/h). Níveis: ATENÇÃO ≥ 30; ALERTA ≥ 60; EMERGÊNCIA ≥ 100 mm"],
            ["Classe/cobertura visual", "LIVRE < 10% ≤ PARCIAL < 80% ≤ CRÍTICO; estimativa 2D da Visão, não mede obstrução interna"],
            ["Score (0-100)", "0,5×cobertura visual proxy + 0,3×risco da área + 0,2×histórico (não disponível) + bônus sensível (não disponível)"],
            ["Capacidade", "2 equipes × 6 bueiros/dia; excedentes sinalizados para reforço"],
            ["Rascunhos", "Área de risco com ativo priorizado; sem localização exata, não publicar como rota ou aviso confirmado"],
            ["Repetições", "Validação de cada inspeção; pontuação de cada bueiro; envio de cada alerta por canal"],
        ], [4 * cm, 13 * cm]),
        Spacer(1, 6),
        p("<b>Resultado demonstrativo</b> (entrada sanitizada da Visão; previsão simulada de tempestade): primeiras posições da lista priorizada. Cobertura visual é estimativa por caixas 2D, não medida de entupimento interno."),
        tabela([["Pos.", "Bueiro", "Bairro", "Logradouro", "Cob. 2D", "Classe", "Score", "Equipe"],
                *[[t["posicao"], t["bueiro_id"], t["bairro"], t["logradouro"], f'{float(t["entupimento_pct"]):.0f}%',
                   t["classe"], t["score"], t["equipe"]] for t in top]],
               [1.1 * cm, 1.7 * cm, 2.6 * cm, 4.5 * cm, 1.5 * cm, 2 * cm, 1.4 * cm, 1.5 * cm]),
        Spacer(1, 6),
        p("<b>Rascunho operacional</b> e <b>rascunho por área</b> (não publicados):"),
        Preformatted("\n".join(l for r in alerta_equipe for l in textwrap.wrap(r, 115)), CODIGO),
        Spacer(1, 3),
        Preformatted("\n".join(textwrap.wrap(alerta_morador, 115)), CODIGO),
        Paragraph("7. Tratamento de exceções e recuperação", H1),
        tabela([
            ["Falha", "Tratamento"],
            ["API de previsão fora do ar", "3 tentativas com backoff exponencial; depois cache de até 6h; sem cache: falha explícita (exit 2) e alerta de operação"],
            ["Arquivo ausente ou colunas faltando", "FALHA_DADOS (exit 3) e alerta de operação"],
            ["Linha inválida/duplicada", "Isolada em rejeitados.csv; o lote continua; mantém a inspeção mais recente"],
            ["Imagem sem bueiro detectado ou área inválida", "Revisão manual / item rejeitado, sem afirmar que o bueiro está livre"],
            ["Canal de envio indisponível", "Webhook bloqueado por padrão; requer revisão humana e opção --aprovar-envio"],
            ["Reexecução no mesmo dia", "Idempotência por chave data|audiência|bairro|nível"],
        ], [5.5 * cm, 11.5 * cm]),
        Paragraph("8. Logs e evidências de auditoria", H1),
        p("Cada execução gera log com data/hora, etapa, contagens e motivos de rejeição, sem dados pessoais. "
          "A tabela <i>execucoes</i> (SQLite) registra status, previsão e totais. Trecho real (<i>logs/exemplo_01_sucesso_tempestade.log</i>):"),
        trecho_log("exemplo_01_sucesso_tempestade.log", 14),
        Paragraph("9. Integração com o MVP", H1),
        p("O RPA consome o contrato real da Visão: <i>action_queue.json</i> (schema 1.0) e o CSV de áreas. O resultado "
          "do RPA é disponibilizado para o futuro MVP por três contratos locais: (1) <b>SQLite</b> <i>output/mvp.db</i> "
          "(tabelas execucoes, prioridades, alertas_enviados); (2) arquivos estruturados <i>prioridades.json</i> e "
          "<i>lista_limpeza.csv</i>; (3) <b>API HTTP read-only</b> (<i>/api/prioridades</i>, <i>/api/alertas</i>, <i>/api/saude</i>) para o "
          "dashboard/app. As prioridades do contrato sinalizam <i>human_approval_required=true</i>. Essa API é "
          "somente local; ainda não foi conectado um dashboard público. Os testes "
          "<i>test_vision_integration</i> e <i>test_api_do_mvp_serve_resultado_do_robo</i> verificam respectivamente "
          "a entrada da Visão e a API local de saída."),
        Paragraph("10. Testes realizados (sucesso, decisão e falha)", H1),
        tabela([
            ["Tipo", "Cenário", "Resultado"],
            ["Sucesso", "Tempestade gera lista ordenada, alertas, exportações e API do MVP", "Aprovado"],
            ["Decisão", "Chuva abaixo do limite/baixa probabilidade não aciona; níveis ATENÇÃO/ALERTA/EMERGÊNCIA; pico horário", "Aprovado"],
            ["Decisão", "Score, faixas, capacidade e bueiro sem inspeção; idempotência na reexecução", "Aprovado"],
            ["Falha", "API fora do ar (retry, cache, falha explícita); arquivo ausente; linhas inválidas; canal fora do ar", "Aprovado"],
        ], [2.2 * cm, 12 * cm, 2.8 * cm]),
        Spacer(1, 4),
        p("Total: <b>28 testes aprovados</b> (<i>tests/resultado_pytest.txt</i>). Execução real da falha de API (<i>exit 2</i>):"),
        trecho_log("exemplo_04_api_fora_do_ar.log", 10),
        Paragraph("11. Segurança e LGPD", H1),
        p("O robô <b>não trata dados pessoais</b> de moradores; as saídas são rascunhos por área. Segredos "
          "(webhook) ficam em variáveis de ambiente/GitHub Secrets, e <i>.env</i> não é versionado; a URL nunca é "
          "registrada em log. A API é somente leitura e escuta em 127.0.0.1 por padrão. Se houver futuro cadastro de "
          "moradores: base legal/consentimento, minimização, pseudonimização e prazo de retenção. A priorização é "
          "explicável (regras em JSON) e a equipe valida em campo (humano no circuito)."),
        Paragraph("12. Links", H1),
        p(f"Repositório GitHub: {LINK_GITHUB}<br/>Vídeo demonstrativo (até 3 min): {LINK_VIDEO}"),
    ]
    destino = RAIZ / "docs" / "relatorio_tecnico.pdf"
    SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                      bottomMargin=1.8 * cm, title="Boca de Lobo - Relatório Técnico").build(s)
    print("Gerado", destino)


if __name__ == "__main__":
    main()
