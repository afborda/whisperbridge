# WhisperBridge - doctor + instalador.
#
#   .\Doctor.ps1           só verifica (não instala nada)
#   .\Doctor.ps1 -Fix      instala o que falta (Python/Node via winget, depois setup.ps1)
#   .\Doctor.ps1 -Menu     menu para quem deu duplo clique no Instalar.bat
#
# Mostra o que a máquina aguenta (os 4 modos) e como abrir o app.

param(
    [switch]$Fix,
    [switch]$Menu,
    [switch]$Cpu,
    [switch]$Overlay,
    [switch]$Speakers
)

$ErrorActionPreference = "Continue"
$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$venv = Join-Path $root ".venv"
$vpy  = Join-Path $venv "Scripts\python.exe"
$dist = Join-Path $root "apps\desktop\dist\index.html"
$envF = Join-Path $root ".env"

function Titulo($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Ok($m)     { Write-Host "  OK   $m" -ForegroundColor Green }
function Falha($m)  { Write-Host "  X    $m" -ForegroundColor Red }
function Aviso($m)  { Write-Host "  !    $m" -ForegroundColor Yellow }
function Info($m)   { Write-Host "       $m" -ForegroundColor DarkGray }

function Tem-Cmd($nome) { [bool](Get-Command $nome -ErrorAction SilentlyContinue) }

function Get-Python {
    foreach ($c in @("python", "py")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $ver = & $cmd.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($ver -match '^\d+\.\d+$') {
            return [pscustomobject]@{ Exe = $cmd.Source; Ver = [version]$ver }
        }
    }
    return $null
}

function Try-WingetInstall($id, $label) {
    if (-not (Tem-Cmd "winget")) {
        Aviso "winget nao esta no PATH. Instale $label manualmente."
        return $false
    }
    Info "instalando $label ($id)..."
    & winget install --id $id -e --accept-package-agreements --accept-source-agreements
    return ($LASTEXITCODE -eq 0)
}

# ── menu interativo ──────────────────────────────────────────────────────────
if ($Menu) {
    Write-Host ""
    Write-Host "  WhisperBridge - o que voce quer fazer?" -ForegroundColor White
    Write-Host ""
    Write-Host "    1  So verificar este PC (doctor)"
    Write-Host "    2  Instalar o que falta          (recomendado)"
    Write-Host "    3  Instalar + janela flutuante   (precisa de Rust, ~10 min)"
    Write-Host "    4  Abrir o WhisperBridge agora"
    Write-Host "    5  Sair"
    Write-Host ""
    $esc = Read-Host "  Escolha [2]"
    if (-not $esc) { $esc = "2" }
    switch ($esc) {
        "1" { }
        "2" { $Fix = $true }
        "3" { $Fix = $true; $Overlay = $true }
        "4" {
            $start = Join-Path $root "Start-Browser.ps1"
            if (Test-Path $start) { & $start } else { Falha "Start-Browser.ps1 nao encontrado." }
            exit $LASTEXITCODE
        }
        default { exit 0 }
    }
}

Titulo "WhisperBridge doctor"
Info "pasta: $root"

# ── checagens ────────────────────────────────────────────────────────────────
$faltas = New-Object System.Collections.ArrayList
$avisos = New-Object System.Collections.ArrayList

# Windows
Titulo "1. Computador"
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$ramGb = if ($os) { [math]::Round($os.TotalVisibleMemorySize / 1MB, 1) } else { 0 }
if ($os) { Ok ("Windows {0}  ·  RAM {1} GB" -f $os.Caption.Trim(), $ramGb) }
else { Aviso "Nao consegui ler o Windows." }
if ($ramGb -gt 0 -and $ramGb -lt 8) {
    [void]$avisos.Add("RAM abaixo de 8 GB: o modo rapido na placa pode ficar apertado.")
}

$gpuNome = $null
$vramGb = 0.0
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    $csv = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
    if ($LASTEXITCODE -eq 0 -and $csv) {
        $linha = ($csv | Select-Object -First 1).ToString()
        $partes = $linha -split ","
        $gpuNome = $partes[0].Trim()
        [void][double]::TryParse(($partes[1].Trim() -replace ',', '.'), [ref]$vramGb)
        $vramGb = [math]::Round($vramGb / 1024.0, 1)
        Ok ("GPU NVIDIA: {0}  ·  {1} GB VRAM" -f $gpuNome, $vramGb)
        if ($vramGb -gt 0 -and $vramGb -lt 4) {
            [void]$avisos.Add("VRAM abaixo de 4 GB: prefira 'IA sem placa de video' se o jogo tambem usar a placa.")
        }
    }
}
if (-not $gpuNome) {
    Aviso "Nenhuma GPU NVIDIA visivel (nvidia-smi). Os modos rapidos na placa ficam indisponiveis."
}

# Python
Titulo "2. Programas"
$py = Get-Python
if ($py -and $py.Ver -ge [version]"3.10" -and $py.Ver -lt [version]"3.13") {
    Ok ("Python {0}" -f $py.Ver)
} elseif ($py) {
    Falha ("Python {0} nao serve - precisa 3.10, 3.11 ou 3.12 (nao use 3.13)." -f $py.Ver)
    [void]$faltas.Add("python-versao")
} else {
    Falha "Python nao encontrado."
    [void]$faltas.Add("python")
}

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $nv = & node -v 2>$null
    Ok ("Node.js {0}" -f $nv)
} else {
    Falha "Node.js / npm nao encontrado (preciso para montar a interface)."
    [void]$faltas.Add("node")
}

$rust = Get-Command cargo -ErrorAction SilentlyContinue
if ($rust) { Ok "Rust (cargo) - da para compilar a janela flutuante" }
else { Info "Rust nao instalado - tudo bem; use o navegador. rustup.rs so se quiser overlay." }

# Ambiente do projeto
Titulo "3. Este projeto"
if (Test-Path $vpy) { Ok ".venv pronto" } else { Aviso ".venv ainda nao existe"; [void]$faltas.Add("venv") }

$torchCuda = $null
if (Test-Path $vpy) {
    $tv = & $vpy -c "import torch; print(torch.__version__); print(torch.cuda.is_available())" 2>$null
    if ($LASTEXITCODE -eq 0 -and $tv) {
        $linhas = @($tv)
        $verT = $linhas[0]
        $cuda = $linhas[1]
        $torchCuda = ($cuda -eq "True")
        if ($torchCuda) { Ok ("PyTorch {0} com CUDA" -f $verT) }
        else { Ok ("PyTorch {0} (CPU)" -f $verT); if ($gpuNome) { [void]$avisos.Add("Tem placa NVIDIA mas o torch e CPU. Rode: .\Doctor.ps1 -Fix") } }
    } else {
        Aviso "PyTorch ainda nao instalado no .venv"
        [void]$faltas.Add("torch")
    }
}

if (Test-Path $dist) { Ok "Interface compilada (apps\desktop\dist)" }
else { Aviso "Interface ainda nao compilada"; [void]$faltas.Add("ui") }

if (Test-Path $envF) { Ok ".env existe" }
else { Aviso ".env ainda nao existe (o instalador cria a partir do .env.example)" }

$temGemini = $false
$temLlm = $false
$temHf = $false
if (Test-Path $envF) {
    Get-Content $envF -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_ -match '^\s*GEMINI_API_KEY\s*=\s*\S+') { $temGemini = $true }
        if ($_ -match '^\s*LLM_API_KEY\s*=\s*\S+') { $temLlm = $true }
        if ($_ -match '^\s*HF_TOKEN\s*=\s*\S+') { $temHf = $true }
    }
}
$us = Join-Path $root "user-settings.json"
if (Test-Path $us) {
    try {
        $j = Get-Content $us -Raw | ConvertFrom-Json
        if ($j.gemini_key) { $temGemini = $true }
        if ($j.llm_key) { $temLlm = $true }
    } catch {}
}
$temChaveIa = $temGemini -or $temLlm
if ($temChaveIa) { Ok "Chave de IA encontrada (Gemini ou outra)" }
else { Info "Sem chave de IA - os modos com traducao na nuvem pedem uma no icone de configuracoes" }
if ($temHf) { Ok "HF_TOKEN presente (falantes)" }
else { Info "Sem HF_TOKEN - o app roda, mas nao separa Pessoa 1 / Pessoa 2" }

$overlay = Test-Path (Join-Path $root "WhisperBridge-UI.exe")
if ($overlay) { Ok "Janela flutuante (WhisperBridge-UI.exe)" }
else { Info "Sem overlay compilado - use o navegador (Start-Browser.ps1)" }

# ── niveis ───────────────────────────────────────────────────────────────────
Titulo "4. O que ESTE PC consegue usar"

$podeGpu = [bool]$torchCuda
if (-not $podeGpu -and $gpuNome -and -not (Test-Path $vpy)) { $podeGpu = $true } # ainda nao instalou; potencial

function Linha-Nivel($nome, $ok, $porque) {
    if ($ok) { Write-Host ("  SIM   {0}" -f $nome) -ForegroundColor Green }
    else     { Write-Host ("  NAO   {0}" -f $nome) -ForegroundColor DarkGray }
    Info $porque
}

Linha-Nivel "Neste PC (rapido)" `
    ($podeGpu) `
    $(if ($podeGpu) { "Ouve e traduz neste computador. Ingles -> portugues. Sem internet." } else { "Precisa de GPU NVIDIA + PyTorch CUDA." })

Linha-Nivel "Recomendado (IA)" `
    ($podeGpu -and $temChaveIa) `
    $(if ($podeGpu -and $temChaveIa) { "Melhor traducao. Voce escolhe os idiomas." } `
      elseif ($podeGpu) { "Placa ok. Falta colar a chave da IA no ⚙ (Gemini gratis em aistudio.google.com/apikey)." } `
      else { "Precisa da placa e de uma chave de IA." })

Linha-Nivel "IA sem placa de video" `
    $temChaveIa `
    $(if ($temChaveIa) { "Libera a placa. Ouvir fica mais lento." } else { "Funciona sem NVIDIA, mas precisa da chave da IA." })

Linha-Nivel "Neste PC (sem internet)" `
    $true `
    "Sempre da. Tudo no processador. Mais lento, ingles -> portugues."

# ── consertar ────────────────────────────────────────────────────────────────
if ($Fix) {
    Titulo "5. Instalando o que falta"

    if ($faltas -contains "python" -or $faltas -contains "python-versao") {
        if (Try-WingetInstall "Python.Python.3.12" "Python 3.12") {
            Ok "Python instalado. FECHE este terminal, abra outro e rode .\Doctor.ps1 -Fix de novo (o PATH so atualiza em janela nova)."
            Write-Host ""
            exit 0
        } else {
            Falha "Instale Python 3.12 em https://www.python.org/downloads/  (marque Add python.exe to PATH)"
        }
    }
    if ($faltas -contains "node") {
        if (Try-WingetInstall "OpenJS.NodeJS.LTS" "Node.js LTS") {
            Ok "Node instalado. FECHE este terminal, abra outro e rode .\Doctor.ps1 -Fix de novo."
            Write-Host ""
            exit 0
        } else {
            Falha "Instale Node LTS em https://nodejs.org/"
        }
    }

    $setup = Join-Path $root "setup.ps1"
    if (-not (Test-Path $setup)) { Falha "setup.ps1 nao encontrado."; exit 1 }
    $argsSetup = @()
    if ($Cpu) { $argsSetup += "-Cpu" }
    if ($Overlay) { $argsSetup += "-Overlay" }
    if ($Speakers) { $argsSetup += "-Speakers" }
    Info "chamando setup.ps1 $($argsSetup -join ' ') ..."
    & $setup @argsSetup
    if ($LASTEXITCODE -ne 0) { Falha "setup.ps1 terminou com erro $LASTEXITCODE"; exit $LASTEXITCODE }
}

if ($avisos.Count -gt 0) {
    Titulo "Avisos"
    foreach ($a in $avisos) { Aviso $a }
}

# ── como iniciar ─────────────────────────────────────────────────────────────
Titulo "Como iniciar"
$prontoBase = (Test-Path $vpy) -and (Test-Path $dist)
if (-not $prontoBase -and -not $Fix) {
    Write-Host "  Ainda falta instalar. Rode:" -ForegroundColor Yellow
    Write-Host "      .\Doctor.ps1 -Fix" -ForegroundColor White
    Write-Host "  ou de um duplo clique em  Instalar.bat" -ForegroundColor White
} else {
    Write-Host "  1. Duplo clique em   Start-Browser.ps1     (navegador, mais simples)" -ForegroundColor White
    if (Test-Path (Join-Path $root "WhisperBridge-UI.exe")) {
        Write-Host "  2. Ou duplo clique em  WhisperBridge.bat     (janela flutuante)" -ForegroundColor White
    } else {
        Write-Host "  2. Janela flutuante:  .\Doctor.ps1 -Fix -Overlay" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "  Na tela: escolha Som do PC ou Microfone  ->  Iniciar" -ForegroundColor DarkGray
    Write-Host "  Modo Recomendado (IA): abra Configuracoes, cole a chave, escolha os idiomas." -ForegroundColor DarkGray
    Write-Host "  Nao use o X se quiser deixar o motor rodando - minimize." -ForegroundColor DarkGray
}

Write-Host ""
if (-not $Fix -and $faltas.Count -gt 0) {
    Write-Host "  Proximo passo:  .\Doctor.ps1 -Fix" -ForegroundColor Cyan
    Write-Host ""
}
exit 0
