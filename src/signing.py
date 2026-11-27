import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from cryptography.hazmat.primitives import serialization

BASE_DIR = Path(__file__).resolve().parent.parent
KEYS_DIR = BASE_DIR / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "private_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "public_key.pem"
MODELS_DIR = BASE_DIR / "models"

MANIFEST = "manifest.json"
SIGNATURE = "manifest.sig"
EXCLUDED = {MANIFEST, SIGNATURE}

def load_private_key(path=PRIVATE_KEY_PATH):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No signing key found at {path}. Run setup.py first.")
    return serialization.load_pem_private_key(path.read_bytes(), password=None)

def key_id(public_key) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()

def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()

def session_files(session_dir: Path):
    for p in sorted(session_dir.rglob("*")):
        rel = p.relative_to(session_dir).as_posix()
        if p.is_file() and rel not in EXCLUDED:
            yield rel, p

def _package_versions():
    return dict(sorted(
        (dist.metadata["Name"], dist.version) for dist in metadata.distributions()
    ))

def _write_safe(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def sign_session(session_dir: Path, session_id: str, private_key, extra: dict) -> dict:
    manifest = {
        "format": "lpat-manifest-v1",
        "session_id": session_id,
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "software": {
            "python": sys.version.split()[0],
            "packages": _package_versions(),
        },
        **extra,
        "files": {rel: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
                  for rel, p in session_files(session_dir)},
        "signing_key": {"algorithm": "ed25519",
                        "public_key_sha256": key_id(private_key.public_key())},
    }
    data = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    _write_safe(session_dir / MANIFEST, data)
    _write_safe(session_dir / SIGNATURE, private_key.sign(data))
    return manifest