# 08 — Interface Flutuante (Tauri + React)

Janela transparente que fica sempre por cima do Teams e exibe as legendas em português.

---

## 8.1 Criar o projeto Tauri

```powershell
cd C:\Users\abner\Documents\whisperbridge\apps
npm create tauri-app@latest desktop
```

Escolher quando perguntado:
- Package manager: `npm`
- Frontend language: `TypeScript`
- UI template: `React`

```powershell
cd desktop
npm install
```

---

## 8.2 Configurar a janela overlay

Editar `src-tauri/tauri.conf.json`:

```json
{
  "app": {
    "windows": [
      {
        "title": "WhisperBridge",
        "width": 800,
        "height": 160,
        "resizable": true,
        "transparent": true,
        "decorations": false,
        "alwaysOnTop": true,
        "skipTaskbar": true,
        "x": 100,
        "y": 800
      }
    ]
  }
}
```

- `transparent: true` — fundo sem cor
- `decorations: false` — sem barra de título do Windows
- `alwaysOnTop: true` — sempre sobre outras janelas
- `skipTaskbar: true` — não aparece na barra de tarefas

---

## 8.3 Hook de conexão WebSocket

```typescript
// src/hooks/useTranslationSocket.ts

import { useEffect, useRef, useState, useCallback } from "react";

export interface SubtitleSegment {
  id: string;
  sourceText: string;
  translatedText?: string;
  status: "partial" | "translated";
  startedAt: number;
  endedAt?: number;
}

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export function useTranslationSocket(url: string = "ws://localhost:37865/ws") {
  const ws = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [segments, setSegments] = useState<SubtitleSegment[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const connect = useCallback(() => {
    setStatus("connecting");
    ws.current = new WebSocket(url);

    ws.current.onopen = () => setStatus("connected");
    ws.current.onclose = () => setStatus("disconnected");
    ws.current.onerror = () => setStatus("error");

    ws.current.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      if (msg.type === "subtitle") {
        const seg: SubtitleSegment = msg.data;
        setSegments((prev) => {
          const idx = prev.findIndex((s) => s.id === seg.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = seg;
            return next;
          }
          // Manter apenas as últimas 4 frases
          return [...prev.slice(-3), seg];
        });
      }

      if (msg.type === "status") {
        setIsRunning(msg.data.state === "running");
      }
    };
  }, [url]);

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg));
    }
  }, []);

  const start = useCallback(() => send({ type: "start" }), [send]);
  const pause = useCallback(() => send({ type: "pause" }), [send]);
  const stop = useCallback(() => send({ type: "stop" }), [send]);
  const clear = useCallback(() => setSegments([]), []);

  useEffect(() => {
    connect();
    return () => ws.current?.close();
  }, [connect]);

  return { status, segments, isRunning, start, pause, stop, clear };
}
```

---

## 8.4 Componente de legenda

```tsx
// src/components/SubtitleOverlay.tsx

import { SubtitleSegment } from "../hooks/useTranslationSocket";

interface Props {
  segments: SubtitleSegment[];
}

export function SubtitleOverlay({ segments }: Props) {
  const visible = segments.slice(-4);

  return (
    <div
      style={{
        padding: "12px 16px",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      {visible.map((seg) => (
        <div
          key={seg.id}
          style={{
            background:
              seg.status === "partial"
                ? "rgba(0, 0, 0, 0.55)"
                : "rgba(0, 0, 0, 0.80)",
            borderRadius: "6px",
            padding: "8px 14px",
            transition: "background 0.2s",
          }}
        >
          {seg.translatedText ? (
            <span
              style={{
                color: "#ffffff",
                fontSize: "18px",
                fontFamily: "Segoe UI, sans-serif",
                fontWeight: 500,
                lineHeight: 1.4,
                textShadow: "0 1px 3px rgba(0,0,0,0.8)",
              }}
            >
              {seg.translatedText}
            </span>
          ) : (
            <span
              style={{
                color: "rgba(255,255,255,0.55)",
                fontSize: "16px",
                fontFamily: "Segoe UI, sans-serif",
                fontStyle: "italic",
                lineHeight: 1.4,
              }}
            >
              {seg.sourceText}…
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
```

---

## 8.5 App principal

```tsx
// src/App.tsx

import { useTranslationSocket } from "./hooks/useTranslationSocket";
import { SubtitleOverlay } from "./components/SubtitleOverlay";

export default function App() {
  const { status, segments, isRunning, start, pause, stop, clear } =
    useTranslationSocket();

  const connected = status === "connected";

  return (
    <div
      style={{
        width: "100vw",
        minHeight: "100vh",
        background: "transparent",
        userSelect: "none",
      }}
      // Arrastar a janela pela área vazia
      data-tauri-drag-region
    >
      <SubtitleOverlay segments={segments} />

      {/* Barra de controles — aparece ao passar o mouse */}
      <div
        style={{
          position: "fixed",
          bottom: 8,
          right: 8,
          display: "flex",
          gap: "6px",
          opacity: 0.7,
        }}
      >
        {!connected && (
          <span style={{ color: "red", fontSize: 12 }}>desconectado</span>
        )}
        {connected && !isRunning && (
          <button onClick={start} style={btnStyle("#2563eb")}>
            ▶ Iniciar
          </button>
        )}
        {isRunning && (
          <button onClick={pause} style={btnStyle("#d97706")}>
            ⏸ Pausar
          </button>
        )}
        <button onClick={clear} style={btnStyle("#374151")}>
          ✕ Limpar
        </button>
      </div>
    </div>
  );
}

function btnStyle(bg: string): React.CSSProperties {
  return {
    background: bg,
    color: "#fff",
    border: "none",
    borderRadius: 4,
    padding: "4px 10px",
    fontSize: 12,
    cursor: "pointer",
  };
}
```

---

## 8.6 Rodar em desenvolvimento

Dois terminais:

**Terminal 1 — backend:**
```powershell
cd C:\Users\abner\Documents\whisperbridge
.\.venv\Scripts\Activate.ps1
python -m services.speech_engine.websocket.server
```

**Terminal 2 — frontend:**
```powershell
cd C:\Users\abner\Documents\whisperbridge\apps\desktop
npm run tauri dev
```

---

## 8.7 Atalhos de teclado globais

Adicionar no `src-tauri/src/main.rs` para atalhos que funcionam mesmo com o Teams em foco:

```rust
use tauri_plugin_global_shortcut::{Code, Modifiers, ShortcutState};

// Ctrl+Shift+T — iniciar/pausar
// Ctrl+Shift+C — limpar legendas
```

Adicionar o plugin:

```powershell
cargo add tauri-plugin-global-shortcut
```

---

**Próximo passo:** [09-gpu-optimization.md](./09-gpu-optimization.md)
