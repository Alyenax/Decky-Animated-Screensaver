"""Explicit optional FFmpeg tools, installed only in the user's data directory.

No downloads, probes or process creation happen during import/construction.
The published asset digest is pinned independently from the downloaded bytes.
"""
from __future__ import annotations

import hashlib
import errno
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import socket
import ssl
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

from .catalog import ScreensaverError, atomic_json

PIN_TAG = "autobuild-2026-09-30-13-08"
PIN_STEM = "ffmpeg-n9.0.2-17-g2a571b6068-linux64-lgpl-shared-9.0"
PIN_SIZE = 63245836
PIN_SHA256 = "7a1ba2af36e5beeb98151e766a903b1d115f2206a86571f17f873cd7292c424f"
PIN_URL = f"https://github.com/BtbN/FFmpeg-Builds/releases/download/{PIN_TAG}/{PIN_STEM}.tar.xz"
BUILD_SOURCE = f"https://github.com/BtbN/FFmpeg-Builds/tree/{PIN_TAG}"
FFMPEG_SOURCE = "https://github.com/FFmpeg/FFmpeg/commit/2a571b6068"
MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_EXTRACTED = 512 * 1024 * 1024
MAX_FILES = 4096
DISK_RESERVE = 64 * 1024 * 1024
RECEIPT = ".cinema-tools-verified.json"
OWNER = "decky-animated-screensaver-tools-v1"
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com"}


def _trusted_download(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in DOWNLOAD_HOSTS
            and not parsed.username and not parsed.password and parsed.port in (None, 443))


class _DownloadRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _trusted_download(newurl):
            raise ScreensaverError('Untrusted video tools redirect', 'download_host')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _relative(name):
    if not isinstance(name, str) or len(name) > 1024 or "\\" in name or "\x00" in name:
        raise ScreensaverError("Unsafe media tools archive path", "unsafe_archive")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ScreensaverError("Unsafe media tools archive path", "unsafe_archive")
    return path


def _elf_x86_64(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        header = stream.read(64)
    return len(header) >= 64 and header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\x3e\x00"


class _ProbeFailure(ScreensaverError):
    """Only fixed labels/numbers may leave a probe, never its raw output."""
    def __init__(self, probe, reason, *, exit_code=None, elapsed_ms=None, missing=None, error_number=None):
        super().__init__("Screensaver media tools verification failed", "probe_failed")
        self.probe_detail = {"probe": probe, "reason": reason}
        if isinstance(exit_code, int): self.probe_detail["exit_code"] = exit_code
        if isinstance(elapsed_ms, int): self.probe_detail["elapsed_ms"] = max(0, elapsed_ms)
        if missing: self.probe_detail["missing"] = list(missing)
        if isinstance(error_number, int): self.probe_detail["errno"] = error_number


def _probe_exit_reason(output, returncode):
    # Classify loader failures without retaining any library names, paths or text.
    if "error while loading shared libraries:" in output: return "shared_library"
    if "GLIBC_" in output and "not found" in output: return "glibc_version"
    if "undefined symbol:" in output or "symbol lookup error:" in output: return "symbol_lookup"
    if returncode is not None and returncode < 0: return "process_signal"
    return "process_exit"


class Resources:
    def __init__(self, root, *, opener=None, clock=time.monotonic, event_callback=None):
        self.root = Path(root).expanduser().resolve()
        self.directory = self.root / "cinema-tools-v1"
        self.opener = opener or build_opener(_DownloadRedirects()).open
        self.clock, self.event_callback = clock, event_callback
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.thread = self.process = self.response = None
        self.closed = False
        self.phase, self.percent, self.error = "idle", 0, ""
        self._ready = False
        self._checked = False
        self.last_failure = {}
        self.download_attempt = self.downloaded_bytes = 0

    def _event(self, name, **fields):
        if callable(self.event_callback):
            try: self.event_callback('cinema_tools_' + name, **fields)
            except Exception: pass

    def _failure(self, error, stage):
        from das.provider import _certificate_failure
        reason = getattr(error, 'reason', error)
        if isinstance(error, ScreensaverError): code = error.code
        elif _certificate_failure(error): code = 'download_tls'
        elif isinstance(error, HTTPError): code = 'download_http'
        elif isinstance(reason, (TimeoutError, socket.timeout)): code = 'download_timeout'
        elif isinstance(reason, PermissionError): code = 'download_permission'
        elif getattr(reason, 'errno', None) == errno.ENOSPC: code = 'insufficient_storage'
        elif isinstance(error, URLError): code = 'download_network'
        elif isinstance(error, OSError): code = 'download_io'
        else: code = 'download_failed'
        detail = {'code': code, 'stage': stage, 'exception': type(error).__name__,
                  'attempt': self.download_attempt, 'bytes': self.downloaded_bytes}
        if isinstance(error, HTTPError): detail['http_status'] = int(error.code)
        if isinstance(getattr(reason, 'errno', None), int): detail['errno'] = reason.errno
        if isinstance(error, _ProbeFailure): detail.update(error.probe_detail)
        # Deliberately omit messages, paths, signed redirect URLs and headers.
        with self.lock: self.last_failure = detail
        self._event('failure', **detail)
        return code

    def _open(self, request):
        from das.provider import _certificate_failure, SYSTEM_CA_BUNDLES
        try:
            return self.opener(request, timeout=20)
        except (URLError, ssl.SSLError) as first:
            if not _certificate_failure(first): raise
            attempted = set()
            for bundle in SYSTEM_CA_BUNDLES:
                if not os.path.isfile(bundle): continue
                resolved = os.path.realpath(bundle)
                if resolved in attempted: continue
                attempted.add(resolved)
                self._check()
                try:
                    context = ssl.create_default_context(cafile=bundle)
                    response = build_opener(_DownloadRedirects(), HTTPSHandler(context=context)).open(request, timeout=20)
                    self._event('system_ca_recovered')
                    return response
                except (OSError, URLError, ssl.SSLError) as error:
                    if not _certificate_failure(error) and not isinstance(error, FileNotFoundError): raise
            raise ScreensaverError('System CA verification failed', 'download_tls') from first

    @staticmethod
    def _supported():
        return platform.system() == "Linux" and platform.machine().lower() in {"x86_64", "amd64"}

    def _check(self):
        if self.cancelled.is_set() or self.closed:
            raise ScreensaverError("Screensaver media tools download cancelled", "cancelled")

    def _progress(self, phase, percent):
        with self.lock:
            self.phase, self.percent = phase, max(0, min(100, int(percent)))

    def _read_receipt(self, directory=None):
        directory = directory or self.directory
        if directory.is_symlink():
            return None
        path = directory / RECEIPT
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
                return None
            value = json.loads(path.read_text())
            if value.get("owner") != OWNER or not isinstance(value.get("files"), dict) or len(value["files"]) > MAX_FILES:
                return None
            for name, record in value["files"].items():
                relative = _relative(name)
                if str(relative) != name or name == RECEIPT or not isinstance(record, dict):
                    return None
            return value
        except (OSError, ValueError, TypeError, ScreensaverError):
            return None

    def _validate_receipt(self, directory=None):
        directory = directory or self.directory
        receipt = self._read_receipt(directory)
        if (not self._supported() or not receipt or receipt.get("verified") is not True
                or receipt.get("archive_sha256") != PIN_SHA256 or receipt.get("tag") != PIN_TAG
                or not {"bin/ffmpeg", "bin/ffprobe", "LICENSE.txt"}.issubset(receipt["files"])):
            return False
        try:
            for name, record in receipt["files"].items():
                path = directory / name
                path.resolve(strict=True).relative_to(directory)
                if "link" in record:
                    if not path.is_symlink() or os.readlink(path) != record["link"]:
                        return False
                else:
                    info = path.lstat()
                    if (not stat.S_ISREG(info.st_mode) or info.st_size != record["size"]
                            or info.st_mtime_ns != record["mtime_ns"]):
                        return False
            return (_elf_x86_64(directory / "bin/ffmpeg") and _elf_x86_64(directory / "bin/ffprobe")
                    and os.access(directory / "bin/ffmpeg", os.X_OK)
                    and os.access(directory / "bin/ffprobe", os.X_OK))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return False

    def status(self):
        with self.lock:
            if not self._checked:
                self._ready = self._validate_receipt()
                self._checked = True
            active = self.phase in {"downloading", "extracting", "verifying"}
            return {"ready": self._ready, "supported": self._supported(), "phase": self.phase if active or not self._ready else "ready",
                    "percent": self.percent if active or not self._ready else 100, "error": self.error,
                    "download_bytes": PIN_SIZE, "version": "FFmpeg 9.0.2", "tag": PIN_TAG,
                    "source_url": PIN_URL, "license": "LGPL shared distribution; full notices are retained locally",
                    "installation_path": str(self.directory),
                    "download_required": not self._ready, "last_failure": dict(self.last_failure),
                    "attempt": self.download_attempt, "downloaded_bytes": self.downloaded_bytes}

    def executable(self):
        with self.lock:
            self._ready = self._validate_receipt(); self._checked = True
            return str(self.directory / "bin/ffmpeg") if self._ready else None

    def library_path(self):
        return str(self.directory / "lib") if self.executable() else None

    def start(self):
        with self.lock:
            if self.closed:
                raise ScreensaverError("Screensaver media tools are shutting down", "closed")
            if not self._supported():
                raise ScreensaverError("Optional Screensaver media tools require Linux x86_64", "unsupported_platform")
            if self.thread is not None and self.thread.is_alive():
                return self.status()
            if self.phase in {"downloading", "extracting", "verifying"}:
                return self.status()
            if self.executable():
                return self.status()
            self.cancelled.clear(); self.error = ""; self.phase = "downloading"; self.percent = 0
            self.last_failure = {}; self.download_attempt = self.downloaded_bytes = 0
            self.thread = threading.Thread(target=self._install, name="gabecube-cinema-tools", daemon=True)
            self.thread.start()
            return self.status()

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            process, response = self.process, self.response
        if process is not None:
            self._terminate(process)
        if response is not None:
            try: response.close()
            except OSError: pass
        return self.status()

    def shutdown(self, timeout=3):
        self.closed = True
        self.cancel()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))

    def verify(self):
        """Explicit disk hash + short executable probe; run off Decky's loop.

        Never downloads. UI status and ordinary executable resolution do not
        invoke this work. The same cancellation/process budget applies.
        """
        with self.lock:
            if self.closed:
                raise ScreensaverError("Screensaver media tools are shutting down", "closed")
            if self.phase in {"downloading", "extracting", "verifying"} or (self.thread and self.thread.is_alive()):
                raise ScreensaverError("Screensaver media tools are busy", "busy")
            self.cancelled.clear(); self.phase = "verifying"; self.error = ""; self.percent = 0
        receipt = self._read_receipt()
        try:
            if not self._validate_receipt():
                raise ScreensaverError("Screensaver media tools need repair", "invalid_runtime")
            files = list(receipt["files"].items())
            for number, (name, record) in enumerate(files):
                self._check()
                if "link" not in record:
                    digest = hashlib.sha256()
                    with (self.directory / name).open("rb") as stream:
                        for block in iter(lambda: stream.read(65536), b""):
                            self._check(); digest.update(block)
                    if digest.hexdigest() != record.get("sha256"):
                        raise ScreensaverError("Screensaver media tools checksum changed", "checksum_failed")
                self._progress("verifying", (number + 1) * 90 / max(1, len(files)))
            self._probe(self.directory); self._check()
            self._ready = True; self._checked = True; self._progress("ready", 100)
            with self.lock: self.last_failure = {}
        except Exception as exc:
            cancelled = self.cancelled.is_set() or self.closed
            code = "cancelled" if cancelled else self._failure(exc, "verifying")
            with self.lock:
                self.phase = "cancelled" if cancelled else "failed"
                self.error = code
                self._ready = self._validate_receipt() if cancelled else False
                self._checked = True
            if receipt is not None and not cancelled:
                receipt["verified"] = False
                atomic_json(self.directory / RECEIPT, receipt)
        return self.status()

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=.5)
        except (OSError, subprocess.TimeoutExpired):
            try: os.killpg(process.pid, signal.SIGKILL)
            except OSError: pass
            try: process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired): pass

    def _download(self, archive):
        started = self.clock()
        for attempt in range(1, 4):
            self._check()
            self.download_attempt, self.downloaded_bytes = attempt, 0
            self._event('download_started', attempt=attempt)
            try:
                self._download_once(archive, started)
                self._event('download_verified', bytes=PIN_SIZE, attempt=attempt)
                return
            except Exception as error:
                code = self._failure(error, 'downloading')
                reason = getattr(error, 'reason', error)
                transient = (code in {'download_timeout', 'download_network'}
                    or isinstance(reason, ConnectionError)
                    or isinstance(error, HTTPError) and error.code in {408, 429, 500, 502, 503, 504})
                if not transient or attempt == 3 or self.clock() - started > 290: raise
                # This leaf belongs to the current isolated installation job.
                archive.unlink(missing_ok=True)
                wait = 2 ** attempt
                if isinstance(error, HTTPError):
                    retry = error.headers.get('Retry-After', '') if error.headers else ''
                    if retry.isdigit():
                        if int(retry) > 20: raise
                        wait = max(wait, int(retry))
                if self.cancelled.wait(wait): self._check()

    def _download_once(self, archive, started):
        digest, count = hashlib.sha256(), 0
        request = Request(PIN_URL, headers={"User-Agent": "GabeCubeAura-Screensaver/1", "Accept": "application/octet-stream"})
        with self._open(request) as response:
            with self.lock: self.response = response
            try:
                if not _trusted_download(response.geturl() if hasattr(response, "geturl") else PIN_URL):
                    raise ScreensaverError("Unexpected media tools download host", "download_host")
                declared = response.headers.get("Content-Length")
                if declared is not None and (not str(declared).isdigit() or int(declared) != PIN_SIZE):
                    raise ScreensaverError("Media tools size mismatch", "download_size")
                with archive.open("xb") as stream:
                    while True:
                        self._check()
                        if self.clock() - started > 300:
                            raise ScreensaverError("Media tools download timed out", "download_timeout")
                        block = response.read(65536)
                        if not block: break
                        count += len(block)
                        self.downloaded_bytes = count
                        if count > min(PIN_SIZE, MAX_DOWNLOAD):
                            raise ScreensaverError("Media tools size limit exceeded", "download_size")
                        digest.update(block); stream.write(block)
                        self._progress("downloading", count * 65 / PIN_SIZE)
                    stream.flush(); os.fsync(stream.fileno())
            finally:
                with self.lock: self.response = None
        if count != PIN_SIZE or digest.hexdigest() != PIN_SHA256:
            raise ScreensaverError("Media tools checksum mismatch", "checksum_failed")

    def _extract(self, archive, target):
        seen, links, declared, actual, count = set(), [], 0, 0, 0
        with tarfile.open(archive, "r|xz") as package:
            for entry in package:
                self._check(); count += 1
                if count > MAX_FILES:
                    raise ScreensaverError("Too many media tools archive entries", "unsafe_archive")
                original = _relative(entry.name)
                if original.parts[0] != PIN_STEM:
                    raise ScreensaverError("Unexpected media tools archive root", "unsafe_archive")
                if len(original.parts) == 1:
                    if not entry.isdir(): raise ScreensaverError("Invalid media tools root", "unsafe_archive")
                    continue
                relative = PurePosixPath(*original.parts[1:])
                name = relative.as_posix()
                if name in seen:
                    raise ScreensaverError("Duplicate media tools archive entry", "unsafe_archive")
                seen.add(name)
                destination = target.joinpath(*relative.parts)
                if entry.isdir():
                    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                if entry.issym():
                    # Shared-lib SONAME links are needed, but links may never
                    # introduce directories or leave the same library folder.
                    link = _relative(entry.linkname)
                    if len(relative.parts) != 2 or relative.parts[0] != "lib" or len(link.parts) != 1:
                        raise ScreensaverError("Unsafe media tools library link", "unsafe_archive")
                    links.append((destination, entry.linkname))
                    continue
                if not entry.isfile() or entry.size < 0:
                    raise ScreensaverError("Unsupported media tools archive entry", "unsafe_archive")
                declared += entry.size
                if declared > MAX_EXTRACTED:
                    raise ScreensaverError("Media tools extraction limit exceeded", "unsafe_archive")
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                source = package.extractfile(entry)
                if source is None: raise ScreensaverError("Incomplete media tools archive", "unsafe_archive")
                remaining = entry.size
                with source, destination.open("xb") as stream:
                    os.fchmod(stream.fileno(), 0o700 if name in {"bin/ffmpeg", "bin/ffprobe"} else 0o600)
                    while remaining:
                        self._check(); block = source.read(min(65536, remaining))
                        if not block: raise ScreensaverError("Incomplete media tools archive", "unsafe_archive")
                        remaining -= len(block); actual += len(block)
                        if actual > MAX_EXTRACTED: raise ScreensaverError("Media tools extraction limit exceeded", "unsafe_archive")
                        stream.write(block)
        # Build links after all real files, and reject dangling/cyclic targets.
        for destination, link in links:
            destination.symlink_to(link)
        for destination, _ in links:
            try:
                resolved = destination.resolve(strict=True)
                resolved.relative_to(target / "lib")
                if not resolved.is_file(): raise ValueError("not a file")
            except (OSError, RuntimeError, ValueError) as exc:
                raise ScreensaverError("Invalid media tools library link", "unsafe_archive") from exc
        if (not _elf_x86_64(target / "bin/ffmpeg") or not _elf_x86_64(target / "bin/ffprobe")
                or not (target / "lib").is_dir() or not (target / "LICENSE.txt").is_file()):
            raise ScreensaverError("Incomplete or incompatible Screensaver media tools", "invalid_runtime")

    def _probe_output(self, executable, arguments, stage):
        from das.environment import clean_environment
        self._check()
        environment = clean_environment()
        environment["LD_LIBRARY_PATH"] = str(stage / "lib")
        log = stage / ".probe-output"
        process = None
        name = {"-version": "version", "-encoders": "encoders", "-filters": "filters",
                "-decoders": "decoders"}.get(arguments[-1], "unknown")
        probe = ("ffprobe" if executable.name == "ffprobe" else "ffmpeg") + "-" + name
        started = self.clock()
        self._event('probe_started', probe=probe)
        try:
            with log.open("wb") as output:
                try:
                    process = subprocess.Popen([str(executable), *arguments], stdin=subprocess.DEVNULL,
                        stdout=output, stderr=subprocess.STDOUT, env=environment,
                        start_new_session=True, cwd=stage)
                except OSError as exc:
                    raise _ProbeFailure(probe, "spawn_failed", error_number=exc.errno) from exc
                with self.lock: self.process = process
                deadline = started + 10
                while process.poll() is None:
                    self._check()
                    if self.clock() > deadline or log.stat().st_size > 512 * 1024:
                        raise _ProbeFailure(probe, "timeout" if self.clock() > deadline else "output_limit",
                                            elapsed_ms=int((self.clock() - started) * 1000))
                    self.cancelled.wait(.05)
                self._check()
            elapsed = int((self.clock() - started) * 1000)
            if log.stat().st_size > 512 * 1024:
                raise _ProbeFailure(probe, "output_limit", exit_code=process.returncode, elapsed_ms=elapsed)
            result = log.read_text(errors="replace")
            if process.returncode:
                raise _ProbeFailure(probe, _probe_exit_reason(result, process.returncode),
                                    exit_code=process.returncode, elapsed_ms=elapsed)
            self._event('probe_passed', probe=probe, elapsed_ms=max(0, elapsed), bytes=log.stat().st_size)
            return result
        finally:
            if process is not None: self._terminate(process)
            with self.lock: self.process = None
            log.unlink(missing_ok=True)

    def _probe(self, stage):
        executable = stage / "bin/ffmpeg"
        version = self._probe_output(executable, ["-version"], stage)
        if "ffmpeg version" not in version:
            raise _ProbeFailure("ffmpeg-version", "version_output")
        if "--enable-gpl" in version or "--enable-nonfree" in version:
            raise _ProbeFailure("ffmpeg-version", "license_configuration")
        encoders = self._probe_output(executable, ["-hide_banner", "-encoders"], stage)
        filters = self._probe_output(executable, ["-hide_banner", "-filters"], stage)
        decoders = self._probe_output(executable, ["-hide_banner", "-decoders"], stage)
        if 'webp_anim' not in decoders.split():
            raise _ProbeFailure("ffmpeg-decoders", "missing_capability", missing=["webp_anim"])
        available_encoders, available_filters = set(encoders.split()), set(filters.split())
        missing = [name for name in ("libvpx-vp9", "png", "rawvideo") if name not in available_encoders]
        if missing: raise _ProbeFailure("ffmpeg-encoders", "missing_capability", missing=missing)
        # Exact names: avgblur / gblur_vulkan must not masquerade as CPU gblur.
        missing = [name for name in ("scale", "fps", "gblur", "overlay", "split", "setpts") if name not in available_filters]
        if missing: raise _ProbeFailure("ffmpeg-filters", "missing_capability", missing=missing)
        if "ffprobe version" not in self._probe_output(stage / "bin/ffprobe", ["-version"], stage):
            raise _ProbeFailure("ffprobe-version", "version_output")

    def _old_owned(self):
        if not self.directory.exists() and not self.directory.is_symlink():
            return False
        receipt = self._read_receipt()
        if receipt is None:
            raise ScreensaverError("Existing media tools are unowned; no files were replaced", "installation_conflict")
        known = {*receipt["files"], RECEIPT}
        known_dirs = {ancestor.as_posix() for name in receipt["files"]
                      for ancestor in PurePosixPath(name).parents if str(ancestor) != "."}
        for path in self.directory.rglob("*"):
            name = path.relative_to(self.directory).as_posix()
            if ((path.is_symlink() and name not in known)
                    or (path.is_dir() and not path.is_symlink() and name not in known_dirs)
                    or (not path.is_dir() and name not in known)):
                raise ScreensaverError("Media tools contain foreign files; preserve them before repair", "installation_conflict")
        return True

    def _install(self):
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            old = self._old_owned()
            if PIN_SIZE > MAX_DOWNLOAD or shutil.disk_usage(self.root).free < PIN_SIZE + MAX_EXTRACTED + DISK_RESERVE:
                raise ScreensaverError("Not enough space for optional Screensaver tools", "insufficient_storage")
            with tempfile.TemporaryDirectory(prefix=".cinema-tools-", dir=self.root) as temporary:
                temporary = Path(temporary)
                archive, stage = temporary / "download.tar.xz", temporary / "prepared"
                stage.mkdir(mode=0o700)
                self._download(archive); self._check(); self._progress("extracting", 70)
                self._extract(archive, stage); self._check(); self._progress("verifying", 90)
                self._probe(stage); self._check()
                records = {}
                for path in stage.rglob("*"):
                    name = path.relative_to(stage).as_posix()
                    if path.is_symlink(): records[name] = {"link": os.readlink(path)}
                    elif path.is_file():
                        digest = hashlib.sha256()
                        with path.open("rb") as stream:
                            for block in iter(lambda: stream.read(65536), b""): self._check(); digest.update(block)
                        info = path.stat()
                        records[name] = {"sha256": digest.hexdigest(), "size": info.st_size, "mtime_ns": info.st_mtime_ns}
                atomic_json(stage / RECEIPT, {"owner": OWNER, "verified": True, "archive_sha256": PIN_SHA256, "tag": PIN_TAG,
                    "source_url": PIN_URL, "build_source_url": BUILD_SOURCE, "ffmpeg_source_url": FFMPEG_SOURCE,
                    "files": records, "verified_codecs": ["libvpx-vp9", "png", "rawvideo", "webp_anim"],
                    "license_notice": "Original LICENSE.txt and accompanying notices are retained. No GPL/nonfree build accepted."})
                self._check()
                if not self._validate_receipt(stage):
                    raise ScreensaverError("Screensaver tools verification did not persist", "invalid_runtime")
                backup = temporary / "previous"
                if old: self.directory.rename(backup)
                try:
                    stage.rename(self.directory)
                    if not self._validate_receipt():
                        raise ScreensaverError("Screensaver tools verification did not persist", "invalid_runtime")
                except BaseException:
                    if self.directory.exists(): self.directory.rename(stage)
                    if old: backup.rename(self.directory)
                    raise
                self._ready = True; self._checked = True
                self._progress("ready", 100)
        except Exception as exc:
            with self.lock:
                stage = self.phase
                self._ready = False; self._checked = True
                self.phase = "cancelled" if self.cancelled.is_set() or self.closed else "failed"
                self.error = "cancelled" if self.phase == "cancelled" else self._failure(exc, stage)
        finally:
            with self.lock: self.response = self.process = None
