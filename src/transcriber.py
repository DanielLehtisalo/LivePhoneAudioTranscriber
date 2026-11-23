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


BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

_models = {}
_default_model_name = None

_cuda_loaded = False
def _add_cuda_dlls():
    global _cuda_loaded
    if not _cuda_loaded:
        _cuda_loaded = True
        if os.name != "nt":
            return
        for sp in site.getsitepackages():
            for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
                dll_dir = Path(sp) / sub
                if dll_dir.is_dir():
                    os.add_dll_directory(str(dll_dir))
                    os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ["PATH"]

def init_worker(model_name, device="cuda", compute_type="float16"):
    from faster_whisper import WhisperModel
    global _models
    global _default_model_name
    if model_name not in _models:
        _add_cuda_dlls()
        new_model = WhisperModel(str(MODELS_DIR / model_name), device=device, compute_type=compute_type)
        if not _models:
            _default_model_name = model_name
        _models[model_name] = new_model


def transcribe(audio, language=None, initial_prompt=None, model=None):
    global _models
    if not _models:
        sl().warning("No models loaded, transcription task missed.")
        raise RuntimeError("No models loaded")

    if model is None:
        _model = _default_model_name
    else:
        _model = model
    segments, info = _models[_model].transcribe(
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

from log import sys_log as sl

class Transcriber:
    def __init__(self):
        self.model_name = None
        pass

    def start(self, model_name):
        if model_name is not None:
            self.model_name = model_name
        self._executor = ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=init_worker,
            initargs=(self.model_name,),
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

async def transcription_task(queue, transcriber, transcript_path, ws):
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
        if transcriber is None:
            if sl() is not None:
                sl().warning("No transcriber initialized.")
        while True:
            item = await queue.get()
            if item is None:
                break
            start_sample, audio = item
            offset = start_sample / 16000

            try:
                result = await transcriber.run(audio, language=None)
            except Exception as e:
                sl().warning(f"Transcription failed. {e}")
                out.write(json.dumps({"failed": True, "start_sample": start_sample,
                      "error": str(e)}) + "\n")
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