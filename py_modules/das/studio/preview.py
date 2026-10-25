"""On-demand same-player preview, bounded transport, no video bytes in Decky RPC."""
from pathlib import Path
import copy
import secrets
import threading
import base64
import hashlib
import os
import tempfile
import json
import re
import shutil
import errno
from urllib.parse import urlsplit
from das.core.preview import PreviewMedia
from das.core.catalog import ScreensaverError
from das.provider import SteamGridDBError
from .installer import player_catalog, catalog_script, FILES

class Preview:
    def __init__(self,store,assets,service=None):
        self.store=store; self.assets=Path(assets); self.code=store.managed('preview-code')
        self.service=service;self.generation=0;self.lock=threading.Lock();self.lifecycle=threading.RLock();self.request_id=None;self.nonce=None;self.inspected={};self.cancelled_ids={};self.snapshot=None
        self.transport=PreviewMedia(store.root,code_root=self.code,maximum_files=50006,idle_seconds=600,maximum_media_bytes=None)

    def candidate(self,number,role,asset_id,motion=False,request_id=None):
        """Resolve server-known candidates only; RPC never accepts a media URL."""
        if request_id in self.cancelled_ids:raise ScreensaverError('Preview cancelled','preview_cancelled')
        if not self.lock.acquire(False):raise ScreensaverError('Preview is loading','busy')
        try:
            if motion:
                self.close();self.request_id=request_id
            ticket=self.generation
            def check():
                if ticket!=self.generation or request_id in self.cancelled_ids:raise ScreensaverError('Preview cancelled','preview_cancelled')
                if self.service._busy() or self.service._playing():raise ScreensaverError('Wait for preparation or game','busy')
            check()
            rows=self.service._candidates.get((number,role),[])
            asset=next((a for a in rows if a['id']==asset_id),None)
            if not asset:raise ScreensaverError('Refresh the candidate list','invalid_asset')
            identity=hashlib.sha256(('gallery-v1:'+asset['url']+'|'+asset.get('thumb','')).encode()).hexdigest()
            root=self.store.managed('candidate-previews-v1');root.mkdir(exist_ok=True,mode=0o700)
            suffixes=('webp','webm') if motion else ('jpg',)
            for ext in suffixes:
                path=self.store.managed(f'candidate-previews-v1/{identity}.{ext}')
                if path.is_file() and 0<path.stat().st_size<=(8*1024*1024 if motion else 96*1024):
                    check();os.utime(path,None)
                    return self._candidate_result(path,motion)
            if (asset.get('width') or 0)*(asset.get('height') or 0)>3840*2160:raise ScreensaverError('Image too large','source_limit')
            from .candidate_media import render
            sources=[]
            # Fetch thumbnails through the backend's verified TLS path, not the
            # Steam frontend. Legacy S3 thumbnail hosts remain narrowly allowed.
            if asset.get('thumb'):
                sources.append((dict(url=asset['thumb']),True,8*1024*1024,20))
            sources.append((asset,False,128*1024*1024,90))
            failure=None
            for source_asset,is_thumb,maximum,seconds in sources:
                try:
                    source=self.service._download(source_asset,checkpoint=check,maximum=maximum,seconds=seconds,thumbnail=is_thumb)
                    check();self.service._admit(10*1024*1024)
                    with tempfile.TemporaryDirectory(prefix='.gallery-',dir=root) as temporary:
                        with self.service.lease():path=render(self.service.compiler,source,Path(temporary),check,motion)
                        check();target=root/(identity+path.suffix);os.replace(path,target)
                    self._prune_candidates(root,target)
                    return self._candidate_result(target,motion)
                except (ScreensaverError,SteamGridDBError,OSError) as error:
                    check();failure=error
                    if getattr(error,'code','') in {'busy','worker_busy','storage_limit','ffmpeg_missing','ffprobe_missing'}:raise
            raise failure or ScreensaverError('Preview unavailable','download_failed')
        finally:self._release()

    def _candidate_result(self,path,motion):
        if motion:return dict(source_url=self.transport.url(path),source_format=path.suffix[1:],derivative=True)
        return dict(still='data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode(),derivative=True)

    def _drop_snapshot(self):
        previous=self.snapshot;self.snapshot=None
        if previous:
            try:previous.cleanup()
            except OSError:pass

    def _release(self):
        # Serialize release with close: a cancellation after the final check
        # must not leave a private snapshot behind in the tiny return window.
        with self.lifecycle:
            if self.nonce is None:self._drop_snapshot()
            self.lock.release()

    def installed(self,installer,number=None,request_id=None):
        """Preview verified installed bytes, never the mutable working catalog.

        Private hardlinks retain the old export across an atomic replacement.
        Cross-filesystem copies are bounded and cancellation-aware. The generated
        preview catalog drops all delegation credentials and carries previewNonce.
        """
        if request_id in self.cancelled_ids:raise ScreensaverError('Preview cancelled','preview_cancelled')
        if not self.lock.acquire(False):raise ScreensaverError('Preview is loading','busy')
        export_fd=None
        try:
            self.close();self._drop_snapshot();ticket=self.generation;self.request_id=request_id
            def check():
                if ticket!=self.generation or request_id in self.cancelled_ids:raise ScreensaverError('Preview cancelled','preview_cancelled')
            parent=installer.boundary._safe_parent()
            if not installer.destination.exists():raise ScreensaverError('No installed collection','not_ready')
            import fcntl
            export_fd=os.open(parent/'.decky-animated-screensaver.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
            try:fcntl.flock(export_fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError:raise ScreensaverError('Steam files are being updated','busy') from None
            owned=installer._owned()
            if not owned:raise ScreensaverError('No installed collection','not_ready')
            records=owned['files'];total=0
            def read(name,maximum):
                check();record=records.get(name);path=installer.destination/name
                if not isinstance(record,dict) or path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=maximum:raise ScreensaverError('Invalid installed snapshot','installation_conflict')
                raw=path.read_bytes()
                if len(raw)!=record.get('size') or hashlib.sha256(raw).hexdigest()!=record.get('sha256'):raise ScreensaverError('Installed files need repair','installation_conflict')
                return raw
            raw=read('catalog.js',4*1024*1024).decode('utf8')
            if not raw.startswith('window.SAS_CATALOG=') or not raw.endswith(';\n'):raise ScreensaverError('Invalid installed catalog','installation_conflict')
            catalog=json.loads(raw[len('window.SAS_CATALOG='):-2])
            if not isinstance(catalog,dict) or not isinstance(catalog.get('games'),list) or not 0<len(catalog['games'])<=5000:raise ScreensaverError('Invalid installed catalog','installation_conflict')
            if number is not None:
                identity=('steam:' if number>0 else 'sgdb:')+str(abs(number))
                catalog['games']=[g for g in catalog['games'] if isinstance(g,dict) and g.get('id')==identity]
                if not catalog['games']:raise ScreensaverError('Game is not in the installed collection','not_ready')
            root=self.store.managed('preview-snapshots');root.mkdir(exist_ok=True,mode=0o700)
            self.snapshot=tempfile.TemporaryDirectory(prefix='installed-',dir=root);snapshot=Path(self.snapshot.name);mapped={}
            def resolve(name):
                nonlocal total
                if not isinstance(name,str) or not re.fullmatch(r'media/[0-9]{4,5}\.(?:webm|mp4|gif|png|jpg|jpeg|webp)',name):raise ScreensaverError('Unsafe installed media','installation_conflict')
                if name in mapped:return mapped[name]
                check();record=records.get(name);source=installer.destination/name
                if (not isinstance(record,dict) or source.is_symlink() or source.parent.is_symlink() or not source.is_file()
                    or not 0<source.stat().st_size or source.stat().st_size!=record.get('size')):raise ScreensaverError('Installed media needs repair','installation_conflict')
                total+=source.stat().st_size
                if self.store.options()['storage_mib'] and total>self.store.options()['storage_mib']*1024**2:raise ScreensaverError('Preview exceeds snapshot budget','source_limit')
                target=snapshot/source.name
                try:os.link(source,target,follow_symlinks=False)
                except OSError as error:
                    if error.errno!=errno.EXDEV:raise
                    if shutil.disk_usage(snapshot).free<source.stat().st_size+64*1024*1024:raise ScreensaverError('Not enough preview storage','storage_limit')
                    with source.open('rb') as src,target.open('xb') as dst:
                        while block:=src.read(65536):check();dst.write(block)
                digest=hashlib.sha256()
                with target.open('rb') as src:
                    while block:=src.read(65536):check();digest.update(block)
                if target.stat().st_size!=record['size'] or digest.hexdigest()!=record.get('sha256'):raise ScreensaverError('Installed media needs repair','installation_conflict')
                mapped[name]=urlsplit(self.transport.url(target)).path;return mapped[name]
            for game in catalog['games']:
                if not isinstance(game,dict) or not isinstance(game.get('media'),dict) or not game['media'].get('file') or not game['media'].get('thumbnail'):raise ScreensaverError('Invalid installed game','installation_conflict')
                for key in ('file','thumbnail'):
                    if game['media'].get(key):game['media'][key]=resolve(game['media'][key])
                for key in ('cover','logo'):
                    if isinstance(game.get(key),dict):game[key]['file']=resolve(game[key].get('file'))
                    elif game.get(key):game[key]=resolve(game[key])
            catalog.pop('jsaux',None);catalog.pop('bridge_token',None)
            nonce=secrets.token_hex(24);self.nonce=nonce;catalog['previewNonce']=nonce
            self.code.mkdir(exist_ok=True,mode=0o700);urls={}
            for name in FILES:
                data=(self.assets/name).read_bytes() if name=='diagnostic-config.js' else read(name,512*1024)
                (self.code/name).write_bytes(data);urls[name]=self.transport.url(self.code/name)
            (self.code/'catalog.js').write_bytes(catalog_script(catalog));urls['catalog.js']=self.transport.url(self.code/'catalog.js')
            html=(self.code/'index.html').read_text()
            html=re.sub(r"connect-src [^;]+;","connect-src 'none';",html)
            for name in ('player.css','player.js','catalog.js','diagnostic.js','diagnostic-config.js'):
                html=re.sub(r'"'+re.escape(name)+r'(?:\?[^"<>]*)?"','"'+urlsplit(urls[name]).path+'"',html)
            (self.code/'index.html').write_text(html);check()
            return dict(url=urls['index.html'],nonce=nonce,count=len(catalog['games']),revision='installed-snapshot-v1',installed=True)
        except BaseException:
            self.close();self._drop_snapshot();raise
        finally:
            if export_fd is not None:os.close(export_fd)
            self._release()

    @staticmethod
    def _prune_candidates(root,keep):
        files=sorted((p for p in root.iterdir() if p.is_file() and not p.is_symlink() and p.suffix in {'.jpg','.webm','.webp'}),key=lambda p:p.stat().st_mtime,reverse=True)
        total=0
        for index,path in enumerate(files):
            total+=path.stat().st_size
            if path!=keep and (index>=64 or total>64*1024*1024):path.unlink()

    def open(self,number=None,patch=None,request_id=None,artwork_only=False):
        if request_id is not None and request_id in self.cancelled_ids:raise ScreensaverError('Preview cancelled','preview_cancelled')
        # A close invalidates pending downloads too; a late reply cannot revive it.
        if not self.lock.acquire(blocking=False):raise ScreensaverError('Preview is loading','busy')
        try:return self._open(number,patch,request_id,artwork_only)
        except BaseException:
            self.close();raise
        finally:self._release()

    def _open(self,number,patch,request_id,artwork_only):
        self.close();self._drop_snapshot();ticket=self.generation
        if request_id is not None and request_id in self.cancelled_ids:raise ScreensaverError('Preview cancelled','preview_cancelled')
        self.request_id=request_id
        warnings=[]
        def check():
            if self.generation!=ticket:raise ScreensaverError('Preview cancelled','preview_cancelled')
        store=self.store
        if number is not None:
            original=self.store.get(number)
            game=copy.deepcopy(original)
            if patch is not None:
                game.update(copy.deepcopy(patch));media=game.setdefault('media',{})
                source_changed='asset' in patch or game.get('pending_change') or not media.get('tv')
                if source_changed:
                    asset=game.get('asset')
                    if not asset:
                        rows=self.service._candidates.get((number,'animation'))
                        if rows is None:rows=self.service._assets(number,'animation')
                        if not rows and self.store.options()['static_fallback']:rows=self.service._assets(number,'still_tv')
                        asset=rows[0] if rows else None
                    if asset:
                        if (asset.get('width') or 0)*(asset.get('height') or 0)>3840*2160:raise ScreensaverError('Image exceeds preview budget','source_limit')
                        path=self.service._download(asset,checkpoint=check,maximum=32*1024*1024,seconds=30)
                    else:
                        path=self.service._local_artwork(number)
                        if not path:raise ScreensaverError('Choose an animation or a still image','animation_missing')
                    # Inspect in the existing bounded subprocess supervisor.
                    # No encoder or preparation job is started for the preview.
                    stamp=path.stat();key=(str(path),stamp.st_size,stamp.st_mtime_ns)
                    info=self.inspected.get(key)
                    if info is None:
                        with self.service.lease():info=self.service.compiler.inspect(path,check)
                        self.inspected[key]=info
                        while len(self.inspected)>32:self.inspected.pop(next(iter(self.inspected)))
                    game.update(animated=bool(info['animated']),width=info['width'],height=info['height'],duration=info.get('duration'))
                    check();media['tv']=str(path.relative_to(self.store.root));media['thumbnail']=media['tv']
                    media.pop('still_motion',None);media.pop('smoothed',None)
                for role in (() if artwork_only else ('cover','logo')):
                    asset=patch.get(role+'_asset')
                    if not asset and source_changed and not media.get(role) and self.store.options()['show_'+role]:
                        try:
                            rows=self.service._assets(number,role);asset=rows[0] if rows else None
                        except ScreensaverError:asset=None
                    if asset:
                        try:
                            path=self.service._download(asset,checkpoint=check,maximum=16*1024*1024,seconds=20)
                            from .media import signature
                            if signature(path) not in {'jpg','png','webp','gif'}:raise ScreensaverError('Invalid optional image','invalid_media')
                            check();media[role]=str(path.relative_to(self.store.root))
                        except (ScreensaverError,OSError) as error:
                            check()
                            warnings.append(dict(role=role,code=getattr(error,'code','download_failed')))
            if not game.get('media',{}).get('tv'):raise ScreensaverError('No prepared image yet','not_ready')
            game['media'].setdefault('thumbnail',game['media']['tv'])
            game.update(excluded=False,status='ready',pending_change=False,still_mode=game.get('still_mode','inherit'))
            # Same catalog builder and player as Steam. No draft/catalog/export mutation.
            class Single:
                def options(inner):return {**self.store.options(),'shuffle':False,'static_fallback':True}
                def games(inner):return [game]
                def ready(inner,g):return True
            store=Single()
        check();self.code.mkdir(exist_ok=True,mode=0o700)
        catalog=player_catalog(store,lambda relative:urlsplit(self.transport.url(self.store.managed(relative,True))).path)
        if number is not None:
            identity=('steam:' if int(number)>0 else 'sgdb:')+str(abs(int(number)))
            catalog['games']=[g for g in catalog['games'] if g['id']==identity]
        if not catalog['games']:
            self.close(); raise ScreensaverError('Prepare and include at least one animation first','not_ready')
        nonce=secrets.token_hex(24);self.nonce=nonce;catalog['previewNonce']=nonce
        urls={}
        for name in FILES:
            (self.code/name).write_bytes((self.assets/name).read_bytes())
            urls[name]=self.transport.url(self.code/name)
        (self.code/'catalog.js').write_bytes(catalog_script(catalog))
        urls['catalog.js']=self.transport.url(self.code/'catalog.js')
        html=(self.assets/'index.html').read_text()
        for name in ('player.css','player.js','catalog.js','diagnostic.js','diagnostic-config.js'): html=html.replace('"'+name+'"','"'+urlsplit(urls[name]).path+'"')
        (self.code/'index.html').write_text(html)
        check()
        result=dict(url=urls['index.html'],nonce=nonce,count=len(catalog['games']),revision='studio-2',warnings=warnings)
        if artwork_only and number is not None:
            result.update(source_url=self.transport.url(self.store.managed(game['media']['tv'],True)),source_format=Path(game['media']['tv']).suffix[1:],width=game.get('width'),height=game.get('height'))
        check()
        return result

    def quiesce(self,timeout=3):
        """Cancel inspection and wait for its codec lease before admitting a job."""
        self.close()
        if not self.lock.acquire(timeout=timeout):raise ScreensaverError('Preview is still stopping','busy')
        try:self._drop_snapshot()
        finally:self._release()

    def close(self, timeout=3,request_id=None,nonce=None):
        with self.lifecycle:self._close(timeout,request_id,nonce)

    def _close(self,timeout,request_id,nonce):
        if isinstance(request_id,str):
            self.cancelled_ids[request_id]=True
            while len(self.cancelled_ids)>128:self.cancelled_ids.pop(next(iter(self.cancelled_ids)))
        if request_id is not None and request_id!=self.request_id:return
        if nonce is not None and nonce!=self.nonce:return
        self.generation+=1
        self.request_id=None;self.nonce=None
        self.transport.close(timeout=timeout)
        if self.lock.acquire(False):
            try:self._drop_snapshot()
            finally:self._release()
