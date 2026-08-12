# 10 — Build e Instalador Windows

Empacota o WhisperBridge em um instalador `.exe` que qualquer pessoa pode instalar sem configurar Python ou Node.

---

## Estratégia de distribuição

O app tem duas partes que precisam ser empacotadas juntas:

```
WhisperBridge.exe (Tauri)
    │
    └── inicia automaticamente ao abrir
            │
            ▼
    whisperbridge-engine.exe  (Python empacotado com PyInstaller)
            │
            ├── faster-whisper
            ├── tradução Helsinki
            └── VAD Silero
```

Os modelos de IA são baixados na primeira execução e ficam em `%APPDATA%\WhisperBridge\models`.

---

## 10.1 Empacotar o backend Python com PyInstaller

```powershell
pip install pyinstaller
```

```powershell
pyinstaller `
  --onefile `
  --name whisperbridge-engine `
  --hidden-import faster_whisper `
  --hidden-import transformers `
  --hidden-import silero_vad `
  --hidden-import pyaudiowpatch `
  --hidden-import uvicorn `
  --hidden-import fastapi `
  services/speech_engine/websocket/server.py
```

O executável fica em `dist/whisperbridge-engine.exe`.

---

## 10.2 Iniciar o engine a partir do Tauri

O Tauri pode iniciar e encerrar processos filhos. Adicionar no `src-tauri/src/main.rs`:

```rust
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::State;

struct EngineProcess(Mutex<Option<Child>>);

#[tauri::command]
fn start_engine(state: State<EngineProcess>) {
    let mut process = state.0.lock().unwrap();
    if process.is_none() {
        let child = Command::new("whisperbridge-engine.exe")
            .spawn()
            .expect("Falha ao iniciar engine");
        *process = Some(child);
    }
}

#[tauri::command]
fn stop_engine(state: State<EngineProcess>) {
    let mut process = state.0.lock().unwrap();
    if let Some(mut child) = process.take() {
        child.kill().ok();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(EngineProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![start_engine, stop_engine])
        .run(tauri::generate_context!())
        .expect("Erro ao iniciar WhisperBridge");
}
```

---

## 10.3 Incluir o engine no bundle Tauri

Em `src-tauri/tauri.conf.json`:

```json
{
  "bundle": {
    "active": true,
    "targets": ["nsis"],
    "resources": [
      "../../../dist/whisperbridge-engine.exe"
    ],
    "externalBin": [
      "binaries/whisperbridge-engine"
    ]
  }
}
```

---

## 10.4 Download automático dos modelos

Na primeira execução, verificar se os modelos existem e baixar se necessário:

```python
# services/speech_engine/models/downloader.py

import os
from pathlib import Path
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer

MODELS_DIR = Path(os.getenv("APPDATA", ".")) / "WhisperBridge" / "models"

def ensure_models(whisper_model: str = "medium.en"):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    whisper_path = MODELS_DIR / whisper_model
    if not whisper_path.exists():
        print(f"Baixando Whisper {whisper_model}...")
        WhisperModel(whisper_model, device="cpu", download_root=str(MODELS_DIR))
        print("Whisper pronto")

    translation_path = MODELS_DIR / "opus-mt-tc-big-en-pt"
    if not translation_path.exists():
        print("Baixando modelo de tradução...")
        MarianTokenizer.from_pretrained(
            "Helsinki-NLP/opus-mt-tc-big-en-pt",
            cache_dir=str(MODELS_DIR)
        )
        MarianMTModel.from_pretrained(
            "Helsinki-NLP/opus-mt-tc-big-en-pt",
            cache_dir=str(MODELS_DIR)
        )
        print("Tradução pronta")

    print("Todos os modelos prontos")
```

---

## 10.5 Tela de boas-vindas (primeiro uso)

Quando os modelos não estiverem presentes, mostrar tela de setup no React:

```tsx
// src/components/FirstRunSetup.tsx

interface Props {
  onComplete: () => void;
}

export function FirstRunSetup({ onComplete }: Props) {
  return (
    <div style={{ padding: 24, color: "#fff", background: "rgba(0,0,0,0.9)", borderRadius: 8 }}>
      <h2>Bem-vindo ao WhisperBridge</h2>
      <p>Na primeira execução, os modelos de IA serão baixados (~2 GB).</p>
      <p>Isso leva alguns minutos e só acontece uma vez.</p>
      <ul>
        <li>Whisper medium.en — ~1.5 GB</li>
        <li>Tradução EN→PT — ~300 MB</li>
        <li>VAD Silero — ~1 MB</li>
      </ul>
      <button onClick={onComplete}>Baixar e configurar</button>
    </div>
  );
}
```

---

## 10.6 Gerar o instalador

```powershell
cd apps/desktop
npm run tauri build
```

O instalador NSIS fica em:
```
apps/desktop/src-tauri/target/release/bundle/nsis/WhisperBridge_x.x.x_x64-setup.exe
```

---

## 10.7 Iniciar com o Windows (opcional)

```typescript
// src/hooks/useAutostart.ts
import { enable, disable, isEnabled } from "@tauri-apps/plugin-autostart";

export async function toggleAutostart(enabled: boolean) {
  if (enabled) {
    await enable();
  } else {
    await disable();
  }
}
```

Adicionar o plugin:

```powershell
cargo add tauri-plugin-autostart
npm install @tauri-apps/plugin-autostart
```

---

## 10.8 Checklist de release

- [ ] Engine Python compilado com PyInstaller
- [ ] Modelos baixados e testados
- [ ] Bundle Tauri com engine incluído
- [ ] Tela de primeiro uso testada
- [ ] Atalhos globais funcionando
- [ ] Autostart funcionando
- [ ] Instalador testado em máquina limpa
- [ ] Versão no `tauri.conf.json` atualizada

---

**Próximo passo:** [11-roadmap.md](./11-roadmap.md)
