import os
import stat
from pathlib import Path

class ScreensaverInstaller:
    def __init__(self, data_root, steam_root=None, player_root=None):
        self.data_root = Path(data_root).expanduser().resolve()
        root = Path(steam_root).expanduser() if steam_root is not None else Path.home() / ".steam/root"
        self.steam_root = root.resolve()
        self.destination = self.steam_root / 'config/uioverrides/screensavers/decky-animated-screensaver'

    def _safe_parent(self, create=False):
        if not self.steam_root.is_dir():
            raise ValueError("Steam installation was not found. No files were installed.")
        current = self.steam_root
        for part in ("config", "uioverrides", "screensavers"):
            current = current / part
            if current.is_symlink():
                raise ValueError("Steam screensaver directory contains a symbolic link.")
            if create:
                try:
                    current.mkdir(mode=0o755)
                    current.chmod(0o755)  # Ignore root's private umask only on our new export ancestors.
                except FileExistsError:
                    pass
            if current.exists() and not current.is_dir():
                raise ValueError("Steam screensaver parent is not a directory.")
        return current

    @staticmethod
    def _copy(source, target, expected=None):
        # NOFOLLOW protects the final component; source ancestors have already
        # been canonicalized and constrained to the Screensaver data root.
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as incoming, target.open("xb") as outgoing:
            info = os.fstat(incoming.fileno())
            if not stat.S_ISREG(info.st_mode) or (expected is not None and
                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) !=
                    (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns)):
                raise ValueError("Screensaver media changed while being installed; retry preparation.")
            remaining = info.st_size
            while remaining:
                block = incoming.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError("Screensaver media became incomplete during installation.")
                outgoing.write(block)
                remaining -= len(block)
            if incoming.read(1):
                raise ValueError("Screensaver media grew during installation.")
            outgoing.flush()
            os.fsync(outgoing.fileno())
