"""Bounded, atomic Screensaver metadata, separate from Pixel Studio's library."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath
import tempfile
import threading


COMPILER_VERSION = "cinema-2-animated"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_GAMES = 2000
class ScreensaverError(RuntimeError):
    def __init__(self, message, code="cinema_error"):
        super().__init__(message)
        self.code = code


def app_id(value):
    if isinstance(value, bool):
        raise ScreensaverError("Invalid Steam AppID", "invalid_appid")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ScreensaverError("Invalid Steam AppID", "invalid_appid") from error
    if not 0 < number <= 0xFFFFFFFF:
        raise ScreensaverError("Invalid Steam AppID", "invalid_appid")
    return number


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(payload) > MAX_CATALOG_BYTES:
        raise ScreensaverError("Screensaver metadata is too large", "catalog_limit")
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".cinema-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path, maximum=MAX_CATALOG_BYTES):
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            return {}
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(256 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
