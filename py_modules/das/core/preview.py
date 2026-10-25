"""On-demand loopback streaming for Decky's explicit preview, never playback.

No media is base64-expanded into Decky's RPC/WebSocket. The native Steam player
uses its installed relative files and does not depend on this preview server.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

MIMES = {'.webm': 'video/webm', '.mp4': 'video/mp4', '.gif': 'image/gif',
         '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
MAX_MEDIA_BYTES = 128 * 1024 * 1024


class PreviewMedia:
    def __init__(self, root, *, idle_seconds=120, clock=time.monotonic, code_root=None, maximum_files=64, maximum_media_bytes=MAX_MEDIA_BYTES):
        self.root = Path(root).resolve()
        self.clock, self.idle_seconds = clock, idle_seconds
        self.lock = threading.RLock()
        self.server = self.thread = None
        self.files = {}
        self.token = secrets.token_urlsafe(32)
        self.last_used = 0.0
        self.stopping = threading.Event()
        self.code_root = Path(code_root).resolve() if code_root else None
        self.maximum_files=maximum_files
        self.maximum_media_bytes=maximum_media_bytes

    def mime(self, path):
        if path.suffix.lower() in MIMES: return MIMES[path.suffix.lower()]
        if self.code_root and path.parent == self.code_root:
            return {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[path.suffix]
        raise ValueError('Not an allowed code file')

    def _safe(self, path):
        path = Path(path)
        if '..' in path.parts:
            raise ValueError('Unsafe Screensaver preview path')
        if not path.is_absolute(): path = self.root / path
        # Resolve containment AND reject symlinks, including internal aliases.
        path.relative_to(self.root)
        for item in (path, *path.parents):
            if item == self.root: break
            if item.is_symlink(): raise ValueError('Unsafe Screensaver preview path')
        resolved = path.resolve(strict=True)
        resolved.relative_to(self.root)
        is_code = bool(self.code_root and resolved.parent == self.code_root and
                       resolved.name in {'index.html','player.js','player.css','catalog.js','diagnostic.js','diagnostic-config.js'})
        if not resolved.is_file() or resolved.suffix.lower() not in MIMES and not is_code:
            raise ValueError('Unsupported Screensaver preview media')
        if resolved.stat().st_size<=0 or self.maximum_media_bytes is not None and resolved.stat().st_size>self.maximum_media_bytes:
            raise ValueError('Screensaver preview media exceeds its limit')
        return resolved

    def url(self, path):
        resolved = self._safe(path)
        with self.lock:
            self._start()
            # Registry is bounded to one small gallery and explicit previews.
            key = next((key for key, value in self.files.items() if value == resolved), None)
            if key is None:
                if len(self.files) >= self.maximum_files:
                    if self.code_root: raise ValueError('Preview collection exceeds its limit')
                    self.files.pop(next(iter(self.files)))
                key = secrets.token_hex(12)
                self.files[key] = resolved
            self.last_used = self.clock()
            return f'http://127.0.0.1:{self.server.server_port}/{self.token}/{key}'

    def _start(self):
        if self.server is not None: return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass  # Never log capability URLs.
            def do_HEAD(self): self.serve(False)
            def do_GET(self): self.serve(True)
            def serve(self, body):
                self.connection.settimeout(2)
                parts = urlsplit(self.path).path.split('/')
                with owner.lock:
                    path = owner.files.get(parts[2]) if len(parts) == 3 and secrets.compare_digest(parts[1], owner.token) else None
                if path is None:
                    self.send_error(404); return
                try:
                    path = owner._safe(path)
                    size = path.stat().st_size
                    first, last, partial = 0, size - 1, False
                    value = self.headers.get('Range')
                    if value:
                        if not value.startswith('bytes=') or ',' in value: raise ValueError()
                        left, right = value[6:].split('-', 1)
                        if not left:
                            length = int(right)
                            if length <= 0: raise ValueError()
                            first = max(0, size - length)
                        else:
                            first = int(left)
                            last = min(size - 1, int(right)) if right else size - 1
                        if first < 0 or first >= size or last < first: raise ValueError()
                        partial = True
                except (OSError, ValueError):
                    self.send_error(416); return
                with owner.lock: owner.last_used = owner.clock()
                self.send_response(206 if partial else 200)
                self.send_header('Content-Type', owner.mime(path))
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; media-src 'self'; img-src 'self'; connect-src 'none'; frame-ancestors https://steamloopback.host http://127.0.0.1:* http://localhost:*")
                self.send_header('Content-Length', str(last - first + 1))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Access-Control-Allow-Origin', 'https://steamloopback.host')
                self.send_header('X-Content-Type-Options', 'nosniff')
                if partial: self.send_header('Content-Range', f'bytes {first}-{last}/{size}')
                self.end_headers()
                if not body: return
                try:
                    with path.open('rb') as stream:
                        stream.seek(first); remaining = last - first + 1
                        while remaining and not owner.stopping.is_set():
                            chunk = stream.read(min(65536, remaining))
                            if not chunk: break
                            self.wfile.write(chunk); remaining -= len(chunk)
                except (OSError, TimeoutError): pass

        self.stopping.clear()
        class BoundedServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(2)
                return connection, address
        server = BoundedServer(('127.0.0.1', 0), Handler)
        server.timeout = .5
        self.server = server
        def run():
            try:
                while not self.stopping.is_set() and self.clock() - self.last_used < self.idle_seconds:
                    server.handle_request()
            finally:
                server.server_close()
                with self.lock:
                    if self.server is server: self.server = None
        self.last_used = self.clock()
        self.thread = threading.Thread(target=run, name='gabecube-cinema-preview', daemon=True)
        self.thread.start()

    def close(self, timeout=3):
        self.stopping.set()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread(): thread.join(timeout=max(0.0, float(timeout)))
        with self.lock:
            self.files.clear()
            self.token = secrets.token_urlsafe(32)
