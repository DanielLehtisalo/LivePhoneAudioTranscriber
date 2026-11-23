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

transcriber = Transcriber()

@asynccontextmanager
async def lifespan(app):
    transcriber.start(MODEL_PATH)
    sl().info("Starting transcriber...")
    await transcriber.warm_up()
    sl().info("Transcriber ready.")
    yield
    transcriber.stop()

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

    new_session = Session(transcriber, session_id)
    _sessions[session_id] = new_session
    try:
        await new_session.reconnect(ws)
    finally:
        _sessions.pop(session_id)
        sl().info(f"Ending session {session_id}")

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