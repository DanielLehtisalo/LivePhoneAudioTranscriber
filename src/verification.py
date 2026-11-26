import hashlib
import json
from dataclasses import dataclass

from audio_processing import CHUNK_META, chain_origin

@dataclass
class ChainReport:
    result: str
    """Options: INTACT, INTERRUPTED, MODIFIED, ERROR"""
    chunks_read: int
    chunks_verified: int
    message: str

    def __str__(self):
        return (f"[{self.result.upper()}] {self.message} (verified {self.chunks_verified}/{self.chunks_read} chunks)")

def _read_audio_log(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [line for line in f.read().split("\n") if line.strip()]
    events = []
    for i, line, in enumerate(lines):
        try:
            events.append(json.loads(line))
        except:
            if i==len(lines) - 1:
                break
            return None, f"audio_log.jsonl line {i + 1} is not valid json."
    return events, None


def verify_chain(session_dir, session_id):
    """Checks the chain stored in audio_log.jsonl"""
    events, err = _read_audio_log(session_dir / "audio_log.jsonl")
    if err:
        return ChainReport("modified", 0, 0, err)

    started = next((e for e in events if e["event"] == "recording_started"), None)
    ended = next((e for e in events if e["event"] == "recording_ended"), None)
    checkpoints = [e for e in events if e["event"] == "checkpoint"]

    chain = chain_origin(session_id)
    if started is None:
        return ChainReport("error", 0, 0, "no recording_started event in log")
    if started.get("chain_origin") != chain.hex():
        return ChainReport("modified", 0, 0, "chain origin doesn't match the session id")

    file_hash = hashlib.sha256()
    chunks = 0
    byte_count = 0
    last_good = None

    def verified():
        return last_good["chunks"] if last_good else 0

    i = 0
    def check_checkpoints():
        nonlocal i, last_good
        while i < len(checkpoints):
            checkpoint = checkpoints[i]
            if checkpoint["chunks"] < chunks:
                return f"checkpoint {i} (chunk {checkpoint['chunks']}) is out of order"
            if checkpoint["chunks"] > chunks:
                return None
            loc = f"between chunk {verified()} and chunk {chunks} (checkpoint {i})"
            if checkpoint["chain"] != chain.hex():
                return f"hash chain mismatch {loc}"
            if checkpoint["bytes"] != byte_count:
                return f"byte count mismatch {loc}: log {checkpoint['bytes']}, files {byte_count}"
            if checkpoint["sha256_prefix"] != file_hash.hexdigest():
                return f"file hash mismatch {loc}"
            last_good = checkpoint
            i += 1
        return None

    problem = check_checkpoints()
    tail_note = None

    with open(session_dir / "audio.raw", "rb") as audio, \
        open(session_dir / "chunks.idx", "rb") as index:
        while problem is None:
            meta = index.read(CHUNK_META.size)
            if len(meta) < CHUNK_META.size:
                if meta:
                    tail_note = "partial index record at end of chunks.idx"
                break
            
            seq, client_ms, server_ms, length = CHUNK_META.unpack(meta)
            data = audio.read(length)
            if len(data) != length:
                tail_note = f"Audio cut off for chunk seq {seq}."
                break
            
            chain = hashlib.sha256(chain + meta + data).digest()
            file_hash.update(data)
            chunks += 1
            byte_count += length
            problem = check_checkpoints()

        extra_audio: bool = problem is None and tail_note is None and audio.read(1) != b""
    
    if problem:
        return ChainReport("modified", chunks, verified(), problem)
    
    if i < len(checkpoints):
        missing = checkpoints[i]["chunks"]
        return ChainReport("modified", chunks, verified(),
                           f"log has a checkpoint at chunk {missing}, but the files end at chunk {chunks}")

    if ended is not None:
        if tail_note or extra_audio:
            return ChainReport("modified", chunks, verified(),
                               tail_note or "audio.raw has bytes not in index")
        if ended["chunks"] != chunks or ended["chain_final"] != chain.hex() or ended["sha256"] != file_hash.hexdigest():
            return ChainReport("modified", chunks, verified(),
                               "files do not match recording_ended")
        return ChainReport("intact", chunks, chunks, "recording completely intact")

    unverified = chunks - verified()
    details = [f"{unverified} chunk(s) after the last checkpoint are unverified"]
    if tail_note:
        details.append(tail_note)
    if extra_audio:
        details.append("audio.raw has bytes not in index")
    return ChainReport("interrupted", chunks, verified(), " ".join(details))