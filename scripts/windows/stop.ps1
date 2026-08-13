# Encerra qualquer WhisperBridge preso (servidor + UI).
# Porta do engine: 37865 (ver src/whisperbridge/config/ports.py)

$EnginePort = 37865

Write-Host "Procurando processos WhisperBridge..." -ForegroundColor Cyan

$killed = @()

try {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$EnginePort/shutdown" -TimeoutSec 2 -ErrorAction Stop | Out-Null
    Write-Host "  pedi /shutdown ao engine (descarrega VRAM)" -ForegroundColor DarkGray
    Start-Sleep -Milliseconds 500
} catch {}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'run_server\.py' -or
            ($_.Name -match '^python' -and $_.CommandLine -like '*whisperbridge*')
        )
    } |
    ForEach-Object {
        Write-Host "  matando python PID $($_.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed += $_.ProcessId
    }

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^(desktop|WhisperBridge|WhisperBridge-UI)\.exe$' -and
        $_.ExecutablePath -and
        ($_.ExecutablePath -like '*whisperbridge*' -or $_.Name -eq 'WhisperBridge-UI.exe')
    } |
    ForEach-Object {
        Write-Host "  matando UI PID $($_.ProcessId) ($($_.Name))" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $killed += $_.ProcessId
    }

try {
    $conns = Get-NetTCPConnection -LocalPort $EnginePort -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess -and ($killed -notcontains $c.OwningProcess)) {
            Write-Host "  matando processo na porta $EnginePort PID $($c.OwningProcess)" -ForegroundColor Yellow
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            $killed += $c.OwningProcess
        }
    }
} catch {}

Start-Sleep -Milliseconds 300

try {
    $h = Invoke-RestMethod "http://127.0.0.1:$EnginePort/health" -TimeoutSec 1 -ErrorAction Stop
    Write-Host "AVISO: health ainda responde: $($h | ConvertTo-Json -Compress)" -ForegroundColor Red
} catch {
    Write-Host "Porta $EnginePort livre. Tudo limpo." -ForegroundColor Green
}

if ($killed.Count -eq 0) {
    Write-Host "Nada preso encontrado." -ForegroundColor DarkGray
} else {
    Write-Host "Encerrados: $($killed -join ', ')" -ForegroundColor Green
}
