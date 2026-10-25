"""Bounded offline media subprocess supervision. No USB or playback-side encoding."""

from __future__ import annotations

import json
from fractions import Fraction
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from das.core.catalog import ScreensaverError, atomic_json
    from das.core.process_guard import capture, spawn, system_python, failure_evidence
else:
    from .catalog import ScreensaverError, atomic_json
    from .process_guard import capture, spawn, system_python, failure_evidence


MAX_TV_BYTES = 64 * 1024 * 1024
MAX_PROCESS_SECONDS = 180


def capabilities():
    return {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe"))}


def _decoder_environment(library_path=None):
    from das.environment import clean_environment
    environment = clean_environment()
    if library_path:
        # Never append the host's LD_LIBRARY_PATH. Only the locally verified,
        # explicitly installed Screensaver runtime's libraries enter its subprocess.
        environment["LD_LIBRARY_PATH"] = str(library_path)
    return environment


class FFmpegMediaCompiler:
    def __init__(self, ffmpeg=None, library_path=None, clock=time.monotonic):
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")
        self.library_path = None
        self.clock = clock
        self.last_failure = {}
        self.lease_fd = None
        self._owner_pid = os.getppid()
        self._process_lock = threading.RLock()
        self._process = None
        self._decoder_support = None
        self._capability_error = ''
        if library_path:
            self.configure_runtime(self.ffmpeg, library_path)

    def configure_runtime(self, executable, library_path=None):
        """Called by the owner's verified resource manager, never an RPC path.

        Validation here is path hygiene, not a substitute for the resource
        manager's pinned archive/binary hashes and explicit download consent.
        """
        self._decoder_support = None
        self._capability_error = ''
        if executable is None:
            self.ffmpeg, self.library_path = shutil.which("ffmpeg"), None
            return
        executable = Path(executable)
        if (not executable.is_absolute() or executable.is_symlink()
                or not executable.is_file() or not os.access(executable, os.X_OK)):
            raise ScreensaverError("The verified Screensaver encoder is unavailable", "ffmpeg_missing")
        if library_path is not None:
            library_path = Path(library_path)
            if not library_path.is_absolute() or library_path.is_symlink() or not library_path.is_dir():
                raise ScreensaverError("The Screensaver runtime library directory is invalid", "unsafe_path")
        self.ffmpeg = str(executable)
        self.library_path = str(library_path) if library_path else None

    def _environment_for(self, command):
        is_decoder = self.ffmpeg is not None and str(command[0]) == str(self.ffmpeg)
        return _decoder_environment(self.library_path if is_decoder else None)

    def capabilities(self):
        # Page/preparation request only, cached per chosen executable. No probe
        # at construction, no periodic worker and no reliance on version text.
        if self.ffmpeg and self._decoder_support is None:
            try:
                output = capture([self.ffmpeg, '-hide_banner', '-decoders'],
                    environment=_decoder_environment(self.library_path), timeout=4,
                    maximum=512 * 1024, lease_fd=self.lease_fd, owner_pid=self._owner_pid)
                self._decoder_support = b'webp_anim' in output.split()
            except (ScreensaverError, OSError, subprocess.TimeoutExpired) as error:
                self._decoder_support = False
                self._capability_error = getattr(error, 'code', 'runtime_isolation')
        return {"ffmpeg": bool(self.ffmpeg and self._decoder_support),
                "ffmpeg_found": bool(self.ffmpeg), "animated_webp": bool(self._decoder_support),
                "ffprobe": bool(shutil.which("ffprobe")), 'error': self._capability_error}

    def _native_webm(self, source, directory, checkpoint):
        """Keep compatible silent VP8/VP9 bytes; uncertain inputs use encoding.

        No assumption that a .webm suffix establishes its codec. Metadata-only
        probe is bounded and used only by explicit background preparation.
        """
        probe = Path(self.ffmpeg).with_name('ffprobe') if self.ffmpeg else None
        if not probe or not probe.is_file():
            found = shutil.which('ffprobe')
            probe = Path(found) if found else None
        if not probe or source.suffix.lower() != '.webm' or source.stat().st_size >= MAX_TV_BYTES:
            return None
        checkpoint()
        try:
            output = capture([str(probe), '-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-f', 'matroska', '-show_entries', 'stream=codec_type,codec_name,width,height,r_frame_rate:format=duration',
                '-of', 'json', str(source)], environment=_decoder_environment(self.library_path), timeout=8,
                maximum=65536, checkpoint=checkpoint, lease_fd=self.lease_fd, owner_pid=self._owner_pid)
            details = json.loads(output)
            streams = details.get('streams', [])
            visual = [stream for stream in streams if stream.get('codec_type') == 'video']
            if len(visual) != 1 or any(stream.get('codec_type') == 'audio' for stream in streams): return None
            video = visual[0]
            width, height = int(video['width']), int(video['height'])
            duration = float(details['format']['duration'])
            rate = str(video.get('r_frame_rate', ''))
            if len(rate) > 40: return None
            cadence = float(Fraction(rate))
            # Never increase native playback's resolution/cadence budget above
            # the existing conservative TV path without target-device evidence.
            if (video.get('codec_name') not in {'vp8', 'vp9'} or not 0 < width <= 1280
                    or not 0 < height <= 720 or not 0 < cadence <= 30 or not 0 < duration <= 600): return None
            checkpoint()
            return {'width': width, 'height': height, 'duration': duration, 'codec': video['codec_name']}
        except ScreensaverError as error:
            if error.code not in {'decode_failed', 'decode_timeout'}: raise
            return None
        except (OSError, ValueError, ZeroDivisionError, OverflowError, KeyError, TypeError, subprocess.TimeoutExpired):
            return None

    def _run(self, command, directory, checkpoint, timeout=MAX_PROCESS_SECONDS):
        """One process group, cancellable between 100 ms waits, bounded stderr."""
        log = Path(directory) / ".decoder.log"
        process = None
        lifeline = None
        start = self.clock()
        try:
            with log.open("wb") as stderr:
                checkpoint()
                try:
                    process, lifeline = spawn(command, environment=self._environment_for(command),
                        stderr=stderr, cwd=directory, lease_fd=self.lease_fd, owner_pid=self._owner_pid)
                except OSError as error:
                    raise ScreensaverError('Screensaver could not start its isolated process', 'runtime_isolation') from error
                with self._process_lock: self._process = process
                while process.poll() is None:
                    checkpoint()
                    if self.clock() - start > timeout:
                        raise ScreensaverError("Screensaver decoder exceeded its time budget", "decode_timeout")
                    if log.stat().st_size > 1024 * 1024:
                        self.last_failure = {'process': 'ffmpeg' if str(command[0]) == str(self.ffmpeg) else 'media-worker',
                                             'exit_code': None, 'signals': ['excessive_errors']}
                        raise ScreensaverError("Screensaver decoder produced excessive errors", "decode_failed")
                    time.sleep(0.1)
                checkpoint()
                if process.returncode:
                    with log.open('rb') as stream:
                        stream.seek(max(0, log.stat().st_size - 8192))
                        tail = stream.read(8192).decode('utf-8', errors='replace').lower()
                    # Known signal names only, never stderr paths/argv/URLs.
                    self.last_failure=failure_evidence(command,process.returncode,tail)
                    exit_code=self.last_failure.get('exit_code');flags=self.last_failure['signals']
                    if exit_code is None:exit_code=process.returncode
                    # Do not return argv, source URLs or arbitrary decoder output to diagnostics.
                    code = ('resource_limit' if 'memory_limit' in flags else
                            'runtime_isolation' if 'isolation_failed' in flags else
                            'worker_signal' if exit_code < 0 or exit_code >= 128 else 'decode_failed')
                    error=ScreensaverError('Screensaver conversion stopped; see its diagnostic',code)
                    error.process_failure=dict(self.last_failure);raise error
        finally:
            if lifeline is not None: os.close(lifeline)
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    process.wait(timeout=2.0)
            with self._process_lock:
                if self._process is process: self._process = None
            log.unlink(missing_ok=True)

    def cancel(self):
        with self._process_lock: process = self._process
        if process is not None and process.poll() is None:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
