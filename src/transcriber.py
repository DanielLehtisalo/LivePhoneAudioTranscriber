import os
import site
from pathlib import Path
import asyncio
import functools
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import numpy as np
import json

_model = None

def _add_cuda_dlls():
    if os.name != "nt":
        return
    for sp in site.getsitepackages():
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
            dll_dir = Path(sp) / sub
            if dll_dir.is_dir():
                os.add_dll_directory(str(dll_dir))
                os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ["PATH"]

def init_worker(model_path, device="cuda", compute_type="float16"):
    global _model
    _add_cuda_dlls()
    from faster_whisper import WhisperModel
    _model = WhisperModel(model_path, device=device, compute_type=compute_type)

def transcribe(audio, language=None, initial_prompt=None):
    segments, info = _model.transcribe(
        audio,
        language=language,
        task="transcribe",
        initial_prompt=initial_prompt,
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
        word_timestamps=True,
    )
    out = []
    for s in segments:
        out.append({
            "start": s.start,
            "end": s.end,
            "text": s.text.strip(),
            "avg_logprob": s.avg_logprob,
            "no_speech_prob": s.no_speech_prob,
            "compression_ratio": s.compression_ratio,
            "temperature": s.temperature,
            "words": [
                {"start": w.start, "end": w.end, "word": w.word, "p": w.probability}
                for w in (s.words or [])
            ],
        })
    return {
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": out,
    }

_transcriber = None
from log import sys_log as sl

class Transcriber:
    def __init__(self):
        global _transcriber
        if _transcriber is not None:
            sl().warning("A transcriber already exists, but it was replaced.")
        self._executor = None
        _transcriber = self

    def start(self, MODEL_PATH):
        self._executor = ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=init_worker,
            initargs=(str(MODEL_PATH),),
        )

    async def run(self, audio, **opts):
        loop = asyncio.get_running_loop()
        call = functools.partial(transcribe, audio, **opts)
        try:
            return await loop.run_in_executor(self._executor, call)
        except BrokenProcessPool:
            print("Transcriber crashed, restarting...")
            self._executor.shutdown(wait=False, cancel_futures=True)
            self.start()
            raise

    async def warm_up(self):
        await self.run(np.zeros(16000, dtype=np.float32))

    def stop(self):
        self._executor.shutdown(wait=True, cancel_futures=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

async def transcription_task(queue, transcript_path, ws):
    client_connected = True

    async def send_to_client(payload):
        nonlocal client_connected
        if not client_connected:
            return
        try:
            if ws.application_state == WebSocketState.CONNECTED:
                await ws.send_json(payload)
            else:
                client_connected = False
        except (WebSocketDisconnect, RuntimeError):
            client_connected = False
    
    with open(transcript_path, "a", encoding="utf-8") as out:
        global _transcriber
        if _transcriber is None:
            if sl() is not None:
                sl().warning("No transcriber initialized.")
        while True:
            item = await queue.get()
            if item is None:
                break
            start_sample, audio = item
            offset = start_sample / 16000

            try:
                result = await _transcriber.run(audio, language=None)
            except:
                sl().warning("Transcription failed.")
                out.write("(Failed to transcribe)\n")
                continue

            for seg in result["segments"]:
                seg["start"] += offset
                seg["end"] += offset
                for w in seg["words"]:
                    w["start"] += offset
                    w["end"] += offset
                seg["language"] = result["language"]
                seg["language_probability"] = result["language_probability"]
                out.write(json.dumps(seg, ensure_ascii=False) + "\n")

            for seg in result["segments"]:
                await send_to_client({
                    "type": "segment",
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"],
                })
            
            out.flush()
        out.close()