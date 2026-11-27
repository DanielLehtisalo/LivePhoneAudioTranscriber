import hashlib
import json
import os
from datetime import datetime, timezone
import asyncio
import struct
import time

import wave

CHUNK_META = struct.Struct("<IddI")
"""seq, client_ms, server_ms, length"""
CHAIN_PREFIX = b"LPAT-v1:"

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def chain_origin(session_id: str) -> bytes:
    return hashlib.sha256(CHAIN_PREFIX + session_id.encode()).digest()

class AudioRecorder:
    def __init__(self, session_dir, session_id, sample_rate, checkpoint_rate=10):
        self.dir = session_dir
        self.sample_rate = sample_rate
        self.audio = open(session_dir / "audio.raw", "ab")
        self.index = open(session_dir / "chunks.idx", "ab")
        self.audio_log = open(session_dir / "audio_log.jsonl", "a", encoding="utf-8")

        self.file_hash = hashlib.sha256()
        self.chain = chain_origin(session_id=session_id)

        self.byte_count = 0
        self.chunk_count = 0
        self.checkpoint_rate = checkpoint_rate
        self.pending = 0
        """How many chunks are pending."""

        self.event("recording_started", session_id=session_id, format="pcm_s16le", channels=1, 
                   sample_rate=sample_rate, index_format="<IddI seq,client_ms,server_ms,len",
                   chain_origin=self.chain.hex())

    def event(self, kind, **fields):
        record = {"t": utc_now(), "event": kind, **fields}
        self.audio_log.write(json.dumps(record) + "\n")
        self.audio_log.flush()
        os.fsync(self.audio_log.fileno())

    def write_chunk(self, seq, audio, client_ms, server_ms=None):
        if server_ms is None:
            server_ms = time.time() * 1000
        meta = CHUNK_META.pack(seq, client_ms, server_ms, len(audio))

        self.audio.write(audio)
        self.index.write(meta)

        self.file_hash.update(audio)
        self.chain = hashlib.sha256(self.chain + meta + audio).digest()

        self.byte_count += len(audio)
        self.chunk_count += 1
        self.pending += 1
        if self.pending >= self.checkpoint_rate:
            self.checkpoint(last_seq=seq)

    def checkpoint(self, last_seq=None):
        for f in (self.audio, self.index):
            f.flush()
            os.fsync(f.fileno())
        self.event("checkpoint", last_seq=last_seq, chunks=self.chunk_count,
                   bytes=self.byte_count, 
                   sha256_prefix=self.file_hash.copy().hexdigest(),
                   chain=self.chain.hex())
        self.pending = 0

    def close(self, min_clock_diff):
        if self.audio.closed:
            return

        self.checkpoint()
        self.event("recording_ended", chunks=self.chunk_count, bytes=self.byte_count,
                   min_clock_diff_ms=min_clock_diff,
                   sha256=self.file_hash.hexdigest(), chain_final=self.chain.hex())
        for f in(self.audio, self.index, self.audio_log):
            f.close()

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