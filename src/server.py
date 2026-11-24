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

from session import Session

from log import sys_log as sl
from constants import LIVE_MODEL_NAME, OFFLINE_MODEL_NAME

BASE_DIR = Path(os.getcwd())
STATIC_DIR = BASE_DIR / "static"
CERT_DIR = BASE_DIR / "certs"
SESSIONS_DIR = BASE_DIR / "sessions"


def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"

live_transcriber = Transcriber()
offline_transcriber = Transcriber()

def _on_offline_warmup_done(task: asyncio.Task):
    if task.cancelled():
        sl().warning("Offline transcriber warm-up was cancelled.")
    elif (exc := task.exception()) is not None:
        sl().error(f"Offline transcriber warm-up failed: {exc!r}")
    else:
        sl().info("Offline transcriber ready.")

@asynccontextmanager
async def lifespan(app):
    live_transcriber.start(LIVE_MODEL_NAME)
    offline_transcriber.start(OFFLINE_MODEL_NAME)
    sl().info("Warming up live transcriber...")
    await live_transcriber.warm_up()
    sl().info("Live transcriber ready.")
    sl().info("Warming up offline transcriber in the background")
    app.state.warm_up_task = asyncio.create_task(offline_transcriber.warm_up())
    app.state.warm_up_task.add_done_callback(_on_offline_warmup_done)

    yield
    app.state.warm_up_task.cancel()
    live_transcriber.stop()
    offline_transcriber.stop()

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

_sessions = {}

@app.websocket("/ws")
async def audio_ws(ws: WebSocket):
    await ws.accept()

    session_id = uuid.uuid4().hex
    sl().info(f"Starting new session {session_id}")

    new_session = Session(live_transcriber, session_id)
    _sessions[session_id] = new_session
    try:
        await new_session.connect(ws)
    finally:
        _sessions.pop(session_id)
        sl().info(f"Ending session {session_id}")
        if ws:
            await ws.close(reason="Session ended.")

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