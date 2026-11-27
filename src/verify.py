import argparse
import json
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

from signing import (EXCLUDED, MANIFEST, PUBLIC_KEY_PATH, SIGNATURE,
                     key_id, session_files, sha256_file)
from verification import verify_chain

EXIT_CODES = {"intact": 0, "interrupted": 1, "modified": 2, "error": 3}

def _check(name, status, message):
    return {"check": name, "status": status, "message": message}

def verify_signature(session_dir: Path, public_key_path: Path):
    manifest_path = session_dir / MANIFEST
    sig_path = session_dir / SIGNATURE
    if not manifest_path.exists():
        return None, _check("signature", "interrupted", "session not signed, manifest.json missing")
    if not sig_path.exists():
        return None, _check("signature", "modified", "session signature missing, but manifest.json exists")

    public_key = serialization.load_pem_public_key(Path(public_key_path).read_bytes())
    manifest_bytes = manifest_path.read_bytes()
    try:
        public_key.verify(sig_path.read_bytes(), manifest_bytes)
    except InvalidSignature:
        return None, _check("signature", "modified", "signature does not match manifest (manifest changed or signed with different key)")

    manifest = json.loads(manifest_bytes)
    keyid = key_id(public_key)
    if manifest.get("signing_key", {}).get("public_key_sha256") != keyid:
        return None, _check("signature", "error", "manifest has a different signing key")
    return manifest, _check("signature", "intact", "valid signature")

def verify_files(session_dir: Path, manifest: dict):
    listed = manifest["files"]
    problems = []
    for rel, info in listed.items():
        p = session_dir / rel
        if not p.is_file():
            problems.append(f"missing: {rel}")
        elif p.stat().st_size != info["bytes"] or sha256_file(p) != info["sha256"]:
            problems.append(f"changed: {rel}")

    present = {rel for rel, _ in session_files(session_dir)}
    problems += [f"added after signing: {rel}" for rel in sorted(present - listed.keys())]

    if problems:
        return _check("files", "modified", " ".join(problems))
    return _check("files", "intact", "all files match manifest")

def verify_session(session_dir: Path, public_key_path: Path = PUBLIC_KEY_PATH) -> dict:
    session_dir = Path(session_dir)
    checks = []

    manifest, sig_check = verify_signature(session_dir, public_key_path)
    checks.append(sig_check)
    if manifest is not None:
        checks.append(verify_files(session_dir, manifest))

    try:
        chain = verify_chain(session_dir)
        checks.append(_check("hash_chain", chain.result, f"{chain.message} ({chain.chunks_verified}/{chain.chunks_read} chunks)"))
        if manifest is not None and chain.session_id != manifest.get("session_id"):
            checks.append(_check("session_id", "modified", "manifest session id doesn't match audio log session id"))
    except Exception as e:
        checks.append(_check("hash_chain", "error", repr(e)))

    overall = max((c["status"] for c in checks), key=EXIT_CODES.__getitem__)
    return {"session": session_dir.name, "status": overall, "checks": checks}

def main(argv=None):
    p = argparse.ArgumentParser(prog="lpat verify (read-only)")
    p.add_argument("sessions", nargs="+", type=Path, help="session folder(s)")
    p.add_argument("--json", action="store_true", help="output json")
    p.add_argument("--public-key", type=Path, default=PUBLIC_KEY_PATH, help="public key to use, default: keys/public_key.pem")
    args = p.parse_args(argv)

    results = [verify_session(d, args.public_key) for d in args.sessions]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['session']}: {r['status'].upper()}")
            for c in r["checks"]:
                print(f"    {c['check']} {c['status']} {c['message']}")

    sys.exit(max(EXIT_CODES[r["status"]] for r in results))

if __name__ == "__main__":
    main()