from pathlib import Path
from datetime import datetime, timezone
import os
import logging
import json
import asyncio
import struct

import wave
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import log
from log import sys_log as sl
from transcriber import transcription_task
from segmenter import Segmenter

BASE_DIR = Path(os.getcwd())
SESSIONS_DIR = BASE_DIR / "sessions"

HEADER = struct.Struct("<Id")

class session():
    def __init__(self, ws: WebSocket, transcriber, session_id):
        self.ws = ws
        self.transcriber = transcriber
        self.id = session_id
        self.expected_seq = 0
        self.sample_rate = None
        self.wav = None
        self.started = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

        self.dir = SESSIONS_DIR / f"{self.started}_{session_id}"
        self.dir.mkdir(parents=True)

        self.log = log.setup_logger(f"session-{self.id}-logger", str(self.dir / "session.log"), logging.INFO)
        self.log("== Start of log ==")
        self.queue = asyncio.Queue()
        self.segmenter = None

        self.last_arrival = None

    
    async def reconnect(self, ws: WebSocket):
        """Allows for a client to reconnect"""
        self.ws = ws
    async def loop(self):
        try:
            while True:
                msg = await self.ws.receive()
                self.log.info(f"Received request: {msg}")

                if msg["type"] == "websocket.disconnect":
                    log.info("Websocket disconnected.")
                    self.ws = None
                    break

                if msg.get("text") is not None:
                    data = json.loads(msg["text"])

                    if data["type"] == "start":
                        self.sample_rate = data["sampleRate"]

                        asyncio.create_task(
                            transcription_task(self.queue, self.dir / "transcript_live.jsonl", self.ws)
                        )
                        self.segmenter = Segmenter(self.sample_rate, on_segment=lambda s, audio: self.queue.put_nowait((s, audio)))

                        self.wav = wave.open(str(self.dir / "audio-original.wav"), "wb")
                        self.wav.setnchannels(1)
                        self.wav.setsampwidth(2)
                        self.wav.setframerate(self.sample_rate)
                        sl().info(f"Start received for session {self.id}")
                        self.log.info(f"START. Original request: {msg}")
                    elif data["type"] == "stop":
                        sl().info(f"Stop received for session {self.id}")
                        self.log.info(f"STOP. Original request: {msg}")
                        break

                elif msg.get["bytes"] is not None:
                    raw = msg["bytes"]
                    seq, clientms = HEADER.unpack_from(raw)
                    audio = raw[HEADER.size]

                    self.log.info(f"Data rx: {raw[:16]}... Hash: TODO") # TODO add hash

                    if seq != self.expected_seq:
                        self.log.warning(f"Gap detected, expected packet {self.expected_seq} got {seq}")
                    self.expected_seq = seq + 1
 
                    


