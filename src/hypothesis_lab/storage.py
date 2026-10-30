"""Local experiment storage and explicit-consent optional credentials."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import threading
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path


def state_dir() -> Path:
    custom = os.environ.get("HYPOTHESIS_LAB_HOME")
    default = (
        Path(os.environ["LOCALAPPDATA"]) / "HypothesisLab"
        if os.environ.get("LOCALAPPDATA")
        else Path.home() / ".local" / "share" / "hypothesis-lab"
    )
    result = Path(custom) if custom else default
    result.mkdir(parents=True, exist_ok=True, mode=0o700)
    return result


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(raw)
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def describe_experiment(record: dict) -> dict:
    # Identity covers data/config/result, excluding wall clock metadata.
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    identity = hashlib.sha256(raw.encode()).hexdigest()[:20]
    stored = {
        **record,
        "id": identity,
        "created_at": datetime.now(UTC).isoformat(),
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.system(),
            "hypothesis_lab": "0.4.0",
            "mandatory_dependencies": [],
        },
    }
    return stored


def save_experiment(record: dict) -> dict:
    stored = describe_experiment(record)
    write_json(state_dir() / "experiments" / f"{stored['id']}.json", stored)
    return stored


def load_experiment(identity: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{20}", identity):
        raise ValueError("Invalid experiment identifier")
    return json.loads(
        (state_dir() / "experiments" / f"{identity}.json").read_text(encoding="utf-8")
    )


def list_experiments() -> list[dict]:
    records = []
    directory = state_dir() / "experiments"
    for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[
        :100
    ]:
        value = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {k: value.get(k) for k in ("id", "created_at", "mode", "name", "dataset", "summary")}
        )
    return records


def _protect_native(raw: bytes, decrypt: bool = False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    library = ctypes.windll.crypt32  # type: ignore[attr-defined]
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    # CRYPTPROTECT_UI_FORBIDDEN: credential operations must never open a native prompt.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)  # type: ignore[attr-defined]


def _protect(raw: bytes, decrypt: bool = False) -> bytes:
    result: list[bytes] = []
    errors: list[Exception] = []

    def operation() -> None:
        try:
            result.append(_protect_native(raw, decrypt))
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=operation, daemon=True)
    worker.start()
    worker.join(timeout=5)
    if worker.is_alive() or errors or not result:
        raise ValueError(
            "Windows credential protection is unavailable. No key was saved; offline research is unaffected."
        )
    return result[0]


def credential_status() -> dict:
    return {
        "provider": "Alpha Vantage",
        "saved": (state_dir() / "credential.json").exists(),
        "storage": "Windows DPAPI (current user)"
        if os.name == "nt"
        else "local file, owner-only permissions (not encrypted)",
        "location": str(state_dir() / "credential.json"),
        "purpose": "Optional end-of-day stock quote connection test; not used by offline experiments",
    }


def save_credential(key: str, consent: bool) -> None:
    if not consent:
        raise ValueError("Explicit consent is required to store a provider key")
    if (
        not isinstance(key, str)
        or not 1 <= len(key.strip()) <= 256
        or not re.fullmatch(r"[A-Za-z0-9_-]+", key.strip())
    ):
        raise ValueError("Provider key must contain letters, numbers, underscores or hyphens")
    raw = key.strip().encode()
    if os.name == "nt":
        raw = _protect(raw)
    write_json(
        state_dir() / "credential.json",
        {"protected": os.name == "nt", "value": base64.b64encode(raw).decode()},
    )


def load_credential() -> str:
    path = state_dir() / "credential.json"
    if not path.exists():
        raise ValueError("Save an optional Alpha Vantage key first")
    record = json.loads(path.read_text(encoding="utf-8"))
    raw = base64.b64decode(record["value"])
    if record["protected"]:
        if os.name != "nt":
            raise ValueError("This Windows-protected credential is bound to its original user")
        raw = _protect(raw, decrypt=True)
    return raw.decode()


def remove_credential() -> None:
    (state_dir() / "credential.json").unlink(missing_ok=True)
