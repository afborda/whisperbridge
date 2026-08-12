# WhisperBridge Launcher (silencioso)
# 1) Sobe o engine (HTTP + UI estatica na porta 37865) — responde na hora
# 2) Espera /health (loading ou ok)
# 3) Abre o WebView apontando para http://127.0.0.1:37865/ (sem Vite/localhost dev)
# Log: %TEMP%\WhisperBridge-launch.log

param(
    [switch]$Dev,
    [switch]$ShowConsole
)

$ErrorActionPreference = "Continue"
$root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$python = Join-Path $root ".venv\Scripts\python.exe"
$server = Join-Path $root "run_server.py"
$desktopDir = Join-Path $root "apps\desktop"
$EnginePort = 37865
$EngineHealth = "http://127.0.0.1:$EnginePort/health"
$releaseCandidates = @(
    (Join-Path $root "WhisperBridge-UI.exe"),
    (Join-Path $desktopDir "src-tauri\target\release\WhisperBridge.exe"),
    (Join-Path $desktopDir "src-tauri\target\release\desktop.exe")
)
$releaseExe = $releaseCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
$logFile = Join-Path $env:TEMP "WhisperBridge-launch.log"

function Write-Log([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "[$ts] $Message" -Encoding UTF8
    if ($ShowConsole) { Write-Host $Message }
}

function Show-UserError([string]$Message) {
    Write-Log "ERRO: $Message"
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
        [System.Windows.Forms.MessageBox]::Show(
            $Message, "WhisperBridge",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } catch {
        if ($ShowConsole) { Write-Host $Message -ForegroundColor Red; Read-Host "Enter" }
    }
}

function Stop-WhisperBridgeAll {
    param($ServerProc, $UiProc)
    Write-Log "Encerrando processos..."
    if ($UiProc -and -not $UiProc.HasExited) {
        try { & taskkill.exe /PID $UiProc.Id /T /F 2>$null | Out-Null } catch {}
    }
    # pede ao engine para descarregar a VRAM antes do kill bruto
    try {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$EnginePort/shutdown" -TimeoutSec 2 -ErrorAction Stop | Out-Null
        Start-Sleep -Milliseconds 400
    } catch {}
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(desktop|WhisperBridge|WhisperBridge-UI)\.exe$' -and
            $_.ExecutablePath -and
            ($_.ExecutablePath -like "*whisperbridge*" -or $_.Name -eq "WhisperBridge-UI.exe")
        } |
        ForEach-Object {
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'run_server\.py' -or
                ($_.Name -match '^python' -and $_.CommandLine -like "*whisperbridge*")
            )
        } |
        ForEach-Object {
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
    if ($ServerProc -and -not $ServerProc.HasExited) {
        try { & taskkill.exe /PID $ServerProc.Id /T /F 2>$null | Out-Null } catch {}
        try { Stop-Process -Id $ServerProc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    Start-Sleep -Milliseconds 300
    foreach ($port in @($EnginePort, 8765)) {
        try {
            Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                ForEach-Object {
                    if ($_.OwningProcess) {
                        try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
                    }
                }
        } catch {}
    }
}

# Se o PowerShell morrer (fechar o console no X), o Job Object mata o Python.
# Sem isto o engine fica órfão com ~3 GB na placa.
function New-KillOnCloseJob {
    try {
        Add-Type -TypeDefinition @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
public class WbJob : IDisposable {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr CreateJobObject(IntPtr a, string n);
    [DllImport("kernel32.dll")]
    static extern bool SetInformationJobObject(IntPtr h, int t, IntPtr p, uint l);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr j, IntPtr p);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr h);
    [StructLayout(LayoutKind.Sequential)]
    struct IO_COUNTERS {
        public ulong a,b,c,d,e,f;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    IntPtr handle;
    public WbJob() {
        handle = CreateJobObject(IntPtr.Zero, null);
        var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = 0x2000; // KILL_ON_JOB_CLOSE
        int len = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr ptr = Marshal.AllocHGlobal(len);
        Marshal.StructureToPtr(info, ptr, false);
        SetInformationJobObject(handle, 9, ptr, (uint)len);
        Marshal.FreeHGlobal(ptr);
    }
    public bool Add(int pid) {
        try {
            using (var p = Process.GetProcessById(pid))
                return AssignProcessToJobObject(handle, p.Handle);
        } catch { return false; }
    }
    public void Dispose() { if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; } }
}
"@ -ErrorAction Stop
        return New-Object WbJob
    } catch {
        Write-Log "Job Object indisponivel: $_"
        return $null
    }
}

"" | Set-Content -Path $logFile -Encoding UTF8
Write-Log "=== WhisperBridge launch ==="
Write-Log "root=$root release=$releaseExe port=$EnginePort"

if (-not (Test-Path -LiteralPath $python)) {
    Show-UserError "Python (.venv) nao encontrado."
    exit 1
}
if (-not (Test-Path -LiteralPath $server)) {
    Show-UserError "run_server.py nao encontrado."
    exit 1
}
if (-not $Dev -and -not $releaseExe) {
    Show-UserError "Interface RELEASE nao encontrada.`nRode: cd apps\desktop && npm.cmd run tauri build"
    exit 1
}

Stop-WhisperBridgeAll $null $null
Start-Sleep -Milliseconds 400

$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:TOKENIZERS_PARALLELISM = "false"
$env:PYTHONWARNINGS = "ignore"

# ── 1) Engine primeiro (serve a UI em / e o API) ──────────────────────────────
Write-Log "Iniciando engine (HTTP+UI na porta $EnginePort)..."
$winStyle = if ($ShowConsole) { "Minimized" } else { "Hidden" }
try {
    $serverProc = Start-Process `
        -FilePath $python `
        -ArgumentList @("-u", $server) `
        -WorkingDirectory $root `
        -PassThru `
        -WindowStyle $winStyle `
        -ErrorAction Stop
} catch {
    Show-UserError "Falha ao iniciar o engine:`n$_"
    exit 1
}
Write-Log "Engine PID=$($serverProc.Id)"

# Espera o HTTP responder (status loading ou ok) — NÃO espera modelos inteiros
$httpUp = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Milliseconds 500
    if ($serverProc.HasExited) {
        Show-UserError "O engine encerrou cedo (exit $($serverProc.ExitCode)).`nLog: $logFile"
        exit 1
    }
    try {
        $r = Invoke-RestMethod $EngineHealth -TimeoutSec 2 -ErrorAction Stop
        if ($r.status -eq "ok" -or $r.status -eq "loading") {
            $httpUp = $true
            Write-Log "HTTP up status=$($r.status)"
            break
        }
        if ($r.status -eq "error") {
            Show-UserError "Engine com erro ao carregar modelos:`n$($r.error)"
            Stop-WhisperBridgeAll $serverProc $null
            exit 1
        }
    } catch {}
}

if (-not $httpUp) {
    Show-UserError "Engine nao respondeu em http://127.0.0.1:$EnginePort`nLog: $logFile"
    Stop-WhisperBridgeAll $serverProc $null
    exit 1
}

# ── 2) UI WebView -> porta do engine (nunca Vite/localhost dev) ───────────────
$uiProc = $null
$mode = "release"

if ($Dev) {
    $npmCmd = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
    if (-not (Test-Path $npmCmd)) {
        Show-UserError "npm.cmd nao encontrado."
        Stop-WhisperBridgeAll $serverProc $null
        exit 1
    }
    $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
    Write-Log "Modo DEV (tauri + vite)..."
    $uiProc = Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
        -ArgumentList @("/c", "`"$npmCmd`" run tauri dev") `
        -WorkingDirectory $desktopDir -PassThru -WindowStyle Hidden
    $mode = "dev"
} else {
    Write-Log "Abrindo UI -> $EngineHealth base http://127.0.0.1:$EnginePort/"
    try {
        $uiProc = Start-Process -FilePath $releaseExe `
            -WorkingDirectory (Split-Path $releaseExe) `
            -PassThru -ErrorAction Stop
    } catch {
        Show-UserError "Falha ao abrir a interface:`n$_"
        Stop-WhisperBridgeAll $serverProc $null
        exit 1
    }
}

Start-Sleep -Seconds 2
if ($mode -eq "release" -and $uiProc.HasExited) {
    Show-UserError "A interface fechou na hora.`nTente: winget install Microsoft.EdgeWebView2Runtime"
    Stop-WhisperBridgeAll $serverProc $uiProc
    exit 1
}

$job = New-KillOnCloseJob
if ($job) {
    if ($serverProc -and -not $serverProc.HasExited) { [void]$job.Add($serverProc.Id) }
    if ($uiProc -and -not $uiProc.HasExited) { [void]$job.Add($uiProc.Id) }
    Write-Log "Job Object: filhos morrem se o launcher cair"
}

Write-Log "Aberto (modo $mode). Feche a janela para encerrar."

try {
    if ($mode -eq "release") {
        $uiProc.WaitForExit()
    } else {
        $deadline = (Get-Date).AddMinutes(15)
        $appProc = $null
        while ((Get-Date) -lt $deadline) {
            $appProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Name -eq "desktop.exe" -and
                    $_.ExecutablePath -like "*whisperbridge*"
                } | Select-Object -First 1
            if ($appProc) { break }
            if ($uiProc.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
        if ($appProc) {
            try { Wait-Process -Id $appProc.ProcessId -ErrorAction SilentlyContinue } catch {}
        } elseif ($uiProc -and -not $uiProc.HasExited) {
            $uiProc.WaitForExit()
        }
    }
}
finally {
    Stop-WhisperBridgeAll $serverProc $uiProc
    if ($job) { try { $job.Dispose() } catch {} }
    Write-Log "Fim."
}
