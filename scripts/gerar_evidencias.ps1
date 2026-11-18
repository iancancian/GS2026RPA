# Regenera as evidências (logs/exemplo_*.log e assets/exemplo_saida/) executando os 5 cenários de teste.
# Uso (na raiz do projeto): powershell -File scripts\gerar_evidencias.ps1
$ErrorActionPreference = "Continue"
$env:PYTHONPATH = "src"; $env:PYTHONUTF8 = "1"
$tmp = Join-Path $env:TEMP "bl_evidencias"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force logs, assets\exemplo_saida | Out-Null

function Invoke-Cenario($nome, $saida, $argumentos, $esperado) {
    $env:BL_OUTPUT_DIR = Join-Path $tmp $saida
    $env:BL_LOG_DIR = Join-Path $tmp "log_$nome"
    python -m bocadelobo executar @argumentos 2>$null | Out-Null
    $codigo = $LASTEXITCODE
    Copy-Item (Join-Path $env:BL_LOG_DIR "bocadelobo.log") "logs\exemplo_$nome.log" -Force
    "{0}: exit={1} (esperado {2})" -f $nome, $codigo, $esperado
}

$agora = "2026-11-17T09:00:00+00:00"
$tempestade = @("--previsao-arquivo", "data\samples\previsao_tempestade.json")
$seco = @("--previsao-arquivo", "data\samples\previsao_seco.json")
$visao = @("--visao-action-queue", "data\samples\vision_action_queue.json", "--visao-areas", "data\samples\areas_risco_visao.csv")

Invoke-Cenario "01_sucesso_tempestade" "ok" ($visao + $tempestade + @("--agora", $agora)) 0
foreach ($f in "prioridades.json", "lista_limpeza.csv", "rejeitados.csv", "outbox_alertas.jsonl") {
    Copy-Item (Join-Path $tmp "ok\$f") assets\exemplo_saida\ -Force
}
Invoke-Cenario "02_idempotencia_reexecucao" "ok" ($visao + $tempestade + @("--agora", "2026-11-17T09:30:00+00:00")) 0
Invoke-Cenario "03_dia_seco_sem_acao" "seco" ($visao + $seco + @("--agora", $agora)) 0

$env:HTTPS_PROXY = "http://127.0.0.1:9"   # simula API fora do ar
Invoke-Cenario "04_api_fora_do_ar" "falha_api" @("--agora", $agora) 2
Remove-Item Env:HTTPS_PROXY

$env:BL_DATA_DIR = Join-Path $tmp "dados_vazios"   # simula arquivos de entrada ausentes
New-Item -ItemType Directory -Force $env:BL_DATA_DIR | Out-Null
Invoke-Cenario "05_dados_ausentes" "falha_dados" ($tempestade + @("--agora", $agora)) 3
Remove-Item Env:BL_DATA_DIR
