# Reinstala o atalho WhisperBridge na Area de Trabalho (silencioso, sem terminal)
$here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$proj = (Resolve-Path (Join-Path $here "..\..")).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$srcIco = Join-Path $proj "assets\brand\whisperbridge.ico"
$deskIco = Join-Path $desktop "WhisperBridge-app.ico"
$vbs = Join-Path $proj "WhisperBridge.vbs"
$lnkPath = Join-Path $desktop "WhisperBridge.lnk"

if (-not (Test-Path $srcIco)) { Write-Host "ERRO: $srcIco nao encontrado" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $vbs)) { Write-Host "ERRO: $vbs nao encontrado" -ForegroundColor Red; exit 1 }

Copy-Item $srcIco $deskIco -Force
if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
# wscript = zero janela de console
$sc.TargetPath = "$env:SystemRoot\System32\wscript.exe"
$sc.Arguments = "//nologo `"$vbs`""
$sc.WorkingDirectory = $proj
$sc.IconLocation = "$deskIco,0"
$sc.Description = "WhisperBridge - legendas EN-PT local (sem terminal)"
$sc.WindowStyle = 7
$sc.Save()

$rel = Join-Path $proj "apps\desktop\src-tauri\target\release\desktop.exe"
$copy = Join-Path $proj "WhisperBridge-UI.exe"
if (Test-Path $rel) {
    Copy-Item $rel $copy -Force
    Write-Host "UI: $copy" -ForegroundColor DarkGray
}

Write-Host "Atalho: $lnkPath" -ForegroundColor Green
Write-Host "Icone:  $deskIco" -ForegroundColor Green
Write-Host "Duplo clique em WhisperBridge - sem janela preta." -ForegroundColor Cyan
