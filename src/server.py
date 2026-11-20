from pathlib import Path

import os

import json
import socket
import wave
import time
import uuid
from datetime import datetime, timezone
import asyncio

import qrcode

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from transcriber import Transcriber
from segmenter import Segmenter
from contextlib import asynccontextmanager

import log as r

BASE_DIR = Path(os.getcwd())
STATIC_DIR = BASE_DIR / "static"
CERT_DIR = BASE_DIR / "certs"
SESSIONS_DIR = BASE_DIR / "sessions"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "large-v3-turbo"




def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"



active_session = None
log = None
transcriber = Transcriber()

@asynccontextmanager
async def lifespan(app):
    transcriber.start(MODEL_PATH)
    r.sys_log().info("Starting transcriber...")
    await transcriber.warm_up()
    r.sys_log().info("Transcriber ready.")
    yield
    transcriber.stop()

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")





@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.websocket("/ws")
async def audio_ws(ws: WebSocket):
    global active_session
    global log
    last_arrival = None
    await ws.accept()

    if active_session is not None:
        r.sys_log().warning("Another client tried to connect while session was running.")
        await ws.close(reason="Another session is running.")
        return

    session_id = uuid.uuid4().hex
    active_session = session_id
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = SESSIONS_DIR / f"{started}_{session_id}"
    session_dir.mkdir(parents=True)

    log = r.start_logging(active_session, session_dir)

    sample_rate = None
    wav = None
    expected_seq = 0
    queue = asyncio.Queue()
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                log.info("Websocket disconnected.")
                break

            if msg.get("text") is not None:
                data = json.loads(msg["text"])
                if data["type"] == "start":
                    sample_rate = data["sampleRate"]

                    asyncio.create_task(
                        transcription_task(queue, session_dir / "transcript_live.jsonl", ws)
                    )

                    segmenter = Segmenter(sample_rate, on_segment=lambda s, audio: queue.put_nowait((s, audio)))

                    wav = wave.open(str(session_dir / "original-audio.wav"), "wb")
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)

                    r.sys_log().info("Start received.")
                    log.info(f"Start received. Original request data: {data}")
                elif data["type"] == "stop":
                    r.sys_log().info("Stop received.")
                    log.info(f"Stop received. Original request data: {data}")
                    break
            
            elif msg.get("bytes") is not None:
                raw = msg["bytes"]
                seq, client_ms = HEADER.unpack_from(raw)
                audio = raw[HEADER.size:]

                log.info(f"Data rx: {raw}")

                if seq != expected_seq:
                    log.warning(f"Gap detected, expected {expected_seq} got {seq}")
                expected_seq = seq + 1

                if last_arrival is not None:
                    diff = time.monotonic() - last_arrival
                    if abs(diff - 0.1) > 0.025:
                        log.warning(f"Packet timing is outside of tolerances. Got {diff}s, expected 0.1s. Seq: {seq}")
                last_arrival = time.monotonic()

                wav.writeframes(audio)
                segmenter.feed(audio)

    except WebSocketDisconnect:
        if(wav):
            wav.close()
        pass
    finally:
        if wav:
            wav.close()
        active_session = None
        last_arrival = None
        expected_seq = 0
        segmenter.finish()
        await queue.put(None)
        r.end_logging()
        log = None

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