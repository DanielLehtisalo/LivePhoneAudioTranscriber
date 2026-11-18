import os
import site
from pathlib import Path
import asyncio
import functools
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import numpy as np

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

class Transcriber:
    def __init__(self):
        self._executor = None

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