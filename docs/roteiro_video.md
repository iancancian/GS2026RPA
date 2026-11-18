# Roteiro do vídeo (até 3 minutos)

| Tempo | Cena | Fala sugerida |
|---|---|---|
| 0:00–0:25 | Slide/README com a ficha técnica | "O projeto integra visão computacional e RPA para organizar inspeções e apoiar equipes antes de chuva forte. É um protótipo: as áreas são simuladas e qualquer ação exige confirmação humana." |
| 0:25–0:50 | `docs/fluxo.png` | "A Visão gera uma fila JSON com as avaliações das imagens. O RPA valida esse contrato, consulta a previsão, aplica as regras e prepara resultados estruturados." |
| 0:50–1:40 | Terminal, executar o comando integrado abaixo | "Usamos um snapshot sanitizado da saída real do componente de Visão. Com a previsão de demonstração de 73 mm, o RPA gera uma fila priorizada. Repare nas inspeções rejeitadas pela Visão e nas três que exigem revisão manual: não foram detectados bueiros." Abrir `output/lista_limpeza.csv` e `outbox_alertas.jsonl`; mostrar que os alertas são rascunhos. |
| 1:40–2:00 | Executar com `previsao_seco.json` | "Com chuva abaixo do limite, não há ação operacional; o resultado é registrado como SEM_ACAO." |
| 2:00–2:25 | `python -m bocadelobo servir`; abrir `/api/prioridades` | "A API local expõe o contrato de saída planejado para o MVP. Ainda não há dashboard público conectado." |
| 2:25–2:50 | Mostrar `rejeitados.csv`, revisão manual e `logs/exemplo_04_api_fora_do_ar.log` | "Entradas inconsistentes são isoladas; falha na previsão tenta novamente e usa cache. Um webhook exige revisão humana e aprovação explícita." |
| 2:50–3:00 | Encerramento | "A cobertura é uma estimativa visual, não um diagnóstico de obstrução interna. A equipe confirma no local antes de agir ou divulgar." |

Dica: antes de gravar, apague a pasta `output/` para a demonstração começar do zero.

Comando integrado da demonstração (em PowerShell, na raiz deste repositório):

```powershell
$env:PYTHONPATH = "src"
python -m bocadelobo executar --visao-action-queue data/samples/vision_action_queue.json --visao-areas data/samples/areas_risco_visao.csv --previsao-arquivo data/samples/previsao_tempestade.json --agora 2026-11-17T09:00:00+00:00
```
