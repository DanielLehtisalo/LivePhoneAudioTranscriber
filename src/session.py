from pathlib import Path
from datetime import datetime, timezone
import os
import logging
import json
import asyncio
import struct
import time
from enum import Enum
import hashlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import log
from log import sys_log as sl
from transcriber import transcription_task, complete_transcription
from audio_processing import AudioRecorder, raw_to_wav
from segmenter import Segmenter

from constants import TIMING_TOLERANCE, PACKET_SPACING

BASE_DIR = Path(os.getcwd())
SESSIONS_DIR = BASE_DIR / "sessions"

HEADER = struct.Struct("<Id")

class Session_State(Enum):
    Waiting = 1
    Recording = 2
    Transcribing = 3
    Finished = 4

class Session():
    def __init__(self, transcriber, session_id):
        self.ws = None
        self.transcriber = transcriber
        self.id = session_id
        self.expected_seq = 0
        self.sample_rate = None
        self.started = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

        self.dir = SESSIONS_DIR / f"{self.started}_{session_id}"
        self.dir.mkdir(parents=True)

        self.log = log.setup_logger(f"session-{self.id}-logger", str(self.dir / "session.log"), logging.INFO)
        self.log.info("== Start of log ==")
        self.queue = asyncio.Queue()
        self.segmenter = None
        self.recorder = None

        self.last_arrival = None

        self.state = Session_State.Waiting

    
    async def connect(self, ws: WebSocket):
        self.ws = ws
        await self.loop()
    async def loop(self):
        try:
            while True:
                msg = await self.ws.receive()
                self.log.info(f"Received request from {self.ws.client.host}")

                if msg["type"] == "websocket.disconnect":
                    log.info("Websocket disconnected.")
                    self.ws = None
                    break

                if msg.get("text") is not None:
                    data = json.loads(msg["text"])

                    if data["type"] == "start" and self.state == Session_State.Waiting:
                        self.state = Session_State.Recording
                        
                        self.sample_rate = data["sampleRate"]

                        asyncio.create_task(
                            transcription_task(self.queue, self.transcriber, self.dir / "transcript_live.jsonl", self.ws)
                        )
                        self.segmenter = Segmenter(self.sample_rate, on_segment=lambda s, audio: self.queue.put_nowait((s, audio)))
                        self.recorder = AudioRecorder(session_dir=self.dir, sample_rate=self.sample_rate)

                        sl().info(f"Start received for session {self.id}")
                        self.log.info(f"START. Original request: {msg}")
                        self.log.info("== Recording started ==")
                    elif data["type"] == "stop" and self.state == Session_State.Recording:
                        sl().info(f"Stop received for session {self.id}")
                        self.log.info(f"STOP. Original request: {msg}")
                        break

                elif msg.get("bytes") is not None and self.state == Session_State.Recording:
                    raw = msg["bytes"]
                    seq, clientms = HEADER.unpack_from(raw)
                    audio = raw[HEADER.size:]

                    self.log.info(f"Data rx, Audio SHA256: {hashlib.sha256(audio).hexdigest()}")

                    if seq != self.expected_seq:
                        self.log.warning(f"Gap detected, expected packet {self.expected_seq} got {seq}")
                    self.expected_seq = seq + 1

                    if self.last_arrival is not None:
                        diff = time.monotonic() - self.last_arrival
                        if abs(diff - PACKET_SPACING) > TIMING_TOLERANCE:
                            self.log.warning(f"Packet timing is outside of tolerances. Got {diff}s, expected {PACKET_SPACING}s. Seq: {seq}")
                    self.last_arrival = time.monotonic()

                    if self.recorder:
                        self.recorder.write_chunk(seq=seq, audio=audio)
                    self.segmenter.feed(audio)
        except WebSocketDisconnect:
            self.log.warning("Websocket disconnected.")
            if(self.recorder):
                self.recorder.close()
        finally:
            if(self.recorder):
                self.recorder.close()

            self.log.info("== Recording ended ==")

            self.state = Session_State.Transcribing
            from server import offline_transcriber
            self.log.info("== Final transcription started ==")
            await complete_transcription(self.dir / "audio.raw", offline_transcriber, self.dir / "transcript_final.jsonl", self.sample_rate)
            self.log.info("== Final transcription finished ==")

            self.log.info("Creating wav from raw file.")
            await self.recorder.convert()

            self.state = Session_State.Finished
            self.log.info("== End of log ==")