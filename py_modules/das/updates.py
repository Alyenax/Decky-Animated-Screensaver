"""Public release checks every 24 hours; verified updates require manual actions."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import threading
import time
from uuid import uuid4
from zipfile import ZipFile
from das.github import API,REPO,GitHub,UpdateError,read_json,save
from das.core.process_guard import system_python,clean_child_environment

NAME='Decky-Animated-Screensaver'
MAX_ARCHIVE=16*1024*1024
MAX_EXPANDED=64*1024*1024
CHECK_INTERVAL_MINUTES=1440
VERSION=re.compile(r'^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta)\.(0|[1-9]\d*))?$')

class UnavailableUpdater:
    """Fail closed for updates only, never take down the screensaver plugin."""
    def __init__(self,installed):self.installed=installed;self.phase='error';self.confirmation='';self.cancelled=threading.Event()
    def status(self):return dict(channel='stable',auto_check=False,interval_minutes=CHECK_INTERVAL_MINUTES,phase='error',error='update_storage',
        repository=REPO,repository_state='unchecked',repository_error='',repository_checked_at=0,installed_version=self.installed,
        available_version='',available=False,checked_at=0,percent=0,confirmation='')
    def start(self):pass
    def shutdown(self,timeout=0):pass
    def busy(self):return False
    def configure(self,patch):raise UpdateError('update_storage')
    def check(self):raise UpdateError('update_storage')
    def prepare(self):raise UpdateError('update_storage')
    def install(self,confirmation):raise UpdateError('update_storage')
    def cancel(self):self.cancelled.set()

def version(value):
    match=VERSION.fullmatch(str(value))
    if not match:raise UpdateError('update_version')
    a,b,c,kind,n=match.groups();return (int(a),int(b),int(c),{'alpha':1,'beta':2,None:3}[kind],int(n or 0))

def choose_release(rows,channel):
    if channel not in {'stable','beta'} or not isinstance(rows,list):raise UpdateError('update_metadata')
    allowed=[]
    for r in rows[:50]:
        if not isinstance(r,dict) or r.get('draft'):continue
        try:key=version(r.get('tag_name',''))
        except UpdateError:continue
        rank=key[3]
        if bool(r.get('prerelease'))!=(rank!=3):continue
        if (channel=='stable' and rank==3 or channel=='beta' and rank in {2,3}):allowed.append((key,r))
    return max(allowed,key=lambda x:x[0])[1] if allowed else None

def release_assets(release):
    v=release['tag_name'].removeprefix('v');version(v)
    if release.get('html_url')!='https://github.com/'+REPO+'/releases/tag/'+release['tag_name']:raise UpdateError('update_metadata')
    assets=release.get('assets',[]);wanted=[NAME+'-v'+v+'.zip','SHA256SUMS'];found={}
    for name in wanted:
        matches=[a for a in assets if isinstance(a,dict) and a.get('name')==name]
        if len(matches)!=1:raise UpdateError('update_missing_asset')
        a=matches[0]
        if not re.fullmatch(re.escape(API)+r'/releases/assets/[1-9][0-9]*',str(a.get('url',''))):raise UpdateError('update_unsafe_url')
        if type(a.get('size')) is not int or not 0<a['size']<=(MAX_ARCHIVE if name.endswith('.zip') else 65536):raise UpdateError('update_archive_size')
        found[name]=a
    return v,found

def checksum(raw,name):
    try:matches=[p[0] for line in raw.decode('utf8').splitlines() if len(p:=line.split())==2 and p[1].lstrip('*')==name]
    except UnicodeError:raise UpdateError('update_checksum') from None
    if len(matches)!=1 or not re.fullmatch(r'[a-f0-9]{64}',matches[0]):raise UpdateError('update_checksum')
    return matches[0]

def verify_tree(root,expected):
    manifest=read_json(root/'manifest.sha256.json')
    if not manifest or len(manifest)>512:raise UpdateError('update_manifest')
    leaves=set()
    for p in root.rglob('*'):
        if p.is_symlink():raise UpdateError('update_unsafe_path')
        if p.is_file() and p!=root/'manifest.sha256.json':leaves.add(p.relative_to(root).as_posix())
    if leaves!=set(manifest):raise UpdateError('update_manifest')
    for relative,digest in manifest.items():
        path=PurePosixPath(relative)
        if path.is_absolute() or path.as_posix()!=relative or '..' in path.parts or '\\' in relative or not re.fullmatch(r'[a-f0-9]{64}',str(digest)):
            raise UpdateError('update_manifest')
        leaf=root/relative
        if leaf.stat().st_size>512*1024 or hashlib.sha256(leaf.read_bytes()).hexdigest()!=digest:raise UpdateError('update_manifest')
    required={'main.py','plugin.json','package.json','dist/index.js','LICENSE','py_modules/das/__init__.py'}
    if not required<=leaves:raise UpdateError('update_manifest')
    package=read_json(root/'package.json');plugin=read_json(root/'plugin.json')
    if package.get('version')!=expected or plugin.get('name') not in {NAME,'Animated Screensaver'} or plugin.get('flags')!=['root']:raise UpdateError('update_identity')

def stage_archive(archive,parent,expected):
    # Inspect the small EOCD envelope before ZipFile allocates entry objects.
    # This rejects ZIP64/multipart/huge directories before metadata expansion.
    archive=Path(archive)
    if archive.is_symlink() or not 22<=archive.stat().st_size<=MAX_ARCHIVE:raise UpdateError('update_archive_size')
    with archive.open('rb') as stream:
        size=archive.stat().st_size;start=max(0,size-65557);stream.seek(start);tail=stream.read(65557)
    at=tail.rfind(b'PK\x05\x06')
    if at<0 or at+22>len(tail):raise UpdateError('update_unsafe_archive')
    _,disk,central_disk,count_here,count,central_bytes,offset,comment=struct.unpack_from('<4s4H2LH',tail,at)
    if disk or central_disk or count_here!=count or not 1<=count<=512 or central_bytes>512*1024 or offset+central_bytes!=start+at or at+22+comment!=len(tail):
        raise UpdateError('update_unsafe_archive')
    version(expected);parent=Path(parent).resolve();parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    directory=Path(tempfile.mkdtemp(prefix='validated-',dir=parent));root=directory/NAME
    try:
        with ZipFile(archive) as z:
            entries=z.infolist();seen=set();total=0
            if not 1<=len(entries)<=512:raise UpdateError('update_archive_size')
            for item in entries:
                path=PurePosixPath(item.filename);mode=item.external_attr>>16;kind=stat.S_IFMT(mode)
                if (path.is_absolute() or '..' in path.parts or '\\' in item.filename or not path.parts or path.parts[0]!=NAME or
                    path.as_posix()!=item.filename.rstrip('/') or item.filename.casefold() in seen or item.flag_bits&1 or
                    kind not in {0,stat.S_IFREG,stat.S_IFDIR} or item.file_size>512*1024):raise UpdateError('update_unsafe_archive')
                seen.add(item.filename.casefold());total+=item.file_size
            if total>MAX_EXPANDED or shutil.disk_usage(parent).free<total+32*1024*1024:raise UpdateError('update_storage')
            for item in entries:
                target=directory/item.filename
                if item.is_dir():target.mkdir(parents=True,exist_ok=True,mode=0o755);continue
                target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
                with z.open(item) as source,target.open('xb') as out:
                    remaining=item.file_size
                    while remaining:
                        block=source.read(min(65536,remaining))
                        if not block:raise UpdateError('update_unsafe_archive')
                        out.write(block);remaining-=len(block)
                    if source.read(1):raise UpdateError('update_unsafe_archive')
                target.chmod(0o644)
        verify_tree(root,expected);return root
    except Exception:
        shutil.rmtree(directory);raise

class Updater:
    def __init__(self,root,plugin,installed,blocked=lambda:False,opener=None,install_lock=None):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.plugin=Path(plugin).resolve();self.installed=installed;self.blocked=blocked
        # Share the RPC/work-start lock when embedded in the plugin. Always
        # acquire it before the updater lock to avoid inverted lock order.
        self.install_lock=install_lock if install_lock is not None else threading.RLock()
        self.github=GitHub(**({'opener':opener} if opener else {}))
        self.path=self.root/'preferences.json'
        saved=read_json(self.path)
        self.preferences={'channel':saved.get('channel') if saved.get('channel') in {'stable','beta'} else 'stable',
            'auto_check':saved.get('auto_check') if type(saved.get('auto_check')) is bool else True,
            'interval_minutes':CHECK_INTERVAL_MINUTES}
        # Ignore legacy auth files and automatic-install preferences. Never use
        # credentials or reactivate automation when migrating a private setup.
        self.lock=threading.RLock();self.thread=None;self.closed=threading.Event();self.cancelled=threading.Event();self.reschedule=threading.Event()
        self.phase='idle';self.error='';self.release=None;self.staged=None;self.confirmation='';self.percent=0;self.checked_at=0;self.scheduler=None
        self.repository_state='unchecked';self.repository_error='';self.repository_checked_at=0
        self.preference_epoch=0
        last=read_json(self.root/'result.json')
        if last.get('phase') in {'installing','updated','rolled_back','error'}:
            self.phase=last['phase'];self.error=str(last.get('error',''))[:80]
        self.acknowledge()
    def acknowledge(self):
        tx=read_json(self.root/'transaction.json')
        if tx.get('to_version')==self.installed and re.fullmatch(r'[a-f0-9]{32}',str(tx.get('token',''))):
            # Backend-ready handshake only. Real Steam rendering still needs a
            # physical test; this does not pretend to check frontend health.
            save(self.root/'health'/(''+tx['token']+'.json'),dict(token=tx['token'],version=self.installed))
    def busy(self):return bool(self.thread and self.thread.is_alive()) or self.phase=='installing'
    def cancel(self):
        with self.lock:self.cancelled.set();self.reschedule.set()
    def status(self):
        r=self.release or {}
        try:result=read_json(self.root/'result.json') if self.phase=='installing' else {}
        except UpdateError:result=dict(phase='error',error='update_storage')
        if result.get('phase') in {'updated','rolled_back','error'}:self.phase=result['phase'];self.error=result.get('error','')
        return dict(**self.preferences,phase=self.phase,error=self.error,
            repository=REPO,repository_state=self.repository_state,repository_error=self.repository_error,
            repository_checked_at=self.repository_checked_at,installed_version=self.installed,available_version=r.get('tag_name','').removeprefix('v'),
            available=bool(r and version(r['tag_name'])>version(self.installed)),checked_at=self.checked_at,percent=self.percent,
            confirmation=self.confirmation if self.phase=='ready' else '')
    def configure(self,patch):
        with self.lock:
            if not isinstance(patch,dict) or set(patch)-set(self.preferences):raise UpdateError('update_preferences')
            if 'channel' in patch and patch['channel'] not in {'stable','beta'}:raise UpdateError('update_preferences')
            if any(key in patch and type(patch[key]) is not bool for key in ('auto_check',)):raise UpdateError('update_preferences')
            if 'interval_minutes' in patch and (type(patch['interval_minutes']) is not int or patch['interval_minutes']!=CHECK_INTERVAL_MINUTES):raise UpdateError('update_preferences')
            channel_changed=patch.get('channel',self.preferences['channel'])!=self.preferences['channel']
            if self.busy() and channel_changed:raise UpdateError('update_busy')
            updated={**self.preferences,**patch}
            save(self.path,updated);self.preferences=updated;self.preference_epoch+=1
            if channel_changed:self.release=None;self.confirmation='';self.phase='idle';self.error=''
            self.reschedule.set()
    def start(self):
        if self.closed.is_set() or self.scheduler and self.scheduler.is_alive():return
        def schedule():
            # Wait a full day on startup too. Manual checks remain immediate.
            next_check=time.monotonic()+CHECK_INTERVAL_MINUTES*60;epoch=self.preference_epoch
            while not self.closed.is_set():
                changed=self.reschedule.wait(max(0,next_check-time.monotonic()))
                if self.closed.is_set():return
                if changed:self.reschedule.clear()
                if epoch!=self.preference_epoch:
                    epoch=self.preference_epoch;next_check=time.monotonic()+CHECK_INTERVAL_MINUTES*60
                if time.monotonic()<next_check:continue
                if self.preferences['auto_check'] and not self.blocked() and not self.busy() and self.phase!='ready':
                    try:self.check()
                    except UpdateError:pass
                next_check=time.monotonic()+CHECK_INTERVAL_MINUTES*60
        self.scheduler=threading.Thread(target=schedule,name='das-update-check',daemon=True);self.scheduler.start()
    def launch(self,phase,callback):
        with self.lock:
            if self.busy() or self.closed.is_set():raise UpdateError('update_busy')
            self.phase=phase;self.error='';self.percent=0;self.cancelled.clear()
            def run():
                try:callback()
                except Exception as error:
                    self.error=error.code if isinstance(error,UpdateError) else 'update_failed';self.phase='error'
                finally:self.reschedule.set()
            self.thread=threading.Thread(target=run,name='das-update-'+phase,daemon=True);self.thread.start()
    def checkpoint(self):
        if self.cancelled.is_set() or self.closed.is_set():raise UpdateError('update_cancelled')
    def check(self):
        def work():
            try:
                raw=self.github.fetch(API+'/releases?per_page=50',512*1024);self.checkpoint()
                release=choose_release(json.loads(raw),self.preferences['channel'])
                if release:release_assets(release)
            except Exception as error:
                with self.lock:
                    self.repository_error=error.code if isinstance(error,UpdateError) else 'update_metadata'
                    self.repository_state='error';self.repository_checked_at=int(time.time())
                raise
            with self.lock:
                self.repository_state='ready';self.repository_error='';self.repository_checked_at=int(time.time())
                self.release=release;self.checked_at=self.repository_checked_at
                self.phase='available' if release and version(release['tag_name'])>version(self.installed) else 'current'
        with self.lock:
            if self.repository_state=='checking' or self.phase=='ready':raise UpdateError('update_busy')
            self.launch('checking',work)
    def prepare(self):
        if self.blocked():raise UpdateError('update_game_or_preparation')
        release=self.release
        if not release or version(release['tag_name'])<=version(self.installed):raise UpdateError('update_no_release')
        channel=self.preferences['channel']
        def work():
            expected,assets=release_assets(release);name=NAME+'-v'+expected+'.zip'
            wanted=checksum(self.github.fetch(assets['SHA256SUMS']['url'],65536,True),name)
            reported=assets[name].get('digest')
            if reported and reported!='sha256:'+wanted:raise UpdateError('update_checksum')
            staging=self.root/'staged';staging.mkdir(exist_ok=True,mode=0o700)
            if shutil.disk_usage(staging).free<assets[name]['size']+MAX_EXPANDED+32*1024*1024:raise UpdateError('update_storage')
            archive=staging/(uuid4().hex+'.zip');digest=hashlib.sha256();count=0;started=time.monotonic()
            try:
                with self.github.open(self.github.request(assets[name]['url'],True),timeout=10) as response,archive.open('xb') as out:
                    while True:
                        self.checkpoint()
                        if time.monotonic()-started>120:raise UpdateError('update_timeout')
                        block=response.read(65536)
                        if not block:break
                        count+=len(block)
                        if count>assets[name]['size'] or count>MAX_ARCHIVE:raise UpdateError('update_archive_size')
                        digest.update(block);out.write(block);self.percent=round(count*90/assets[name]['size'])
                if count!=assets[name]['size'] or digest.hexdigest()!=wanted:raise UpdateError('update_checksum')
                self.checkpoint();self.staged=stage_archive(archive,staging,expected)
                self.checkpoint()
                with self.lock:
                    if channel!=self.preferences['channel']:raise UpdateError('update_cancelled')
                    self.confirmation=uuid4().hex;self.percent=100;self.phase='ready'
                # Keep one prior rollback plus the two most recent generated
                # staging trees. Never remove foreign entries or live targets.
                prior=read_json(self.root/'result.json').get('rollback','')
                folders=sorted((p for p in staging.iterdir() if p.is_dir() and not p.is_symlink() and re.fullmatch(r'validated-[A-Za-z0-9_-]+',p.name)),key=lambda p:p.stat().st_mtime,reverse=True)
                keep={self.staged.parent,*folders[:2]}
                if prior:
                    previous=Path(prior)
                    if previous.name==NAME and previous.parent.parent==staging:keep.add(previous.parent)
                for folder in folders:
                    if folder not in keep:
                        # Verify our own generated shape before recoverable
                        # cleanup of obsolete downloaded code (not user media).
                        entries=list(folder.iterdir())
                        if len(entries)==1 and entries[0].name==NAME and not entries[0].is_symlink():shutil.rmtree(folder)
            finally:archive.unlink(missing_ok=True)
        self.launch('downloading',work)
    def install(self,confirmation):
        with self.install_lock,self.lock:return self._install_verified(confirmation)
    def _install_verified(self,confirmation):
        if self.busy() or self.blocked():raise UpdateError('update_game_or_preparation')
        if self.phase!='ready' or not re.fullmatch(r'[a-f0-9]{32}',str(confirmation)) or confirmation!=self.confirmation:raise UpdateError('update_confirmation')
        target=self.release['tag_name'].removeprefix('v');verify_tree(self.staged,target)
        if self.plugin.name!=NAME or os.stat(self.plugin).st_dev!=os.stat(self.staged).st_dev:raise UpdateError('update_install_path')
        environment=clean_child_environment(os.environ);interpreter=system_python(environment);systemd=shutil.which('systemd-run')
        if not interpreter or not systemd or not os.path.isfile(interpreter) or os.uname().sysname!='Linux':raise UpdateError('update_helper_unavailable')
        helper=self.root/'update_helper.py';shutil.copyfile(Path(__file__).with_name('update_helper.py'),helper);helper.chmod(0o600)
        tx=dict(token=confirmation,from_version=self.installed,to_version=target,active=str(self.plugin),staged=str(self.staged),root=str(self.root),channel=self.preferences['channel'])
        save(self.root/'transaction.json',tx);save(self.root/'result.json',dict(phase='installing',error=''));self.phase='installing';self.confirmation=''
        try:subprocess.run([systemd,'--unit=das-update-'+confirmation[:12],'--collect','--no-block','--property=Type=exec','--property=TimeoutStartSec=180',
            interpreter,str(helper),str(self.root/'transaction.json')],env=environment,check=True,capture_output=True,timeout=10)
        except (OSError,subprocess.SubprocessError):
            self.phase='error';self.error='update_helper_launch';save(self.root/'result.json',dict(phase='error',error=self.error));raise UpdateError(self.error) from None
    def shutdown(self,timeout=2):
        deadline=time.monotonic()+max(0,timeout)
        self.closed.set();self.cancelled.set();self.reschedule.set()
        for thread in (self.scheduler,self.thread):
            if thread and thread is not threading.current_thread():thread.join(max(0,deadline-time.monotonic()))
