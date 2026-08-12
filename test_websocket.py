"""
Passo 06 - Teste do WebSocket server
Rode: .venv/Scripts/python.exe -u test_websocket.py
"""
import asyncio
import json
import sys
import time
import websockets

from shared.ports import ENGINE_HOST, ENGINE_PORT

SERVER = f"ws://{ENGINE_HOST}:{ENGINE_PORT}/ws"
SEG_COUNT = 0
last_vad = ""


def fmt_msg(msg: dict):
    global SEG_COUNT, last_vad
    t = msg.get("type")

    if t == "status":
        state = msg["data"]["state"]
        device = msg["data"].get("device", "")
        print(f"[STATUS] {state.upper()}" + (f" | {device}" if device else ""), flush=True)

    elif t == "vad":
        speech = msg["data"]["speech"]
        score  = msg["data"]["score"]
        label  = "VOZ" if speech else "..."
        line   = f"[VAD] {label} {score:.3f}"
        if line != last_vad:          # so imprime quando muda estado
            print(line, flush=True)
            last_vad = line

    elif t == "subtitle":
        SEG_COUNT += 1
        d = msg["data"]
        proc_ms = d.get("processingMs", 0)
        print("", flush=True)
        print(f"[{SEG_COUNT}] +{proc_ms}ms ----------------------------------------", flush=True)
        print(f"  EN: {d['sourceText']}", flush=True)
        print(f"  PT: {d['translatedText']}", flush=True)
        print("-" * 55, flush=True)

    elif t == "pong":
        print(f"[PONG] {msg['ts']:.0f}", flush=True)


async def main():
    print("=" * 55, flush=True)
    print("  WhisperBridge - Passo 06: WebSocket ao vivo", flush=True)
    print("=" * 55, flush=True)
    print(f"Conectando em {SERVER}...", flush=True)

    try:
        async with websockets.connect(SERVER) as ws:
            print("Conectado!", flush=True)

            await ws.send(json.dumps({"type": "ping"}))

            msg = json.loads(await ws.recv())
            fmt_msg(msg)
            msg = json.loads(await ws.recv())
            fmt_msg(msg)

            print("Enviando START...", flush=True)
            await ws.send(json.dumps({"type": "start"}))
            print("Aguardando legendas (audio em ingles reproduzindo?)...\n", flush=True)

            start = time.time()
            async for raw in ws:
                fmt_msg(json.loads(raw))
                if time.time() - start > 90:
                    await ws.send(json.dumps({"type": "stop"}))
                    break

    except ConnectionRefusedError:
        print("ERRO: servidor nao esta rodando.", flush=True)
        print("Inicie: .venv/Scripts/python.exe run_server.py", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass

    print(f"\nTotal legendas recebidas: {SEG_COUNT}", flush=True)
    if SEG_COUNT > 0:
        print("WEBSOCKET OK - pronto para o Passo 07 (frontend Tauri)", flush=True)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
