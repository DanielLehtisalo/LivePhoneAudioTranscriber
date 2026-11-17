from pathlib import Path

import os
import socket

import qrcode

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

def get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"

BASE_DIR = Path(os.getcwd())
STATIC_DIR = BASE_DIR / "static"
CERT_DIR = BASE_DIR / "certs"

app = FastAPI()

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

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