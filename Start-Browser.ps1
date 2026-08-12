# WhisperBridge no navegador — o caminho sem Rust.
#
# O engine ja serve a interface React em / (StaticFiles). O Tauri existe so para
# dar uma janela sem borda e sempre-visivel; nada da aplicacao depende dele. Quem
# nao quer instalar a toolchain do Rust usa isto e tem exatamente as mesmas
# legendas, numa aba do navegador.
#
# Ctrl+C encerra o engine.

$ErrorActionPreference = "Stop"
$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$vpy = Join-Path $root ".venv\Scripts\python.exe"
$porta = 37865
$url = "http://127.0.0.1:$porta/"

if (-not (Test-Path $vpy)) {
    Write-Host "`n  X   .venv nao encontrado. Rode primeiro:  .\setup.ps1`n" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $root "apps\desktop\dist\index.html"))) {
    Write-Host "`n  X   A interface nao foi compilada. Rode:  .\setup.ps1`n" -ForegroundColor Red
    exit 1
}

$emUso = Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue
if ($emUso) {
    Write-Host "Ja existe um engine na porta $porta — abrindo o navegador nele." -ForegroundColor Yellow
    Start-Process $url
    exit 0
}

Write-Host "`nSubindo o engine..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $vpy -ArgumentList "-u", (Join-Path $root "run_server.py") `
    -WorkingDirectory $root -NoNewWindow -PassThru

try {
    # /health responde 'loading' antes dos modelos terminarem: e o suficiente para
    # abrir a aba, porque a propria interface segura a tela de boot ate ficar 'ok'.
    $pronto = $false
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 500
        if ($proc.HasExited) {
            Write-Host "  X   O engine morreu ao subir (codigo $($proc.ExitCode))." -ForegroundColor Red
            exit 1
        }
        try {
            $r = Invoke-RestMethod "$url`health" -TimeoutSec 2
            if ($r.status) { $pronto = $true; break }
        } catch { }
    }
    if (-not $pronto) {
        Write-Host "  X   O engine nao respondeu em 30s." -ForegroundColor Red
        exit 1
    }

    Write-Host "Abrindo $url" -ForegroundColor Green
    Start-Process $url
    Write-Host "`nOs modelos continuam carregando em segundo plano (~30s na primeira vez," -ForegroundColor DarkGray
    Write-Host "que tambem baixa ~1 GB). A aba mostra a tela de carregamento ate ficar pronta." -ForegroundColor DarkGray
    Write-Host "`nCtrl+C encerra.`n" -ForegroundColor DarkGray

    Wait-Process -Id $proc.Id
} finally {
    if (-not $proc.HasExited) {
        Write-Host "`nEncerrando o engine..." -ForegroundColor Cyan
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
