# PDD – Process Definition Document · Boca de Lobo

## 1. Visão geral

| Item | Descrição |
|---|---|
| Processo | Verificação matinal de bueiros em risco e acionamento de alertas antes de chuva forte |
| Dono do processo | Defesa Civil / zeladoria da subprefeitura (usuário final); o robô executa como serviço agendado |
| Frequência | Diária, 06h (America/Sao_Paulo) |
| Execução atual (manual) | Analista consulta o site de previsão, abre planilhas de vistoria, cruza com mapa de áreas de risco, monta a lista e envia mensagens por e-mail/WhatsApp (estimativa de hipótese: 1h30 a 2h por dia) |
| Execução automatizada | Fluxo local executável; a previsão e o lote são processados sem ação humana, mas alertas externos e limpeza exigem aprovação humana |
| Volume | O protótipo foi demonstrado com dezenas de itens; volumes maiores ainda precisam de benchmark |

## 2. Entradas e saídas

| Tipo | Artefato | Origem / Destino |
|---|---|---|
| Entrada principal integrada | `action_queue.json` (schema 1.0): ativo, área, resultado da inspeção visual, avaliação e `human_approval_required` | Componente Applied Computer Vision do grupo |
| Entrada principal integrada | CSV de áreas: `area_id`, `area_name`, `high_risk`, latitude e longitude | Contrato de áreas usado pelo componente de Visão; setores/inventário de demonstração são simulados |
| Entrada de teste isolado | `data/bueiros.csv`, `data/inspecoes.csv`, `data/areas_risco.csv` | Dados sintéticos locais, apenas para testar RPA sem depender da Visão |
| Entrada | Previsão horária de chuva (mm e probabilidade) | API Open-Meteo (pública, sem chave) |
| Entrada | `config/regras.json` – limiares e pesos | Gestão (versionado, auditável) |
| Saída | `output/mvp.db` (SQLite), `prioridades.json`, `lista_limpeza.csv` | Contrato local preparado para o futuro MVP; prioridades marcadas `human_approval_required=true`; API read-only em `/api/*`, sem dashboard público conectado |
| Saída | `output/outbox_alertas.jsonl` | Rascunhos destinados à revisão humana; webhook fica bloqueado por padrão |
| Saída | `output/rejeitados.csv`, `logs/bocadelobo.log` | Auditoria |

## 3. Passo a passo (To-Be)

1. **Agendamento** pode disparar o robô às 06h após configuração da entrada atualizada da Visão e do ambiente; workflow de produção ainda não foi habilitado.
2. **Consultar previsão**: API com até 3 tentativas e *backoff* exponencial; se falhar, usa o último cache com até 6h; sem cache válido, falha explícita.
3. **Classificar chuva** (decisão): aciona se probabilidade ≥ 60% **e** (chuva ≥ 30 mm/24h **ou** pico ≥ 20 mm/h). Níveis: ATENÇÃO (≥30), ALERTA (≥60), EMERGÊNCIA (≥100 mm).
4. Se **abaixo do limite**: registra `SEM_ACAO`, exporta resultado vazio ao contrato local e encerra.
5. **Ler e validar arquivos**: estrutura/colunas obrigatórias; arquivo ausente ou inválido interrompe com `FALHA_DADOS`.
6. **Validar inspeções**: ao consumir a Visão, valida schema, áreas, ids e cobertura; preserva os itens rejeitados pelo componente e rejeita registros inconsistentes. No modo CSV de teste, valida linha a linha, data e duplicidade.
7. **Priorizar** (repetição por ativo): a cobertura visual estimada é convertida em proxy percentual: LIVRE < 10% ≤ PARCIAL < 80% ≤ CRÍTICO, alinhada aos limiares da Visão. A estimativa por caixas 2D não mede entupimento interno. Sem detecção de bueiro, o ativo fica para revisão manual.
8. **Distribuir capacidade**: as primeiras `equipes × bueiros_por_equipe_dia` posições recebem equipe (rodízio); as demais são sinalizadas como acima da capacidade.
9. **Gerar rascunhos**: 1 para equipe e 1 por setor afetado. Como o contrato atual não traz localização individual precisa, os rascunhos não indicam ruas/rotas e não devem ser publicados sem confirmação.
10. **Despachar** (repetição rascunho × canal): o canal padrão é uma outbox local. O webhook só é incluído com URL configurada e uso explícito de `--aprovar-envio` após revisão humana; falha em um canal não interrompe os demais.
11. **Persistir e exportar** ao contrato local do futuro MVP; registrar resumo da execução.

Fluxo: [`fluxo.bpmn`](fluxo.bpmn) (BPMN 2.0) e [`fluxo.png`](fluxo.png).

## 4. Regras de negócio

**Score de prioridade (0–100)**

```
score = 0,5 × cobertura visual estimada (proxy em %)
      + 0,3 × (nivel_risco / 5 × 100)
      + 0,2 × min(alagamentos_ano / 10, 1) × 100
      + 10 se a área tem equipamento sensível (hospital/escola)      → limitado a 100
```

Para o contrato atual da Visão, `high_risk=true` é mapeado para nível 5 e `false` para nível 2; histórico e equipamento sensível não são inferidos e permanecem zerados. Desempate: maior cobertura, depois `bueiro_id`. Esta pontuação é uma fila experimental de triagem, não diagnóstico de entupimento real.

**Moradores** são avisados no bairro que tem bueiro crítico **ou** risco ≥ 4 com bueiro entupido. Todos os parâmetros estão em `config/regras.json`.

## 5. Exceções e tratamento

| Exceção | Tratamento | Resultado |
|---|---|---|
| API de previsão fora do ar / resposta inválida | 3 tentativas com backoff → cache ≤ 6h | Degradação controlada (`fonte=cache`) |
| Sem API e sem cache válido | Registra `FALHA_PREVISAO`, alerta de **operação** para checagem manual | Código de saída 2 |
| Arquivo ausente ou colunas faltando | `FALHA_DADOS` + alerta de operação | Código de saída 3 |
| Linha de inspeção inválida/duplicada | Isola em `rejeitados.csv` e segue o lote | Sem interromper |
| Bueiro sem inspeção | Lista de vistoria; não entra no score | Registrado em log |
| Bairro sem cadastro de risco | Usa risco 3 (conservador) | — |
| Canal de envio fora do ar | Registra erro, não marca como enviado, tenta de novo na próxima execução | Sem falha silenciosa |
| Reexecução no mesmo dia | Chave `data|audiência|bairro|nível` evita duplicar rascunhos; se o nível escalar, novo rascunho | Idempotente |

## 6. Logs e auditoria

Formato `data/hora nível módulo | mensagem`, com etapas `[1/5]…[5/5]`, contagens (processados, rejeitados, enviados, duplicados, falhas) e motivos de rejeição. Tabela `execucoes` no SQLite guarda um registro por execução. Não há dados pessoais nem a URL de webhook nos logs (apenas o host em caso de falha de envio).

## 7. Segurança e LGPD

- **Sem dados pessoais**: o robô trata somente objetos urbanos (bueiros) e áreas; alertas são *broadcast* por bairro.
- Segredos (`BL_WEBHOOK_URL`) vêm de variável de ambiente / GitHub Secrets; `.env` está no `.gitignore`.
- API do MVP é somente leitura, vinculada a `127.0.0.1` por padrão e expõe apenas dados não pessoais.
- Caso se adicione cadastro de moradores: base legal/consentimento, minimização, pseudonimização e retenção definida.
- Decisão sensível mantém humano no circuito: a estimativa de visão é experimental; revisar localmente os rascunhos; webhook requer `--aprovar-envio`; a equipe confirma o ponto em campo antes de qualquer ação ou aviso.

## 8. Estado de integração e publicação

- **Visão → RPA:** adaptador executável para o `action_queue.json` schema 1.0 e CSV de áreas, com snapshot de saída real sanitizado em `data/samples/`. Testado localmente.
- **RPA → MVP:** SQLite/JSON/CSV e API local read-only são contratos implementados e cobertos por teste. Ainda não há consumidor web público nem URL pública do MVP; portanto, esta parte não deve ser apresentada como deploy/integração em produção.
- **Agendamento:** o fluxo suporta execução diária e o workflow de Actions só roda no schedule com `BL_PRODUCTION_ENABLED=true` e caminhos configurados para o feed atualizado da Visão. O snapshot de demonstração não deve ser usado como fonte diária de produção.
- **Dados de demonstração:** áreas/cadastro sem localização individual são simulados. A amostra de saída da Visão representa imagens de teste, não inspeções georreferenciadas em campo.
