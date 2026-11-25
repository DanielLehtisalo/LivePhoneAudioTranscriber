import hashlib
import json
import os
from datetime import datetime, timezone
import asyncio

import wave

def utc_now():
    return datetime.now(timezone.utc).isoformat()

class AudioRecorder:
    def __init__(self, session_dir, sample_rate, checkpoint_rate=10):
        self.dir = session_dir
        self.sample_rate = sample_rate
        self.audio = open(session_dir / "audio.raw", "ab")
        self.audio_log = open(session_dir / "audio_log.jsonl", "a", encoding="utf-8")
        self.file_hash = hashlib.sha256()
        self.byte_count = 0
        self.checkpoint_rate = checkpoint_rate
        self.pending = 0
        """How many chunks are pending."""
        self.closed = False

        self.event("recording_started", format="pcm_s16le", channels=1, sample_rate=sample_rate)

    def event(self, kind, **fields):
        record = {"t": utc_now(), "event": kind, **fields}
        self.audio_log.write(json.dumps(record) + "\n")
        self.audio_log.flush()
        os.fsync(self.audio_log.fileno())

    def write_chunk(self, seq, audio, clientms):
        self.audio.write(audio)
        self.file_hash.update(audio)
        self.byte_count += len(audio)
        self.pending += 1
        if self.pending >= self.checkpoint_rate:
            self.checkpoint(last_seq=seq)

    def checkpoint(self, last_seq=None):
        self.audio.flush()
        os.fsync(self.audio.fileno())
        self.event("checkpoint", last_seq=last_seq, bytes=self.byte_count, 
                   sha256_prefix=self.file_hash.copy().hexdigest())
        self.pending = 0

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.checkpoint()
        self.event("recording_ended", bytes=self.byte_count,
                   sha256=self.file_hash.hexdigest())
        self.audio.close()
        self.audio_log.close()

    async def convert(self):
        """Create a wav from the recorded raw file"""
        await asyncio.to_thread(
        raw_to_wav, self.dir / "audio.raw", self.dir / "audio-converted.wav", self.sample_rate
    )


def raw_to_wav(raw_path, wav_path, sample_rate):
    with open(raw_path, "rb") as src, wave.open(str(wav_path), "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(sample_rate)
        while chunk := src.read(1 << 20):
            dst.writeframes(chunk)