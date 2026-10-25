"""Explicit verified copy from the old GCA Studio; no key/export takeover."""
from __future__ import annotations
import copy
import fcntl
import hashlib
import os
from pathlib import Path,PurePosixPath
import shutil
import tempfile
import threading
from uuid import uuid4
from das.core.catalog import ScreensaverError
from .storage import read_object,validate

def _source(root,relative):
    if not isinstance(relative,str) or '\\' in relative:raise ScreensaverError('Invalid import path','unsafe_path')
    part=PurePosixPath(relative)
    if part.is_absolute() or str(part)!=relative or '..' in part.parts or len(part.parts)>5:
        raise ScreensaverError('Invalid import path','unsafe_path')
    path=root.joinpath(*part.parts)
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():raise ScreensaverError('Import media missing','missing_media')
    return path

def start(service,root):
    root=Path(root).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):raise ScreensaverError('Import links preserved','unsafe_path')
    if service._busy() or service._playing():raise ScreensaverError('Stop other preparation first','busy')
    metadata=read_object(root/'studio.json')
    if not metadata or metadata.get('schema')!=1 or not isinstance(metadata.get('games'),dict):
        raise ScreensaverError('No reusable GCA Studio library found','import_missing')
    if len(metadata['games'])>2000:raise ScreensaverError('Import exceeds library limit','storage_limit')
    # Source lock must exist from the previous preparation. Never create files in
    # another plugin's data or run two old/new heavy pipelines concurrently.
    lock=root/'prepare.lock'
    if lock.is_symlink() or not lock.is_file():raise ScreensaverError('Old library is not ready for import','import_unavailable')
    service.cancelled.clear();service._save_job(state='running',stage='importing',completed=0,total=len(metadata['games']),percent=0,queue=[],error='')
    service.thread=threading.Thread(target=_run,args=(service,root,metadata),name='studio-verified-import',daemon=True)
    service.thread.start()

def _run(service,root,metadata):
    stage=None;destination=None;committed=False;descriptor=None
    try:
        descriptor=os.open(root/'prepare.lock',os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:raise ScreensaverError('Old Studio is preparing','worker_busy') from error
        with service.lease():
            imports=service.catalog.managed('imported');imports.mkdir(exist_ok=True,mode=0o700)
            stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=imports));name=uuid4().hex;rows=[];used=0
            available=service._storage_available()
            for n,entry in enumerate(metadata['games'].values()):
                service.checkpoint()
                if not isinstance(entry,dict) or type(entry.get('appid')) is not int or not 0<abs(entry['appid'])<=0xffffffff:
                    raise ScreensaverError('Invalid old library','invalid_catalog')
                if not isinstance(entry.get('name',''),str) or len(entry.get('name',''))>200:
                    raise ScreensaverError('Invalid old game name','invalid_catalog')
                if service.catalog.get(entry['appid']):continue # Existing DAS choices win.
                row={k:copy.deepcopy(entry[k]) for k in ('appid','name','installed','excluded','animated','width','height','duration','format','crop','branding','cover_position','original_preserved') if k in entry}
                if isinstance(row.get('branding'),dict) and row['branding'].get('position')=='beside-title':row['branding']['position']='inherit'
                row.update(status='pending',media={},sha256={},imported_from_gca=True)
                if entry.get('status')=='ready' and not entry.get('pending_change'):
                    media=entry.get('media',{});expected=entry.get('sha256',{})
                    if not isinstance(media,dict) or not isinstance(expected,dict):raise ScreensaverError('Invalid import metadata','invalid_catalog')
                    for role in ('tv','thumbnail','cover','logo','panel_source'):
                        if not media.get(role):
                            if role in ('tv','thumbnail'):raise ScreensaverError('Missing prepared import','missing_media')
                            continue
                        path=_source(root,media[role]);size=path.stat().st_size
                        if not 0<size<=1024**3 or used+size>available:raise ScreensaverError('Import exceeds storage','storage_limit')
                        if role in ('tv','thumbnail') and (not isinstance(expected.get(role),str) or len(expected[role])!=64):
                            raise ScreensaverError('Import needs verified media receipts','import_unverified')
                        leaf=f'{n:04d}-{role}{path.suffix.lower()}'
                        if path.suffix.lower() not in {'.gif','.webp','.webm','.jpg','.jpeg','.png'}:raise ScreensaverError('Unsupported import media','invalid_media')
                        digest=hashlib.sha256();count=0
                        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
                        with os.fdopen(fd,'rb') as source,(stage/leaf).open('xb') as target:
                            while True:
                                service.checkpoint();block=source.read(1024*1024)
                                if not block:break
                                count+=len(block)
                                if count>size:raise ScreensaverError('Import source changed','import_unverified')
                                digest.update(block);target.write(block)
                        value=digest.hexdigest()
                        if count!=size or expected.get(role) and value!=expected[role]:raise ScreensaverError('Import checksum mismatch','import_unverified')
                        row['media'][role]=f'imported/{name}/{leaf}';row['sha256'][role]=value;used+=size
                    row['status']='ready'
                rows.append(row)
                service._save_job(completed=n+1,percent=round((n+1)*100/max(1,len(metadata['games']))))
            service.checkpoint();destination=imports/name;stage.rename(destination);stage=None
            with service.catalog.lock:
                before=copy.deepcopy(service.catalog.data)
                try:
                    empty=not service.catalog.data['games']
                    for row in rows:service.catalog.data['games'].setdefault(str(row['appid']),row)
                    if empty:
                        for key,value in metadata.get('options',{}).items():
                            try:service.catalog.data['options'].update(validate({key:value}))
                            except ScreensaverError:pass
                        own=service.catalog.data.get('jsaux',{})
                        if own.get('enabled') and own.get('mode')=='sync':service.catalog.data['options']['shuffle']=False
                    service.catalog.save();committed=True
                except BaseException:service.catalog.data=before;raise
            service._ready={g['appid'] for g in service.catalog.games() if service.catalog.ready(g)}
            service._measure_usage();service._save_job(state='complete',stage='complete',completed=len(metadata['games']),percent=100,current_percent=100)
    except Exception as error:
        if not service.cancelled.is_set() and not service.closed:
            service._save_job(state='paused',stage='interrupted',error=getattr(error,'code','import_failed'))
    finally:
        if descriptor is not None:os.close(descriptor)
        if stage is not None:shutil.rmtree(stage)
        if destination is not None and not committed:shutil.rmtree(destination)
