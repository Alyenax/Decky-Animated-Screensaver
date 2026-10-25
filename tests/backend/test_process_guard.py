"""Harmless real process trees, never a Decky executable or real media/device."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from das.core import process_guard as guard
from das.core.catalog import ScreensaverError


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('Test process did not reach its expected state')


def running(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    stat = Path('/proc')/str(pid)/'stat'
    try:
        if stat.is_file() and stat.read_bytes().rsplit(b') ', 1)[1].split()[0] == b'Z': return False
    except FileNotFoundError: return False
    return True


class ScreensaverProcessGuardTests(unittest.TestCase):
    def test_frozen_decky_and_symlink_alias_are_never_python_candidates(self):
        with tempfile.TemporaryDirectory() as name:
            loader = Path(name) / 'PluginLoader'; loader.write_bytes(b'fixture'); loader.chmod(0o700)
            alias = Path(name) / 'python3'; alias.symlink_to(loader)
            with patch.object(guard.sys, 'frozen', True, create=True), \
                 patch.object(guard.sys, 'executable', str(loader)):
                for candidate in (None, str(loader), str(alias)):
                    with patch.object(guard.shutil, 'which', return_value=candidate):
                        with self.assertRaises(ScreensaverError) as caught: guard.system_python(os.environ)
                        self.assertEqual(caught.exception.code, 'python_missing')
                with patch.object(guard.shutil, 'which', return_value=shutil.which('python3')):
                    self.assertNotEqual(guard.system_python(os.environ), str(loader))

    def test_pyinstaller_environment_never_reaches_system_launcher(self):
        environment = guard.clean_child_environment({'PATH':'/usr/bin', 'LD_LIBRARY_PATH':'/unsafe',
            'LD_PRELOAD':'secret', 'PYTHONHOME':'secret', 'PYTHONPATH':'secret',
            '_PYI_APPLICATION_HOME_DIR':'secret', '_PYI_PARENT_PROCESS_LEVEL':'2', '_MEIPASS2':'secret'})
        self.assertEqual(set(environment), {'PATH', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS'})

    def test_group_rss_counts_only_our_group_and_handles_spaces_in_process_names(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for pid, group, pages in [(100, 42, 3), (101, 42, 5), (102, 43, 10000)]:
                directory = root / str(pid); directory.mkdir()
                fields = ['0'] * 22; fields[0] = 'S'; fields[2] = str(group); fields[21] = str(pages)
                (directory / 'stat').write_text(f'{pid} (a process (with spaces)) ' + ' '.join(fields))
            self.assertEqual(guard.group_rss(42, root), 8 * os.sysconf('SC_PAGE_SIZE'))

    def test_linux_resource_limits_contract_without_limiting_the_test_runner(self):
        import resource
        with patch.object(guard.sys, 'platform', 'linux'), patch.object(resource, 'setrlimit') as limit:
            guard.apply_limits()
        self.assertEqual([call.args for call in limit.call_args_list], [
            (resource.RLIMIT_AS, (guard.ADDRESS_LIMIT, guard.ADDRESS_LIMIT)),
            (resource.RLIMIT_CPU, (180, 185)), (resource.RLIMIT_CORE, (0, 0))])

    def test_real_capture_is_bounded_and_preserves_only_requested_output(self):
        result = guard.capture([sys.executable, '-c', "print('metadata')"],
            environment=os.environ, timeout=3, maximum=1024)
        self.assertEqual(result.strip(), b'metadata')
        with self.assertRaises(ScreensaverError):
            guard.capture([sys.executable, '-c', "print('x'*4096)"],
                environment=os.environ, timeout=3, maximum=16)

    def test_lifeline_eof_kills_worker_and_grandchild(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); ready = root / 'pids.json'
            child = "import subprocess,sys,os,time,json; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); open(sys.argv[1],'w').write(json.dumps([os.getpid(),p.pid])); time.sleep(30)"
            with (root/'stderr').open('wb') as log:
                process, writer = guard.spawn([sys.executable, '-c', child, str(ready)],
                    environment=os.environ, stderr=log, cwd=root)
                try:
                    wait_for(lambda: ready.is_file() and ready.stat().st_size > 0)
                    pids = json.loads(ready.read_text())
                    os.close(writer); writer = None
                    process.wait(timeout=5)
                    for pid in pids: wait_for(lambda p=pid: not running(p))
                finally:
                    if writer is not None: os.close(writer)
                    if process.poll() is None: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)

    def test_guard_holds_preparation_lease_after_parent_closes_its_descriptor(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); lease = root/'lease'
            fd = os.open(lease, os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(fd, fcntl.LOCK_EX)
            with (root/'stderr').open('wb') as log:
                process, writer = guard.spawn([sys.executable, '-c', 'import time;time.sleep(30)'],
                    environment=os.environ, stderr=log, cwd=root, lease_fd=fd)
                os.close(fd)
                try:
                    with lease.open('rb') as competitor:
                        with self.assertRaises(BlockingIOError): fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        os.close(writer); writer = None
                        process.wait(timeout=5)
                        fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    if writer is not None: os.close(writer)
                    if process.poll() is None: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)

    def test_actual_parent_death_stops_the_supervised_tree(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); ready = root/'guard-pid'
            helper = "from das.core.process_guard import spawn; import os,sys; from pathlib import Path; root=Path(sys.argv[1]); log=open(root/'stderr','wb'); p,w=spawn([sys.executable,'-c','import time;time.sleep(30)'],environment=os.environ,stderr=log,cwd=root); (root/'guard-pid').write_text(str(p.pid)); sys.stdin.buffer.read(1); os._exit(0)"
            environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]/'py_modules'))
            parent = subprocess.Popen([sys.executable, '-c', helper, str(root)], stdin=subprocess.PIPE, env=environment)
            pid = None
            try:
                wait_for(lambda: ready.is_file() and ready.stat().st_size > 0)
                pid = int(ready.read_text())
                parent.communicate(b'x', timeout=5)
                wait_for(lambda: not running(pid))
            finally:
                if parent.poll() is None: parent.kill(); parent.wait(timeout=5)
                if pid is not None and running(pid) and os.getpgid(pid) == pid: os.killpg(pid, signal.SIGKILL)

    def test_loader_owner_death_stops_worker_even_when_backend_keeps_pipe_open(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); ready = root/'ready'
            owner = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'], start_new_session=True)
            process = writer = None
            with (root/'stderr').open('wb') as log:
                try:
                    command = [sys.executable, '-c', "from pathlib import Path;import sys,time;Path(sys.argv[1]).touch();time.sleep(30)", str(ready)]
                    process, writer = guard.spawn(command, environment=os.environ, stderr=log,
                        cwd=root, owner_pid=owner.pid)
                    wait_for(ready.exists)
                    owner.terminate(); owner.wait(timeout=5)
                    process.wait(timeout=5)
                    os.fstat(writer)  # Backend/lifeline remains alive: owner detection caused the stop.
                    self.assertNotEqual(process.returncode, 0)
                finally:
                    if writer is not None: os.close(writer)
                    if process is not None and process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
                    if owner.poll() is None: owner.kill(); owner.wait(timeout=5)


if __name__ == '__main__': unittest.main()
