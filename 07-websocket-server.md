# 07 — Servidor WebSocket (FastAPI)

Expõe o pipeline de IA como um serviço local. A interface React se conecta via WebSocket e recebe os eventos de legenda em tempo real.

---

## Por que WebSocket local

O WebSocket permite comunicação bidirecional e de baixa latência entre o backend Python (que tem acesso à GPU e ao áudio) e o frontend React (que renderiza a legenda).

```
Python (GPU + áudio)  ←→  WebSocket (localhost:37865)  ←→  React (overlay)
```

---

## 7.1 Contrato de mensagens

```typescript
// shared/contracts/messages.ts

export type SubtitleStatus = "partial" | "translated";

export interface SubtitleSegment {
  id: string;
  sourceText: string;
  translatedText?: string;
  status: SubtitleStatus;
  startedAt: number;
  endedAt?: number;
}

export type ServerMessage =
  | { type: "subtitle"; data: SubtitleSegment }
  | { type: "status"; data: { state: "running" | "paused" | "stopped" } }
  | { type: "error"; data: { message: string } };

export type ClientMessage =
  | { type: "start" }
  | { type: "pause" }
  | { type: "stop" }
  | { type: "set_model"; data: { model: string } }
  | { type: "ping" };
```

---

## 7.2 Servidor FastAPI + WebSocket

```python
# services/speech-engine/websocket/server.py

import asyncio
import json
import threading
import time
from typing import Set

import numpy as np
import pyaudiowpatch as pyaudio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..pipeline.realtime_pipeline import RealtimePipeline, SubtitleEvent

app = FastAPI(title="WhisperBridge Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # apenas localhost em produção
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        disconnected = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        self.active -= disconnected

manager = ConnectionManager()
pipeline: RealtimePipeline | None = None
audio_thread_handle: threading.Thread | None = None
is_running = False

async def on_subtitle_event(event: SubtitleEvent):
    message = {
        "type": "subtitle",
        "data": {
            "id": event.segment_id,
            "sourceText": event.source_text,
            "translatedText": event.translated_text,
            "status": event.status,
            "startedAt": event.started_at,
            "endedAt": event.ended_at,
        },
    }
    await manager.broadcast(message)

def run_audio_capture(loop: asyncio.AbstractEventLoop):
    global is_running

    p = pyaudio.PyAudio()
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

    loopback = None
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev["name"] == default_output["name"] and dev["isLoopbackDevice"]:
            loopback = dev
            break

    if not loopback:
        return

    stream = p.open(
        format=pyaudio.paFloat32,
        channels=loopback["maxInputChannels"],
        rate=int(loopback["defaultSampleRate"]),
        input=True,
        input_device_index=loopback["index"],
        frames_per_buffer=8000,
    )

    while is_running:
        data = stream.read(8000, exception_on_overflow=False)
        audio = np.frombuffer(data, dtype=np.float32)

        if loopback["maxInputChannels"] > 1:
            audio = audio.reshape(-1, loopback["maxInputChannels"]).mean(axis=1)

        pipeline.process_chunk(audio)

    stream.stop_stream()
    stream.close()
    p.terminate()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global pipeline, audio_thread_handle, is_running

    await manager.connect(ws)

    # Inicializa pipeline na primeira conexão
    if pipeline is None:
        loop = asyncio.get_event_loop()
        pipeline = RealtimePipeline(on_event=on_subtitle_event)
        pipeline.start(loop)

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg["type"] == "start" and not is_running:
                is_running = True
                loop = asyncio.get_event_loop()
                audio_thread_handle = threading.Thread(
                    target=run_audio_capture, args=(loop,), daemon=True
                )
                audio_thread_handle.start()
                await manager.broadcast({"type": "status", "data": {"state": "running"}})

            elif msg["type"] == "pause":
                is_running = False
                await manager.broadcast({"type": "status", "data": {"state": "paused"}})

            elif msg["type"] == "stop":
                is_running = False
                await manager.broadcast({"type": "status", "data": {"state": "stopped"}})

            elif msg["type"] == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(ws)

@app.get("/health")
def health():
    return {"status": "ok", "running": is_running, "timestamp": time.time()}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=37865, log_level="info")
```

---

## 7.3 Iniciar o servidor

```powershell
cd C:\Users\abner\Documents\whisperbridge
.\.venv\Scripts\Activate.ps1
python -m services.speech-engine.websocket.server
```

Ou diretamente:

```powershell
uvicorn services.speech_engine.websocket.server:app --host 127.0.0.1 --port 37865
```

---

## 7.4 Testar o WebSocket manualmente

```powershell
# Instalar wscat para teste rápido
npm install -g wscat

# Conectar
wscat -c ws://localhost:37865/ws
```

Depois de conectado, enviar:

```json
{"type": "start"}
```

E aguardar as mensagens de legenda chegando:

```json
{"type":"subtitle","data":{"id":"seg-1","sourceText":"We need to review","translatedText":null,"status":"partial","startedAt":1722950000.0}}
{"type":"subtitle","data":{"id":"seg-1","sourceText":"We need to review the dashboard filters.","translatedText":"Precisamos revisar os filtros do dashboard.","status":"translated","startedAt":1722950000.0,"endedAt":1722950004.2}}
```

---

## 7.5 Verificar saúde do serviço

```powershell
Invoke-RestMethod http://localhost:37865/health
```

```json
{"status":"ok","running":true,"timestamp":1722950010.5}
```

---

**Próximo passo:** [08-frontend-overlay.md](./08-frontend-overlay.md)
