"""Short-lived conversion supervisor; never launched by importing this module.

The Decky parent alone holds a pipe writer. EOF kills this new process group,
including nested decoders, even if the parent died without running finally.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time


ADDRESS_LIMIT = 1536 * 1024 * 1024
RSS_LIMIT = 768 * 1024 * 1024

FAILURE_FLAGS=(
    ('memory_limit',r'cinema_memory_limit'),('isolation_failed',r'cinema_guard_failed|cinema_parent_lost'),
    ('cancelled',r'cinema_cancelled'),('shared_library_missing',r'error while loading shared librar'),
    ('glibc_version',r'glibc_[0-9.]+.*not found'),('decoder_missing',r'unknown decoder|decoder.*not found'),
    ('invalid_input',r'invalid data found'),('no_video_stream',r'does not contain any stream|matches no streams'),
    ('allocation_failed',r'cannot allocate memory|out of memory'),('filter_missing',r'no such filter'),
    ('permission_denied',r'permission denied'),('excessive_errors',r'excessive_errors'))

def failure_snapshot(value):
    """Allowlist subprocess evidence, including untrusted persisted metadata."""
    if not isinstance(value,dict):return {}
    result={}
    if isinstance(value.get('process'),str) and value['process'] in {'ffmpeg','ffprobe','media-worker'}:result['process']=value['process']
    for key in ('exit_code','supervisor_exit_code'):
        code=value.get(key)
        if code is None or type(code) is int and -255<=code<=255:result[key]=code
    if isinstance(value.get('exit_source'),str) and value['exit_source'] in {'payload','supervisor'}:result['exit_source']=value['exit_source']
    flags=value.get('signals',[])
    result['signals']=[name for name,_ in FAILURE_FLAGS if isinstance(flags,list) and name in flags]
    return result if 'process' in result else {}

def failure_evidence(command,returncode,detail):
    """Keep fixed labels and exit values, never argv, stderr or source paths."""
    detail=detail[-8192:].lower();payload=re.search(r'cinema_payload_exit=(-?\d{1,3})(?!\d)',detail)
    if payload and not -255<=int(payload[1])<=255:payload=None
    name=Path(str(command[0])).name
    return failure_snapshot(dict(process=name if name in {'ffmpeg','ffprobe'} else 'media-worker',
        exit_code=int(payload[1]) if payload else returncode,supervisor_exit_code=returncode,
        exit_source='payload' if payload else 'supervisor',
        signals=[name for name,pattern in FAILURE_FLAGS if re.search(pattern,detail)]))


def system_python(environment):
    from .catalog import ScreensaverError
    candidate = shutil.which('python3', path=environment.get('PATH', os.defpath))
    try:
        path = Path(candidate).resolve(strict=True) if candidate else None
        host = Path(sys.executable).resolve() if sys.executable else None
        if (path is None or not path.is_file() or not os.access(path, os.X_OK)
                or not re.fullmatch(r'python3(?:\.\d+)?', path.name, re.IGNORECASE)
                or getattr(sys, 'frozen', False) and path == host):
            raise ValueError('not an external Python')
    except (OSError, RuntimeError, ValueError) as error:
        raise ScreensaverError('System Python 3 is unavailable; Screensaver was not launched', 'python_missing') from error
    return str(path)


def clean_child_environment(environment):
    environment = dict(environment)
    for key in list(environment):
        if key in {'LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONHOME', 'PYTHONPATH', '_MEIPASS2', 'GABECUBE_CINEMA_CHILD_LIB'} or key.startswith('_PYI_'):
            environment.pop(key, None)
    environment.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    return environment


def spawn(command, *, environment, stderr, cwd, lease_fd=None, stdout=subprocess.DEVNULL, owner_pid=None):
    """Only an external system Python may interpret this guard or media.py."""
    launcher_environment = clean_child_environment(environment)
    interpreter = system_python(launcher_environment)
    library = environment.get('LD_LIBRARY_PATH', '')
    if library:
        launcher_environment['GABECUBE_CINEMA_CHILD_LIB'] = library
    reader, writer = os.pipe()
    passed = (reader,) if lease_fd is None else (reader, lease_fd)
    try:
        process = subprocess.Popen([interpreter, str(Path(__file__).resolve()),
            str(reader), str(os.getpid()), str(owner_pid or os.getppid()), '--', *map(str, command)],
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            env=launcher_environment, cwd=cwd, start_new_session=True, close_fds=True, pass_fds=passed)
        return process, writer
    except BaseException:
        os.close(writer)
        raise
    finally:
        os.close(reader)


def capture(command, *, environment, timeout, maximum, checkpoint=lambda: None, lease_fd=None, owner_pid=None):
    """Metadata probes also get a lifeline and limits; never unbounded PIPE RAM."""
    from .catalog import ScreensaverError
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process, writer = spawn(command, environment=environment, stdout=output,
                                stderr=errors, cwd=None, lease_fd=lease_fd, owner_pid=owner_pid)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                checkpoint()
                if time.monotonic() >= deadline:
                    raise ScreensaverError('Screensaver probe timed out', 'decode_timeout')
                if os.fstat(output.fileno()).st_size > maximum or os.fstat(errors.fileno()).st_size > 1024 * 1024:
                    raise ScreensaverError('Screensaver probe output limit exceeded', 'decode_failed')
                time.sleep(.05)
            if process.returncode:
                errors.seek(max(0, os.fstat(errors.fileno()).st_size - 8192))
                detail = errors.read(8192).decode(errors='replace')
                evidence=failure_evidence(command,process.returncode,detail);code=evidence.get('exit_code')
                if code is None:code=process.returncode
                category = ('resource_limit' if 'memory_limit' in evidence['signals'] else
                            'runtime_isolation' if 'isolation_failed' in evidence['signals'] else
                            'worker_signal' if code < 0 or code >= 128 else 'decode_failed')
                error=ScreensaverError('Screensaver probe stopped',category);error.process_failure=evidence
                raise error
            if os.fstat(output.fileno()).st_size > maximum:
                raise ScreensaverError('Screensaver probe output limit exceeded', 'decode_failed')
            output.seek(0)
            return output.read(maximum)
        finally:
            os.close(writer)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.wait(timeout=2)


def apply_limits():
    if sys.platform.startswith('linux'):
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_LIMIT, ADDRESS_LIMIT))
        resource.setrlimit(resource.RLIMIT_CPU, (180, 185))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def group_rss(group, proc_root=Path('/proc')):
    """Conservative sum of RSS for the supervised group (shared pages may repeat)."""
    total = 0
    page = os.sysconf('SC_PAGE_SIZE')
    with os.scandir(proc_root) as entries:
        for entry in entries:
            if not entry.name.isdecimal(): continue
            try:
                with open(Path(entry.path) / 'stat', 'rb') as stream:
                    fields = stream.read(4096).rsplit(b') ', 1)[1].split()
                if int(fields[2]) == group:
                    total += max(0, int(fields[21])) * page
            except (FileNotFoundError, ProcessLookupError):
                continue
    return total


def _kill_group(marker):
    print(marker, file=sys.stderr, flush=True)
    # Only the session/group created for this guard; never a parent/system PID.
    if os.getpgrp() != os.getpid(): raise RuntimeError('Screensaver guard is not isolated')
    os.killpg(os.getpid(), signal.SIGKILL)


def owner_alive(pid):
    # Decky can use KillMode=process: also observe its original parent process
    # in case the plugin backend survives the main loader. PID 1 is not a loader.
    if pid <= 1: return True
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    if sys.platform.startswith('linux'):
        try:
            with open(f'/proc/{pid}/stat', 'rb') as stream:
                if stream.read(4096).rsplit(b') ', 1)[1].split()[0] == b'Z': return False
        except FileNotFoundError: return False
    return True


def main(argv):
    if len(argv) < 6 or argv[4] != '--' or os.getpgrp() != os.getpid(): return 64
    reader, parent, owner = int(argv[1]), int(argv[2]), int(argv[3])
    if os.getppid() != parent: _kill_group('cinema_parent_lost')
    stopping = [False]
    signal.signal(signal.SIGTERM, lambda *_: stopping.__setitem__(0, True))
    try:
        apply_limits()
        try: os.nice(15)
        except OSError: pass  # Sandboxed development hosts may deny priority changes.
        environment = dict(os.environ)
        library = environment.pop('GABECUBE_CINEMA_CHILD_LIB', '')
        if library: environment['LD_LIBRARY_PATH'] = library
        # Payload and all descendants stay in our group. Caught signals are
        # reset by exec, unlike SIG_IGN; payload SIGTERM is therefore normal.
        process = subprocess.Popen(argv[5:], env=environment, close_fds=True)
        next_memory_check = 0.0
        while True:
            if stopping[0]: _kill_group('cinema_cancelled')
            if not owner_alive(owner): _kill_group('cinema_parent_lost')
            readable, _, _ = select.select([reader], [], [], .05)
            if readable and not os.read(reader, 1): _kill_group('cinema_parent_lost')
            code = process.poll()
            if code is not None:
                if code: _kill_group('cinema_payload_exit=' + str(code))
                return 0
            if sys.platform.startswith('linux') and time.monotonic() >= next_memory_check:
                if group_rss(os.getpid()) > RSS_LIMIT: _kill_group('cinema_memory_limit')
                next_memory_check = time.monotonic() + .25
    except BaseException:
        _kill_group('cinema_guard_failed')


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
