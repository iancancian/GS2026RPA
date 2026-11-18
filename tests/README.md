# Testes e validação

## Como executar

```powershell
pip install -r requirements.txt
python -m pytest -v        # resultado da última execução: tests/resultado_pytest.txt
```

Os testes são isolados (diretório de saída temporário, sem rede) e usam os dados e previsões de `data/`.

## Cenários cobertos (28 testes)

| Tipo | Cenário | Teste | Evidência de execução real |
|---|---|---|---|
| Sucesso | Tempestade: lista ordenada, rascunhos para equipe e áreas, exportações | `test_pipeline_consume_visao_e_emite_rascunhos_sem_endereco_ficticio` | `logs/exemplo_01_sucesso_tempestade.log`, `assets/exemplo_saida/` |
| Integração | Contrato real de entrada da Visão (action queue + CSV de áreas), validação de schema e aprovação humana obrigatória | `tests/test_vision_integration.py` | `data/samples/vision_action_queue.json` |
| Sucesso | API local read-only (contrato proposto para o MVP; prioridades sinalizam aprovação humana; consumidor web externo ainda não publicado) | `test_api_do_mvp_serve_resultado_do_robo` | `assets/exemplo_saida/prioridades.json` |
| Decisão | Chuva abaixo do limite → nenhuma ação | `test_dia_seco_nao_dispara_alertas`, `test_chuva_baixa_ou_improvavel_nao_aciona` | `logs/exemplo_03_dia_seco_sem_acao.log` |
| Decisão | Níveis ATENÇÃO/ALERTA/EMERGÊNCIA; pico horário aciona | `test_classificar_niveis`, `test_pico_horario_aciona_mesmo_com_total_baixo` | — |
| Decisão | Score, faixas de entupimento, capacidade das equipes, bueiro sem inspeção | `test_classificacao_e_score`, `test_lista_ordenada_capacidade_e_sem_inspecao`, `test_capacidade_limita_bueiros_acionados` | `assets/exemplo_saida/lista_limpeza.csv` |
| Decisão | Idempotência: reexecução não duplica alertas | `test_segunda_execucao_nao_duplica_alertas` | `logs/exemplo_02_idempotencia_reexecucao.log` |
| Falha | API fora do ar: retentativas → cache → falha explícita + aviso de operação | `test_api_com_retentativas_e_falha_final`, `test_fallback_para_cache_e_falha_quando_expirado`, `test_api_fora_sem_cache_registra_falha_e_avisa_operacao` | `logs/exemplo_04_api_fora_do_ar.log` (exit 2) |
| Falha | Arquivo ausente / colunas faltando | `test_arquivo_ausente_e_colunas_faltando`, `test_arquivo_de_inspecoes_ausente_e_falha_explicita` | `logs/exemplo_05_dados_ausentes.log` (exit 3) |
| Falha | Linhas inválidas e duplicadas isoladas sem parar o lote | `test_validacao_rejeita_linhas_invalidas_sem_interromper`, `test_duplicadas_mantem_a_mais_recente` | `assets/exemplo_saida/rejeitados.csv` |
| Falha | Canal de envio fora do ar não bloqueia os demais e é reenviado depois | `test_falha_de_canal_nao_impede_outros_e_nao_marca_como_enviado` | — |
| Segurança | `--dry-run` não envia nem grava; webhook requer aprovação explícita | `test_dry_run_nao_grava_nem_envia`, `test_webhook_exige_aprovacao_humana_explicita` | — |

## Regenerar as evidências

```powershell
powershell -File scripts\gerar_evidencias.ps1   # reexecuta os 5 cenários e atualiza logs/ e assets/
```
