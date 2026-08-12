# WhisperBridge — instalador.
#
# Objetivo: sair do "git clone" para legenda na tela sem a pessoa precisar saber
# nada sobre torch, CUDA ou Tauri.
#
#   .\setup.ps1              detecta a máquina e instala o que der
#   .\setup.ps1 -Cpu         força CPU mesmo tendo placa NVIDIA
#   .\setup.ps1 -Overlay     também compila a janela flutuante (precisa de Rust)
#
# É seguro rodar de novo: cada etapa detecta o que já está pronto e pula.

param(
    [switch]$Cpu,
    [switch]$Overlay,
    [switch]$Speakers
)

$ErrorActionPreference = "Stop"
$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$venv = Join-Path $root ".venv"
$vpy = Join-Path $venv "Scripts\python.exe"
$desktop = Join-Path $root "apps\desktop"

$avisos = New-Object System.Collections.ArrayList

function Passo($n) { Write-Host "`n[$n]" -ForegroundColor Cyan }
function Ok($m) { Write-Host "  OK  $m" -ForegroundColor Green }
function Info($m) { Write-Host "      $m" -ForegroundColor DarkGray }
function Aviso($m) {
    Write-Host "  !   $m" -ForegroundColor Yellow
    [void]$avisos.Add($m)
}
function Morre($m) {
    Write-Host "`n  X   $m`n" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== WhisperBridge — instalacao ===" -ForegroundColor White

# ── 1. Python ────────────────────────────────────────────────────────────────
Passo "1/6  Python"
$pyExe = $null
foreach ($cand in @("python", "py")) {
    $c = Get-Command $cand -ErrorAction SilentlyContinue
    if ($c) { $pyExe = $c.Source; break }
}
if (-not $pyExe) { Morre "Python nao encontrado. Instale 3.10, 3.11 ou 3.12 de python.org e marque 'Add to PATH'." }

$verRaw = & $pyExe -c "import sys; print('%d.%d' % sys.version_info[:2])"
$ver = [version]$verRaw
# Limite de cima real: o torch 2.5.1 nao publica wheel para 3.13.
if ($ver -lt [version]"3.10" -or $ver -ge [version]"3.13") {
    Morre "Python $verRaw nao serve. O torch 2.5.1 (exigido pelo CTranslate2) so tem wheel para 3.10-3.12."
}
Ok "Python $verRaw"

# ── 2. Ambiente virtual ──────────────────────────────────────────────────────
Passo "2/6  Ambiente virtual"
if (Test-Path $vpy) {
    Ok ".venv ja existe"
} else {
    Info "criando .venv..."
    & $pyExe -m venv $venv
    if (-not (Test-Path $vpy)) { Morre "Falhou ao criar o .venv." }
    Ok ".venv criado"
}
& $vpy -m pip install --upgrade pip --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Aviso "Nao consegui atualizar o pip; seguindo com a versao atual." }

# ── 3. PyTorch (a etapa que decide se a GPU vai funcionar) ───────────────────
Passo "3/6  PyTorch"
$temGpu = $false
if (-not $Cpu) {
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        $gpuNome = & nvidia-smi --query-gpu=name --format=csv,noheader
        if ($LASTEXITCODE -eq 0 -and $gpuNome) {
            $temGpu = $true
            Info "placa detectada: $($gpuNome | Select-Object -First 1)"
        }
    }
}

$jaTem = & $vpy -c "try:`n import torch`n print(torch.__version__)`nexcept Exception:`n print('')"
if ($jaTem -and $jaTem.Trim()) {
    Ok "torch $($jaTem.Trim()) ja instalado"
} else {
    if ($temGpu) {
        Info "instalando build CUDA 12.1 (~2.5 GB, demora)..."
        & $vpy -m pip install "torch==2.5.1+cu121" "torchaudio==2.5.1+cu121" --index-url https://download.pytorch.org/whl/cu121 --disable-pip-version-check
    } else {
        Info "instalando build CPU (~200 MB)..."
        & $vpy -m pip install "torch==2.5.1" "torchaudio==2.5.1" --index-url https://download.pytorch.org/whl/cpu --disable-pip-version-check
        Aviso "Sem build CUDA: os perfis 'GPU total' e 'GPU + nuvem' vao aparecer bloqueados."
    }
    if ($LASTEXITCODE -ne 0) { Morre "Falhou instalando o torch." }
    Ok "torch instalado"
}

# ── 4. Resto das dependencias ────────────────────────────────────────────────
Passo "4/6  Dependencias Python"
# ARMADILHA, ja testada na pratica: o pip le o "+cu121" como versao LOCAL e
# considera qualquer torch do PyPI mais novo. Como silero-vad e pyannote pedem
# so "torch>=1.12", um pip install comum DESINSTALA a build CUDA e poe a CPU no
# lugar, sem erro nenhum — o instalador termina "com sucesso" e os perfis de GPU
# aparecem bloqueados. O constraints congela o que ja esta instalado.
$pins = Join-Path $env:TEMP "whisperbridge-constraints.txt"
& $vpy -c @"
import importlib
linhas = []
for nome in ('torch', 'torchaudio', 'torchvision'):
    try:
        linhas.append('%s==%s' % (nome, importlib.import_module(nome).__version__))
    except Exception:
        pass
open(r'$pins', 'w').write('\n'.join(linhas) + '\n')
"@
if ($LASTEXITCODE -ne 0) { Morre "Nao consegui descobrir a versao do torch instalada." }
Info "travando: $((Get-Content $pins) -join ', ')"

& $vpy -m pip install -r (Join-Path $root "requirements.txt") --constraint $pins --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Morre "Falhou instalando as dependencias de requirements.txt." }
# Identificacao de falantes: opcional e instalada a parte porque o pyannote 4.0.7
# pede torch>=2.8 enquanto o projeto roda em 2.5.1. --no-deps aplica so ao
# pyannote (que e quem mente sobre o torch); as dependencias dele entram pelo
# caminho normal, sem nenhuma que force o torch.
if ($Speakers) {
    Info "instalando identificacao de falantes (pyannote)..."
    & $vpy -m pip install "pyannote.audio==4.0.7" --no-deps --constraint $pins --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Aviso "pyannote falhou; o app roda sem separar falantes."
    } else {
        & $vpy -m pip install asteroid-filterbanks einops lightning matplotlib rich `
            pyannote-core pyannote-database pyannote-metrics pyannote-pipeline pyannoteai-sdk `
            pytorch-metric-learning torch-audiomentations torchcodec torchmetrics `
            "opentelemetry-api>=1.34.0" "opentelemetry-sdk>=1.34.0" "opentelemetry-exporter-otlp>=1.34.0" `
            --constraint $pins --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { Aviso "Dependencias do pyannote falharam; falantes desativados." }
        else { Ok "identificacao de falantes instalada (precisa de HF_TOKEN no .env)" }
    }
}

$cudaOk = & $vpy -c "import torch; print(torch.cuda.is_available())"
Ok "dependencias instaladas  (torch.cuda.is_available() = $($cudaOk.Trim()))"
if ($temGpu -and $cudaOk.Trim() -ne "True") {
    Aviso "A placa existe mas o torch nao a enxerga — provavelmente a build CPU ficou instalada. Rode: .venv\Scripts\python.exe -m pip uninstall -y torch torchaudio  e repita este script."
}

# ── 5. Configuracao (.env) ───────────────────────────────────────────────────
Passo "5/6  Configuracao"
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Ok ".env ja existe (nao mexi nele)"
} else {
    Copy-Item (Join-Path $root ".env.example") $envFile
    Ok ".env criado a partir do .env.example"
    Info "Ele funciona vazio: o perfil padrao roda 100% local e de graca."
    Info "Preencha GEMINI_API_KEY so se quiser a revisao por IA na nuvem."
    Info "Preencha HF_TOKEN so se quiser separar 'Pessoa 1 / Pessoa 2'."
}

# ── 6. Interface ─────────────────────────────────────────────────────────────
Passo "6/6  Interface"
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Aviso "npm nao encontrado. Sem ele NAO ha interface — o engine sobe mas serve uma pagina vazia. Instale o Node LTS em nodejs.org e rode este script de novo."
} else {
    Push-Location $desktop
    try {
        if (Test-Path (Join-Path $desktop "node_modules")) {
            Info "node_modules ja existe"
        } else {
            Info "npm install..."
            & npm install --silent
            if ($LASTEXITCODE -ne 0) { throw "npm install falhou" }
        }
        Info "compilando a interface..."
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build falhou" }
        Ok "interface compilada em apps\desktop\dist"

        if ($Overlay) {
            $cargo = Get-Command cargo -ErrorAction SilentlyContinue
            if (-not $cargo) {
                Aviso "-Overlay pedido mas o Rust nao esta instalado (rustup.rs). Pulando; use o modo navegador."
            } else {
                Info "compilando a janela flutuante (demora ~10 min na primeira vez)..."
                & npm run tauri build
                if ($LASTEXITCODE -ne 0) {
                    Aviso "A compilacao do overlay falhou. O modo navegador continua funcionando."
                } else {
                    foreach ($n in @("WhisperBridge.exe", "desktop.exe")) {
                        $exe = Join-Path $desktop "src-tauri\target\release\$n"
                        if (Test-Path $exe) {
                            Copy-Item $exe (Join-Path $root "WhisperBridge-UI.exe") -Force
                            Ok "janela flutuante pronta: WhisperBridge-UI.exe"
                            break
                        }
                    }
                }
            }
        }
    } catch {
        Aviso "$_"
    } finally {
        Pop-Location
    }
}

# ── Resumo ───────────────────────────────────────────────────────────────────
Write-Host "`n=== Perfis que vao estar disponiveis ===" -ForegroundColor White
$resumo = & $vpy -c @"
import os, sys
sys.path.insert(0, r'$root')
from dotenv import load_dotenv
load_dotenv(os.path.join(r'$root', '.env'))
import shared.profiles as p
for d in p.list_profiles():
    marca = 'sim' if d['available'] else 'NAO'
    motivo = '' if d['available'] else '  (' + d['unavailable_reason'] + ')'
    print('  %-4s %-16s %s%s' % (marca, d['id'], d['description'][:44], motivo))
"@
if ($LASTEXITCODE -eq 0) { $resumo | ForEach-Object { Write-Host $_ } }
else { Aviso "Nao consegui listar os perfis." }
if (-not $Speakers) {
    Info ""
    Info "Falantes ('Pessoa 1 / Pessoa 2') desativados. Para ligar: .\setup.ps1 -Speakers"
}

if ($avisos.Count -gt 0) {
    Write-Host "`n=== Avisos ===" -ForegroundColor Yellow
    foreach ($a in $avisos) { Write-Host "  - $a" -ForegroundColor Yellow }
}

Write-Host "`n=== Pronto. Para usar ===" -ForegroundColor Green
if (Test-Path (Join-Path $root "WhisperBridge-UI.exe")) {
    Write-Host "  .\WhisperBridge.bat            janela flutuante" -ForegroundColor White
}
Write-Host "  .\Start-Browser.ps1            abre no navegador (nao precisa de Rust)" -ForegroundColor White
Write-Host "`n  Toque audio em ingles no PC e clique em Iniciar.`n" -ForegroundColor DarkGray
