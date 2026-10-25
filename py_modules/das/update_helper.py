"""Temporary independent update transaction, derived from GabeCubeAura (GPLv3).

Standard library only. No resident application, sudo, arbitrary service or shell.
Settings/media remain outside the exchanged plugin directory.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

NAME='Decky-Animated-Screensaver'

def read(path):
    if path.is_symlink() or path.stat().st_size>512*1024:raise ValueError('unsafe transaction file')
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError('invalid transaction file')
    return value

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o600);os.replace(temporary,path)

def check_tree(root,expected):
    if root.is_symlink():raise ValueError('unsafe plugin')
    manifest=read(root/'manifest.sha256.json');leaves=set()
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError('unsafe plugin link')
        if path.is_file() and path!=root/'manifest.sha256.json':leaves.add(path.relative_to(root).as_posix())
    if not manifest or leaves!=set(manifest) or len(leaves)>512:raise ValueError('invalid plugin manifest')
    for relative,digest in manifest.items():
        path=Path(relative)
        if path.is_absolute() or '..' in path.parts or '\\' in relative or not re.fullmatch(r'[a-f0-9]{64}',str(digest)):raise ValueError('unsafe plugin manifest')
        leaf=root/relative
        if leaf.stat().st_size>512*1024 or hashlib.sha256(leaf.read_bytes()).hexdigest()!=digest:raise ValueError('changed plugin content')
    if not {'main.py','plugin.json','package.json','dist/index.js','LICENSE','py_modules/das/__init__.py'}<=leaves:raise ValueError('incomplete plugin')
    plugin=read(root/'plugin.json')
    if read(root/'package.json').get('version')!=expected or plugin.get('name') not in {NAME,'Animated Screensaver'} or plugin.get('flags')!=['root']:raise ValueError('wrong plugin identity')

def exchange(first,second):
    libc=ctypes.CDLL(None,use_errno=True);rename=libc.renameat2
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];rename.restype=ctypes.c_int
    if rename(-100,os.fsencode(first),-100,os.fsencode(second),2)!=0:raise OSError(ctypes.get_errno(),'atomic exchange failed')

class Service:
    def command(self,action):return subprocess.run(['systemctl',action,'plugin_loader.service'],check=True,capture_output=True,timeout=25)
    def stop(self):self.command('stop')
    def start(self):self.command('start')
    def wait_inactive(self):
        for _ in range(80):
            result=subprocess.run(['systemctl','is-active','plugin_loader.service'],capture_output=True,timeout=5)
            if result.returncode!=0:return True
            time.sleep(.25)
        return False

def healthy(path,token,expected,timeout=45):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=read(path)
            if value.get('token')==token and value.get('version')==expected:return True
        except (OSError,ValueError):pass
        time.sleep(.5)
    return False

def transaction(tx,service=None,swapper=exchange,health=healthy):
    if not re.fullmatch(r'[a-f0-9]{32}',str(tx.get('token',''))):raise ValueError('invalid update token')
    root=Path(tx['root']);active=Path(tx['active']);staged=Path(tx['staged'])
    for path in (root,active,staged):
        if not path.is_absolute() or path.is_symlink() or path.resolve()!=path:raise ValueError('unsafe update path')
    if active.name!=NAME or staged.name!=NAME or not staged.is_relative_to(root/'staged') or staged.parent.parent!=root/'staged':raise ValueError('wrong update paths')
    if root.is_relative_to(active) or active.is_relative_to(root):raise ValueError('settings must stay outside plugin')
    if read(active/'plugin.json').get('name') not in {NAME,'Animated Screensaver'} or read(active/'package.json').get('version')!=tx['from_version']:raise ValueError('active plugin changed')
    check_tree(staged,tx['to_version'])
    result=root/'result.json';health_file=root/'health'/(tx['token']+'.json');health_file.unlink(missing_ok=True)
    service=service or Service();swapped=False;stopped=False
    try:
        write(result,dict(phase='installing',error=''))
        stopped=True;service.stop()
        if not service.wait_inactive():raise ValueError('Decky failed to stop')
        check_tree(staged,tx['to_version']);swapper(active,staged);swapped=True
        service.start()
        if not health(health_file,tx['token'],tx['to_version']):raise ValueError('backend health timeout')
        value=dict(phase='updated',error='',rollback=str(staged),version=tx['to_version'])
    except Exception:
        try:
            if swapped:
                service.stop()
                if not service.wait_inactive():raise ValueError('Decky failed to stop for rollback')
                swapper(active,staged)
            if stopped:service.start()
            value=dict(phase='rolled_back',error='update_rolled_back',version=tx['from_version'])
        except Exception:value=dict(phase='error',error='update_recovery_failed')
    write(result,value);return value

if __name__=='__main__':
    try:
        path=Path(sys.argv[1]);tx=read(path)
        if path.name!='transaction.json' or path.parent.resolve()!=Path(tx['root']):raise ValueError('wrong transaction file')
        transaction(tx)
    except Exception:
        # No raw exception paths, transaction contents or authorization data.
        try:
            runtime=Path(__file__).resolve().parent
            if path.name=='transaction.json' and path.parent.resolve()==runtime:write(runtime/'result.json',dict(phase='error',error='update_helper_failed'))
        except Exception:pass
        sys.exit(2)
