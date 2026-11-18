from pathlib import Path

import os
import struct
import json
import socket
import wave
import time
import uuid
from datetime import datetime, timezone

import qrcode

import numpy as np

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles



BASE_DIR = Path(os.getcwd())
STATIC_DIR = BASE_DIR / "static"
CERT_DIR = BASE_DIR / "certs"
SESSIONS_DIR = BASE_DIR / "sessions"

HEADER = struct.Struct("<Id")

active_session = None

def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"

app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.websocket("/ws")
async def audio_ws(ws: WebSocket):
    global active_session
    last_arrival = time.monotonic()
    await ws.accept()

    if active_session is not None:
        await ws.close(reason="Another session is running.")
        return

    session_id = uuid.uuid4().hex
    active_session = session_id
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = SESSIONS_DIR / f"{started}_{session_id}"
    session_dir.mkdir(parents=True)

    sample_rate = None
    wav = None
    expected_seq = 0
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                print("Websocket disconnected.")
                # TODO log properly
                break

            if msg.get("text") is not None:
                data = json.loads(msg["text"])
                if data["type"] == "start":
                    sample_rate = data["sampleRate"]

                    wav = wave.open(str(session_dir / "original-audio.wav"), "wb")
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)

                    # TODO log properly
                    print("Session start:", data)
                elif data["type"] == "stop":
                    # TODO log properly
                    print("Stop pressed")
                    break
            elif msg.get("bytes") is not None:
                raw = msg["bytes"]
                seq, client_ms = HEADER.unpack_from(raw)
                audio = raw[HEADER.size:]

                if seq != expected_seq:
                    # TODO log properly
                    print(f"Gap detected, expected {expected_seq} got {seq}")
                expected_seq = seq + 1

                # TODO detect chunks that took too long to arrive, even with the correct index

                samples = np.frombuffer(audio, dtype="<i2")
                wav.writeframes(audio)

    except WebSocketDisconnect:
        if(wav):
            wav.close() # temp close
        pass
    finally:
        if wav:
            wav.close()
        active_session = None
        expected_seq = 0
        print("Session closed.")

def main():
    ip = get_lan_ip()
    print("\nhttps://localhost:8443/")
    print(f"PHONES: https://{ip}:8443/")

    qr = qrcode.make(f"https://{ip}:8443/")
    qr.get_image().show()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        ssl_certfile=str(CERT_DIR / "certificate.pem"),
        ssl_keyfile=str(CERT_DIR / "key.pem"),
    )