"""Transactional Studio snapshot. Old exports are never silently replaced."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import re
import shutil
import stat
import tempfile
from das.core.catalog import ScreensaverError, atomic_json, file_sha256
from das.core.installer import ScreensaverInstaller
from .storage import read_object
from .presentation import ready_games,manifest

FOLDER='decky-animated-screensaver'
MARKER='.decky-animated-screensaver.json'
OWNER='decky-animated-screensaver-studio-v1'
SELECTION_CONTRACT=1
FILES=('index.html','player.js','player.css','diagnostic.js','diagnostic-config.js')

def player_catalog(store,resolve=lambda path:path):
    options=store.options(); games=[]
    selected=ready_games(store)
    for g in selected:
        m=g['media']; source=m['tv']
        # A still always exports its validated original. Old still-motion and
        # smoothing derivatives may remain on disk, but must never replace it.
        if g.get('animated') and options['smoothing'] and g.get('smoothing_config')==[options['smoothing_mode'],options['smoothing_fps']] and m.get('smoothed'):
            source=m['smoothed']
        author=dict(name=g.get('credits',{}).get('author','SteamGridDB'))
        entry=dict(id=('steam:' if g['appid']>0 else 'sgdb:')+str(abs(g['appid'])),steamAppId=g['appid'] if g['appid']>0 else None,
            name=g.get('name',''),included=True,status='ready',crop=g.get('crop'),explicitStill=g.get('still_mode') in {'motion','fixed'},
            media=dict(file=resolve(source),thumbnail=resolve(m['thumbnail']),format=Path(source).suffix[1:],animated=bool(g.get('animated')),
                width=g.get('width'),
                height=g.get('height'),
                duration=g.get('duration'),author=author))
        if not g.get('animated'):
            entry['stillMotion']='fixed' if options['reduced_motion'] or g.get('still_mode')=='fixed' else 'gentle'
        if m.get('cover'):
            entry['cover']=dict(file=resolve(m['cover']),animated=False,author=dict(name=g.get('cover_credits',{}).get('author','SteamGridDB')))
        if m.get('logo'): entry['logo']=resolve(m['logo'])
        if m.get('logo'):
            entry['logo']=dict(file=resolve(m['logo']),animated=False,author=dict(name=g.get('logo_credits',{}).get('author','SteamGridDB')))
        entry['branding']=g.get('branding')
        entry['coverPosition']=g.get('cover_position',options['cover_position'])
        games.append(entry)
    return dict(version=1,games=games,presentation=manifest(selected,options),settings=dict(sceneDuration=options['scene_seconds'],shuffle=options['shuffle'],
        transition=options['transition'],showLogos=options['show_title'],showCover=options['show_cover'],
        showActualLogos=options['show_logo'],coverPosition=options['cover_position'],framing=options['framing'],
        reducedMotion=options['reduced_motion'],staticFallback=options['static_fallback'],
        nameDisplay=options['name_display'] if options['show_logo'] else ('title' if options['show_title'] else 'hidden'),
        logoPosition=options['logo_position'],showArtworkCredit=options['artwork_credit'],
        showCoverCredit=options['cover_credit'],showLogoCredit=options['logo_credit']))


def catalog_script(value):
    text=json.dumps(value,ensure_ascii=True,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    return ('window.SAS_CATALOG='+text+';\n').encode()

class Installer:
    def __init__(self,store,steam_root,assets):
        self.store=store; self.assets=Path(assets).resolve()
        # Reuse only the audited path/copy primitives, never the old installer transaction.
        self.boundary=ScreensaverInstaller(store.root,steam_root,assets)
        self.destination=self.boundary.destination.with_name(FOLDER)
        self.expected={name:file_sha256(self.assets/name) for name in FILES}
        self.html=(self.assets/'index.html').read_bytes()
        self.token=''; self.cached=dict(installed=False,needs_repair=False,name=FOLDER,revision='studio-1')
        self.jsaux_export=None;self.installed_ids=frozenset()
        self.delegation=None

    def player_html(self,jsaux=None):
        if jsaux is not None and not isinstance(jsaux,dict):raise ScreensaverError('Invalid export descriptor','installation_conflict')
        relay=(jsaux or {}).get('relay',{})
        if not relay:return self.html
        if not isinstance(relay,dict):raise ScreensaverError('Invalid relay descriptor','installation_conflict')
        url=relay.get('url')
        match=re.fullmatch(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/jsaux/v1/player',url) if isinstance(url,str) else None
        if relay.get('kind')!='http-loopback-v1' or not match or int(match[1])>65535:
            raise ScreensaverError('Unsafe local player relay','installation_conflict')
        marker=b"connect-src 'none';"
        if self.html.count(marker)!=1:raise ScreensaverError('Missing player security policy','installation_conflict')
        debug_url=url.replace('/jsaux/v1/player','/jsaux/v1/diagnostic')
        html=self.html.replace(marker,b'connect-src '+url.encode('ascii')+b' '+debug_url.encode('ascii')+b';',1)
        # A cached old script must not silently masquerade as this debug build.
        revision=self.expected['player.js'][:12]
        for name in ('diagnostic.js','diagnostic-config.js','catalog.js','player.js'):
            html=html.replace(('src="'+name+'"').encode(),('src="'+name+'?v='+revision+'"').encode())
        return html

    def player_hashes(self,jsaux=None):
        return {**self.expected,'index.html':hashlib.sha256(self.player_html(jsaux)).hexdigest(),
            'diagnostic-config.js':hashlib.sha256(self.diagnostic_config(jsaux)).hexdigest()}

    def diagnostic_config(self,jsaux=None):
        if not jsaux or not jsaux.get('relay'):return (self.assets/'diagnostic-config.js').read_bytes()
        self.player_html(jsaux) # Validate the exact loopback descriptor first.
        if (not isinstance(jsaux.get('collection_id'),str) or not re.fullmatch('[a-f0-9]{64}',jsaux['collection_id'])
            or not isinstance(self.token,str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',self.token)):
            raise ScreensaverError('Invalid player bootstrap metadata','installation_conflict')
        config=dict(enabled=jsaux.get('controller')!='GabeCubeAura',token=self.token,relay=jsaux['relay'],build=self.expected['player.js'][:12],revision=19,
            collection_id=jsaux['collection_id'])
        text=json.dumps(config,ensure_ascii=True,separators=(',',':')).replace('<','\\u003c')
        return ('window.DAS_PLAYER_BOOT='+text+';window.DAS_PLAYER_DEBUG?.configure(window.DAS_PLAYER_BOOT);\n').encode()

    def _owned(self):
        if self.destination.is_symlink(): raise ScreensaverError('Foreign destination preserved','installation_conflict')
        if not self.destination.exists(): return None
        if self.destination.is_symlink() or not self.destination.is_dir(): raise ScreensaverError('Foreign destination preserved','installation_conflict')
        data=read_object(self.destination/MARKER,512*1024)
        if not data or data.get('owner')!=OWNER or not isinstance(data.get('files'),dict): raise ScreensaverError('Foreign destination preserved','installation_conflict')
        allowed=set(data['files'])|{MARKER}
        for leaf in self.destination.rglob('*'):
            relative=leaf.relative_to(self.destination).as_posix()
            if leaf.is_symlink() or leaf.is_file() and relative not in allowed or leaf.is_dir() and relative!='media':
                raise ScreensaverError('Unowned export files preserved','installation_conflict')
        return data

    def status(self,refresh=False,verify=False):
        if not refresh:
            value=dict(self.cached)
            value['needs_update']=bool(value.get('installed') and (value.get('catalog_revision')!=self.store.revision or value.get('selection_contract')!=SELECTION_CONTRACT))
            return value
        try:
            self.installed_ids=frozenset()
            self.boundary._safe_parent()
            owned=self._owned()
            if owned:
                self.token=owned.get('bridge_token','')
                self.jsaux_export=owned.get('jsaux')
                expected=self.player_hashes(self.jsaux_export)
                different=owned.get('player_sha256')!=expected
                try:
                    if not different: different=any(file_sha256(self.destination/name)!=digest for name,digest in expected.items())
                    if not (self.destination/'catalog.js').is_file(): different=True
                    if not (self.destination/'diagnostic-config.js').is_file():different=True
                    path=self.destination/'catalog.js';record=owned['files'].get('catalog.js',{})
                    if not path.is_file() or not 0<path.stat().st_size<=4*1024*1024:raise ValueError('Invalid installed catalog')
                    raw=path.read_bytes()
                    if not isinstance(record,dict) or len(raw)!=record.get('size') or hashlib.sha256(raw).hexdigest()!=record.get('sha256'):raise ValueError('Invalid installed catalog')
                    text=raw.decode('utf8')
                    if not text.startswith('window.SAS_CATALOG=') or not text.endswith(';\n'):raise ValueError('Invalid installed catalog')
                    catalog=json.loads(text[len('window.SAS_CATALOG='):-2])
                    if not isinstance(catalog,dict):raise ValueError('Invalid installed catalog')
                    games=catalog.get('games',[])
                    if not isinstance(games,list) or not 0<len(games)<=5000:raise ValueError('Invalid installed catalog')
                    identities=[g.get('id') for g in games if isinstance(g,dict)]
                    if len(identities)!=len(games) or any(not isinstance(i,str) or not re.fullmatch(r'(?:steam|sgdb):[1-9][0-9]{0,9}',i) for i in identities) or len(set(identities))!=len(identities):raise ValueError('Invalid installed identities')
                    self.installed_ids=frozenset(identities)
                    if verify:
                        for name,record in owned['files'].items():
                            relative=PurePosixPath(name)
                            if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                                or not name or relative.as_posix()!=name or len(relative.parts)>2
                                or not isinstance(record,dict) or not isinstance(record.get('sha256'),str)):
                                raise ScreensaverError('Unsafe installation receipt','installation_conflict')
                            leaf=self.destination/name
                            if leaf.stat().st_size!=record.get('size') or file_sha256(leaf)!=record['sha256']: different=True
                except (OSError,ValueError,TypeError):
                    different=True
                self.cached=dict(installed=True,needs_repair=different,name=FOLDER,revision=owned.get('revision','unknown'),
                    scene_count=owned.get('scene_count',0),player_current=not different,catalog_revision=owned.get('catalog_revision'),selection_contract=owned.get('selection_contract'))
            else:
                self.token='';self.jsaux_export=None
                self.cached=dict(installed=False,needs_repair=False,name=FOLDER,revision='studio-1')
        except (OSError,ValueError,ScreensaverError):
            self.token='';self.jsaux_export=None
            self.cached=dict(installed=False,needs_repair=True,name=FOLDER,error='installation_conflict')
        return self.status()

    def contains(self,number):
        return ('steam:' if number>0 else 'sgdb:')+str(abs(number)) in self.installed_ids

    def install(self,language='en'):
        if self.delegation:
            blocker=self.delegation.installation_blocker()
            if blocker:
                self.delegation.installation_event('installation-blocked')
                raise ScreensaverError('Finish the requested faceplate preparation before updating Steam',blocker)
            self.delegation.installation_event('installation-started')
        parent=self.boundary._safe_parent(create=True)
        # flock is released by the OS after a crash; no stale lock-directory trap.
        import fcntl
        fd=os.open(parent/'.decky-animated-screensaver.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e: raise ScreensaverError('Another installation is active','worker_busy') from e
            old=self._owned();saved_token=(old or {}).get('bridge_token')
            self.token=saved_token if isinstance(saved_token,str) and re.fullmatch('[A-Za-z0-9_-]{1,80}',saved_token) else secrets.token_hex(24)
            sources={}; total=0
            export_revision=self.store.revision
            def resolve(relative):
                nonlocal total
                source=self.store.managed(relative,True)
                if relative not in sources:
                    size=source.stat().st_size
                    if not 0<size<=1024**3: raise ScreensaverError('Media exceeds export budget','invalid_media')
                    sources[relative]=(source,f'media/{len(sources):04d}{source.suffix}'); total+=size
                return sources[relative][1]
            catalog=player_catalog(self.store,resolve)
            if not catalog['games']: raise ScreensaverError('Prepare at least one animation','not_ready')
            quota=self.store.options()['storage_mib']*1024**2
            if (quota and total>quota) or shutil.disk_usage(parent).free<total+64*1024**2:
                raise ScreensaverError('Not enough export storage','storage_limit')
            catalog['bridge_token']=self.token; catalog['revision']='studio-1'
            jsaux=self.delegation.export() if self.delegation else None
            published=False
            old_player=(old or {}).get('jsaux') or {}
            stage=None;backup=None;committed=False
            try:
                if jsaux:
                    # Fresh token keeps the previous installed export valid if staging fails.
                    self.token=secrets.token_hex(24);catalog['bridge_token']=self.token
                    jsaux=self.delegation.publish_installed_player(jsaux,self.token) if callable(getattr(self.delegation,'publish_installed_player',None)) else jsaux
                    published=jsaux.get('controller')=='GabeCubeAura'
                    if not published and self.delegation.player_relay:
                        self.delegation.player_relay.start()
                        jsaux=self.delegation.export()
                    catalog['jsaux']=jsaux
                    if jsaux['mode']=='sync':catalog['settings']['shuffle']=False
                catalog['settings']['language']='fr' if language=='fr' else 'en'
                stage=Path(tempfile.mkdtemp(prefix='.studio-stage-',dir=parent))
                (stage/'media').mkdir()
                for name in FILES: ScreensaverInstaller._copy(self.assets/name,stage/name)
                if jsaux and jsaux.get('relay'):(stage/'index.html').write_bytes(self.player_html(jsaux))
                ScreensaverInstaller._copy(self.assets.parents[1]/'licenses/GabeCubeAura-BSD-3-Clause.txt',stage/'LICENSE.txt')
                ScreensaverInstaller._copy(self.assets.parents[1]/'licenses/Steam-Animated-Screensaver-GPL-3.0.txt',stage/'PLAYER-LICENSE-GPL-3.0.txt')
                for source,name in sources.values(): ScreensaverInstaller._copy(source,stage/name,source.stat())
                (stage/'catalog.js').write_bytes(catalog_script(catalog))
                if jsaux and jsaux.get('relay'):
                    (stage/'diagnostic-config.js').write_bytes(self.diagnostic_config(jsaux))
                records={p.relative_to(stage).as_posix():dict(size=p.stat().st_size,sha256=file_sha256(p)) for p in stage.rglob('*') if p.is_file()}
                atomic_json(stage/MARKER,dict(owner=OWNER,revision='studio-1',player_sha256=self.player_hashes(jsaux),catalog_revision=export_revision,
                    bridge_token=self.token,jsaux=jsaux,scene_count=len(catalog['games']),selection_contract=SELECTION_CONTRACT,files=records))
                for p in stage.rglob('*'): p.chmod(0o755 if p.is_dir() else 0o644)
                stage.chmod(0o755)
                if old:
                    backup=parent/('.studio-backup-'+secrets.token_hex(8)); self.destination.rename(backup)
                try: stage.rename(self.destination)
                except BaseException:
                    if backup: backup.rename(self.destination); backup=None
                    raise
                committed=True
                if backup:
                    try:shutil.rmtree(backup)
                    except OSError:self.cleanup_deferred=True
                if old_player.get('controller')=='GabeCubeAura' and saved_token!=self.token:
                    try:self.delegation.remove_installed_player(saved_token)
                    except Exception:pass # Retaining an old binding cannot invalidate the committed export.
            except BaseException:
                if not committed and jsaux:
                    try:self.delegation.remove_installed_player(self.token)
                    except Exception:pass
                if not committed:self.token=saved_token or ''
                raise
            finally:
                if stage is not None and stage.exists(): shutil.rmtree(stage)
        finally: os.close(fd)
        result=self.status(True)
        if self.delegation and self.delegation.player_relay and not self.jsaux_export:self.delegation.player_relay.close()
        if self.delegation:self.delegation.installation_event('installation-completed')
        return result

    def uninstall(self,metadata=None):
        parent=self.boundary._safe_parent()
        if not parent.exists():
            if metadata:metadata()
            self.token='';return self.status(True)
        import fcntl
        fd=os.open(parent/'.decky-animated-screensaver.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e: raise ScreensaverError('Another installation is active','worker_busy') from e
            old=self._owned()
            rollback=metadata() if metadata else None
            if old:
                # Detach the owned directory in one operation. Failed renames
                # preserve the complete installed export and restore metadata.
                removed=parent/('.studio-removed-'+secrets.token_hex(8))
                try:self.destination.rename(removed)
                except BaseException:
                    if rollback:rollback()
                    raise
                if (old.get('jsaux') or {}).get('controller')=='GabeCubeAura':
                    try:self.delegation.remove_installed_player(old.get('bridge_token'))
                    except Exception:pass # Removing Steam files remains possible while GCA is offline.
                try:shutil.rmtree(removed)
                except OSError:self.cleanup_deferred=True
        finally: os.close(fd)
        self.token=''; return self.status(True)
