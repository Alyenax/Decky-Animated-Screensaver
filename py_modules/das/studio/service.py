"""One explicit sequential queue. Readiness never probes, scans or hashes media."""
from __future__ import annotations
import copy
from contextlib import contextmanager
import hashlib
import math
import re
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit
from urllib.request import Request
from uuid import uuid4
from das.core.catalog import ScreensaverError, atomic_json, file_sha256
from das.core.process_guard import failure_snapshot
from das.core.jobs import _safe_asset, rank_assets
from das.library import installed_games
from das.provider import API_BASE, HERO_DIMENSIONS, _trusted_url, _source_extension
from .membership import included as selected_game
from .storage import Store, component, crop, read_object
from .media import Media, still_motion_spec
from .problems import game_problem,skipped_media

class Interrupted(Exception): pass

IMAGE_FAILURES={'worker_signal','resource_limit','decode_failed','decode_timeout','invalid_media',
                'unsupported_source','unsupported_format','static_selection','invalid_webp','source_too_large','source_limit','visual_size_limit'}

CANDIDATE_FAILURES=IMAGE_FAILURES|{'download_failed','download_timeout','download_incomplete','animation_missing','artwork_missing'}
SELECTION_POLICY=64

def diagnostic_asset(value):
    """Public artwork identifiers only, including failed automatic candidates."""
    if not isinstance(value,dict):return {}
    result={}
    role=value.get('role')
    if isinstance(role,str) and role in {'background','cover','logo','smoothing','panel'}:result['role']=role
    number=value.get('id')
    if type(number) is int and 0<=number<=0xffffffff:result['id']=number
    for key in ('width','height'):
        number=value.get(key)
        if type(number) is int and 0<number<=16384:result[key]=number
    if type(value.get('animated')) is bool:result['animated']=value['animated']
    fmt=value.get('format')
    if not isinstance(fmt,str):fmt=''
    if not fmt and isinstance(value.get('url'),str):
        try:fmt=Path(urlsplit(value['url']).path).suffix[1:].lower()
        except ValueError:pass
    if fmt in {'png','jpg','jpeg','gif','webp','webm','mp4'}:result['format']=fmt
    return result

class CandidateCache(dict):
    """Small TTL/LRU selection snapshots; persisted choices live in Store."""
    def __init__(self):
        super().__init__();self.times={};self.guard=threading.RLock()
    def prune(self):
        with self.guard:
            now=time.time()
            for key,stamp in list(self.times.items()):
                if now-stamp>=300:self.pop(key,None)
    def __setitem__(self,key,value):
        with self.guard:
            self.prune();self.pop(key,None)
            super().__setitem__(key,copy.deepcopy(value));self.times[key]=time.time()
            while super().__len__()>24:self.pop(next(iter(self)))
    def pop(self,key,default=None):
        with self.guard:self.times.pop(key,None);return super().pop(key,default)
    def get(self,key,default=None):
        with self.guard:self.prune();return super().get(key,default)
    def __len__(self):
        with self.guard:self.prune();return super().__len__()
    def values(self):
        with self.guard:self.prune();return tuple(super().values())
    def clear(self):
        with self.guard:self.times.clear();super().clear()

class StudioService:
    def __init__(self,root,steamgriddb=None,current_game=None,games_provider=None,media=None,event_callback=None,legacy=None):
        self.catalog=Store(root,legacy); self.root=self.catalog.root; self.lock=threading.RLock()
        self.provider=steamgriddb; self.current_game=current_game or (lambda:{})
        self.games_provider=games_provider or installed_games; self.compiler=media or Media()
        self.event_callback=event_callback; self.thread=None; self.closed=False; self.cancelled=threading.Event()
        self._api_lock=threading.Lock(); self._api_at=0.; self._candidates=CandidateCache(); self._scanned=False
        self._pending_work=None; self.after_prepare=None; self.last_cleanup=None
        cached_usage=self.catalog.data.get('storage_bytes',0)
        self._usage=cached_usage if type(cached_usage) is int and cached_usage>=0 else 0
        self._ready=set(); self._key_configured=self._has_key(); self._connection='saved' if self._key_configured else 'missing'
        self.job=dict(state='idle',stage='idle',completed=0,total=0,current_percent=None,percent=0,error='',queue=[],history=[])
        try: previous=read_object(self.catalog.managed('job.json'))
        except (ValueError,ScreensaverError): previous=None
        if previous and self._valid_job(previous):
            self.job.update(previous)
            if self.job['state'] in {'running','paused_game'}: self.job.update(state='paused',stage='interrupted')
        # Metadata-only readiness. Explicit Verify validates hashes and actual files.
        self._ready={g['appid'] for g in self.catalog.games() if g.get('status')=='ready' and not g.get('pending_change') and g.get('media',{}).get('tv')}

    @staticmethod
    def _valid_job(value):
        return (value.get('state') in {'idle','running','paused','paused_game','cancelled','complete'}
            and isinstance(value.get('stage'),str) and len(value['stage'])<100
            and all(type(value.get(k)) is int and 0<=value[k]<=10000 for k in ('completed','total'))
            and value['completed']<=value['total']
            and isinstance(value.get('queue'),list) and len(value['queue'])<=10000
            and all(type(n) is int and 0<abs(n)<=0xffffffff for n in value['queue'])
            and isinstance(value.get('history'),list) and len(value['history'])<=100
            and all(isinstance(h,dict) and isinstance(h.get('stage'),str) and type(h.get('at')) is int
                and (h.get('percent') is None or type(h['percent']) is int and 0<=h['percent']<=100) for h in value['history']))

    def _has_key(self):
        try: return bool(self.provider and self.provider.status().get('configured'))
        except (OSError,ValueError): return False

    def refresh_key_state(self):
        self._key_configured=self._has_key()
        self._connection='saved' if self._key_configured else 'missing'

    def _event(self,kind,**fields):
        if self.event_callback:
            try: self.event_callback('studio_'+kind,**fields)
            except Exception: pass

    def _save_job(self,**patch):
        with self.lock:
            changed=patch.get('stage',self.job.get('stage'))!=self.job.get('stage') or bool(patch.get('error'))
            self.job.update(patch)
            if changed and 'history' not in patch:
                entry=dict(at=int(time.time()),stage=self.job['stage'],percent=self.job.get('current_percent'),
                    appid=self.job.get('appid',0),name=self.job.get('name',''),code=self.job.get('error',''))
                self.job['history']=(self.job.get('history',[])+[entry])[-100:]
            atomic_json(self.catalog.managed('job.json'),self.job)

    def progress(self,stage,value=None):
        if value is not None: value=max(0,min(100,round(float(value)*100)))
        with self.lock:
            if self.cancelled.is_set() or self.closed: return
            changed=stage!=self.job.get('stage')
            bucket=(value//10 if value is not None else None)
            previous=self.job.get('current_percent'); old=(previous//10 if previous is not None else None)
            self.job.update(stage=stage,current_percent=value)
            if changed or bucket!=old:
                entry=dict(at=int(time.time()),stage=stage,percent=value,appid=self.job.get('appid',0))
                self.job['history']=(self.job.get('history',[])+[entry])[-100:]
                self._save_job()
                self._event('phase',**entry)

    def _playing(self):
        try: return int((self.current_game() or {}).get('appid',0))>0
        except (OSError,ValueError,TypeError): return True

    def checkpoint(self):
        if self.closed or self.cancelled.is_set(): raise Interrupted()
        if self._playing():
            if self.job['state']!='paused_game': self._save_job(state='paused_game',stage='paused_game')
            self.compiler.cancel()
            raise Interrupted()

    def status(self):
        with self.lock:
            games=self.catalog.games()
            included=[g for g in games if selected_game(g)]
            issues=[problem for g in games if (problem:=game_problem(g,g['appid'] in self._ready))]
            return dict(name='Decky Animated Screensaver',revision='studio-1',installed_count=sum(bool(g.get('installed')) for g in games),
                game_count=len(games),ready_count=sum(g['appid'] in self._ready and selected_game(g) and (g.get('animated') or self.catalog.options()['static_fallback'] or g.get('still_mode') in {'motion','fixed'}) for g in games),excluded_count=sum(bool(g.get('excluded')) for g in games),
                included_count=len(included),failed_count=sum(g.get('status')=='error' for g in included),missing_count=sum(g.get('status')=='missing' for g in included),
                issues_count=len(issues),issues=issues[:5],
                key_configured=self._key_configured,connection=self._connection,job={**copy.deepcopy(self.job),'worker_active':self._busy()},options=self.catalog.options(),
                storage_bytes=self._usage,warning=self.catalog.warning,capabilities=self.compiler.capabilities())

    def refresh_games(self,include_new=True):
        if self._busy(): raise ScreensaverError('Pause preparation before scanning','busy')
        actual={int(g['appid']):g for g in self.games_provider() if not component(g)}
        with self.catalog.lock:
            for entry in self.catalog.data['games'].values(): entry['installed']=False
            for number,game in list(actual.items())[:2000]:
                entry=self.catalog.data['games'].setdefault(str(number),dict(appid=number,status='pending',excluded=not include_new,manual=False))
                entry.update(name=str(game['name'])[:160],installed=True)
            self.catalog.save()
        self._scanned=True; self._measure_usage()
        return self.status()

    def library(self,page=0,page_size=6,query='',filter='all'):
        games=sorted(self.catalog.games(),key=lambda g:(g.get('name','').casefold(),g['appid']))
        query=str(query)[:160].casefold()
        games=[g for g in games if query in g.get('name','').casefold() and (filter=='all'
            or filter=='attention' and game_problem(g,g['appid'] in self._ready) is not None
            or filter=='ready' and g['appid'] in self._ready or filter=='pending' and g['appid'] not in self._ready
            or filter=='included' and selected_game(g) or filter=='excluded' and g.get('excluded')
            or filter=='not_installed' and not g.get('installed') or filter=='owned' and g.get('owned')
            or filter=='missing' and g.get('status')=='missing' or filter=='animated' and g.get('animated')
            or filter=='popular' and g.get('origin')=='popular'
            or filter=='installed' and g.get('installed') or filter=='manual' and g.get('origin')=='manual')]
        page=max(0,int(page)); size=max(1,min(12,int(page_size))); count=len(games)
        page=min(page,max(0,(count-1)//size))
        return dict(items=[{**g,'problem':game_problem(g,g['appid'] in self._ready)} for g in games[page*size:(page+1)*size]],total=count,page=page,page_size=size)

    def game_details(self,number):
        game=self.catalog.get(number)
        if not game:return {}
        return {**game,'problem':game_problem(game,number in self._ready)}

    def _request(self,callback):
        self._key_configured=self._has_key()
        if not self._key_configured: raise ScreensaverError('Add your SteamGridDB key','key_missing')
        from das.provider import SteamGridDBError
        for attempt in range(3):
            if threading.current_thread() is self.thread: self.checkpoint()
            try:
                with self._api_lock:
                    delay=max(0,self._api_at-time.monotonic())
                    if threading.current_thread() is self.thread:
                        if self.cancelled.wait(delay): raise Interrupted()
                    else: time.sleep(delay)
                    try: value=callback()
                    finally: self._api_at=time.monotonic()+.35
                self._connection='verified'; return value
            except SteamGridDBError as error:
                self._connection='error'
                if error.code=='rate_limited' and attempt<2:
                    if threading.current_thread() is self.thread:
                        if self.cancelled.wait(2**attempt): raise Interrupted()
                    else: time.sleep(2**attempt)
                    continue
                raise ScreensaverError('SteamGridDB request failed','steamgriddb_'+error.code) from error

    def validate_key(self):
        self._request(lambda:self.provider._json_request(API_BASE+'/search/autocomplete/Portal'))
        return self.status()

    def _assets(self,number,role):
        entry=self.catalog.get(number)
        if not entry: raise ScreensaverError('Choose a game','not_installed')
        result=[]
        if role not in {'cover','animation','logo','still_tv','panel'}: raise ScreensaverError('Invalid artwork role','invalid_asset')
        kinds=([('grid','512x512,1024x1024','static')] if role=='panel' else [('hero',HERO_DIMENSIONS,'static'),('grid','600x900,460x215,920x430','static')] if role=='still_tv' else [('logo','','static')] if role=='logo' else [('grid','600x900','static')] if role=='cover' else [('hero','','animated'),('grid','','animated')])
        for kind,dimensions,types in kinds:
            try:
                if kind=='logo':
                    target=('steam/'+str(number)) if number>0 else ('game/'+str(-number))
                    rows=self._request(lambda:self.provider._json_request(f'{API_BASE}/logos/{target}?types=static&nsfw=false&humor=false&epilepsy=false&limit=20'))
                    values=[a for raw in rows.get('data',[]) if (a:=self.provider._asset(raw,kind,types))]
                elif number>0:
                    values=self._request(lambda:self.provider._search_kind(number,kind,dimensions,types))
                else:
                    endpoint='heroes' if kind=='hero' else 'grids'
                    rows=self._request(lambda:self.provider._json_request(f'{API_BASE}/{endpoint}/game/{-number}?types={types}&nsfw=false&humor=false&epilepsy=false&limit=50'))
                    values=[a for raw in rows.get('data',[]) if (a:=self.provider._asset(raw,kind,types))]
                result.extend(values)
            except ScreensaverError as error:
                cause=getattr(getattr(error,'__cause__',None),'__cause__',None)
                if getattr(cause,'code',0)!=404: raise
        cleaned=[]
        for value in result:
            try: asset=_safe_asset(value)
            except (ScreensaverError,ValueError,TypeError): continue
            if asset['animated'] == (role == 'animation'): cleaned.append(asset)
        if role!='animation': cleaned.sort(key=lambda a:-a['score'])
        else: cleaned.sort(key=lambda a:(a['kind']!='hero',-a['score']))
        self._event('candidates',appid=number,stage=role,received=len(result),accepted=len(cleaned))
        self._candidates[(number,role)]=cleaned[:36]
        return cleaned[:36]

    def candidates(self,number,role='animation'): return self._assets(int(number),role)

    def search(self,query):
        query=str(query).strip()[:200]
        if query.isdecimal():
            result=self._request(lambda:self.provider._json_request(f'{API_BASE}/games/steam/{int(query)}'))
            rows=[result.get('data',{})]
        elif query.startswith('https://store.steampowered.com/app/'):
            parts=urlsplit(query).path.split('/'); return self.search(parts[2])
        else:
            if len(query)<2: return []
            rows=self._request(lambda:self.provider._json_request(API_BASE+'/search/autocomplete/'+quote(query,safe=''))).get('data',[])
        return [dict(id=int(g['id']),name=str(g['name'])[:160]) for g in rows[:24] if isinstance(g,dict) and type(g.get('id')) is int and g.get('name')]

    def add(self,sgdb_id):
        sgdb_id=int(sgdb_id)
        if sgdb_id<=0: raise ScreensaverError('Invalid game ID','invalid_appid')
        row=self._request(lambda:self.provider._json_request(f'{API_BASE}/games/id/{sgdb_id}?platformdata=steam')).get('data',{})
        platforms=row.get('platforms',{}).get('steam',[])
        platform=platforms[0] if isinstance(platforms,list) and platforms else platforms
        steam=platform.get('id') if isinstance(platform,dict) else None
        number=int(steam) if steam and str(steam).isdecimal() and 0<int(steam)<=0xffffffff else -sgdb_id
        if self.catalog.get(number): return self.status()
        self.catalog.update(number,dict(name=str(row.get('name','Game'))[:160],sgdb_id=sgdb_id,installed=False,
            origin='manual',excluded=False,status='pending',manual=False))
        return self.status()

    def import_owned(self,key,profile):
        if self._busy(): raise ScreensaverError('Pause preparation first','busy')
        from .account import owned
        games=owned(key,profile)
        # Validate the entire response before changing any catalog entry.
        with self.catalog.lock:
            before=copy.deepcopy(self.catalog.data)
            try:
                for game in games:
                    number=game['appid']
                    entry=self.catalog.data['games'].setdefault(str(number),dict(appid=number,status='pending',installed=False,excluded=True,manual=False))
                    entry.update(name=game['name'],owned=True,playtime_minutes=game.get('playtime_minutes'))
                self.catalog.save()
            except BaseException: self.catalog.data=before; raise
        return self.status()

    def choose(self,number,asset_id,role='animation'):
        if self._busy(): raise ScreensaverError('Pause preparation first','busy')
        choices=self._candidates.get((int(number),role),[])
        matches=[a for a in choices if a['id']==int(asset_id)]
        if len(matches)!=1: raise ScreensaverError('Search and select artwork first','invalid_asset')
        if role=='panel': self.catalog.update(number,dict(panel_asset=matches[0],panel_manual=True,panel_pending=True))
        elif role=='cover': self.catalog.update(number,dict(cover_asset=matches[0],cover_manual=True,cover_pending=True))
        elif role=='logo': self.catalog.update(number,dict(logo_asset=matches[0],logo_pending=True))
        else:
            self.catalog.update(number,dict(asset=matches[0],manual=True,pending_change=True))
            self._ready.discard(number)
        return self.status()

    def update_game(self,number,patch):
        if self._busy(): raise ScreensaverError('Pause preparation before editing games','busy')
        if not self.catalog.get(number): raise ScreensaverError('Unknown game','not_installed')
        clean={}
        if 'excluded' in patch:
            if type(patch['excluded']) is not bool: raise ScreensaverError('Invalid inclusion','invalid_setting')
            clean['excluded']=patch['excluded']
        if 'crop' in patch: clean['crop']=crop(patch['crop'])
        if 'cover_position' in patch:
            if patch['cover_position'] not in ('bottom-left','bottom-right','top-left','top-right'):raise ScreensaverError('Invalid cover position','invalid_setting')
            clean['cover_position']=patch['cover_position']
        if 'faceplate_crop' in patch:
            value=patch['faceplate_crop']
            if (not isinstance(value,dict) or set(value)!={'x','y'} or
                    any(type(value[k]) not in (int,float) or not 0<=value[k]<=100 for k in ('x','y'))):
                raise ScreensaverError('Invalid faceplate crop','invalid_setting')
            clean['faceplate_crop']={k:round(float(value[k]),2) for k in ('x','y')}
        if patch.get('panel_automatic'):
            entry=self.catalog.get(number);media=dict(entry.get('media',{}));media.pop('panel_source',None)
            sha=dict(entry.get('sha256',{}));sha.pop('panel_source',None)
            clean.update(panel_asset=None,panel_manual=False,panel_pending=False,media=media,sha256=sha)
        if 'branding' in patch:
            value=patch['branding']
            if (not isinstance(value,dict) or value.get('mode') not in {'inherit','title','logo','both','hidden'}
                or value.get('position') not in {'inherit','bottom-left','bottom-right','top-left','top-right'}):
                raise ScreensaverError('Invalid branding','invalid_setting')
            clean['branding']=dict(value)
        if patch.get('automatic'): clean.update(manual=False,pending_change=True)
        self.catalog.update(number,clean)
        if clean.get('pending_change'): self._ready.discard(number)
        return self.status()

    def _busy(self): return bool(self.thread and self.thread is not getattr(self,'_finished_thread',None) and self.thread.is_alive())

    def select(self,kind,query='',filter='all'):
        if self._busy(): raise ScreensaverError('Pause preparation first','busy')
        first=self.library(0,12,query,filter)
        scope=first['items']+[g for page in range(1,(first['total']+11)//12) for g in self.library(page,12,query,filter)['items']]
        if kind in {'all','none'}:
            with self.catalog.lock:
                for g in scope: self.catalog.data['games'][str(g['appid'])]['excluded']=kind=='none'
                self.catalog.save()
            return self.status()
        if kind not in {'playtime','players','popular'}: raise ScreensaverError('Unknown selection','invalid_action')
        personal=[g for g in scope if g['appid']>0 and (g.get('owned') or g.get('installed'))]
        if kind=='playtime' and (not personal or any(type(g.get('playtime_minutes')) is not int for g in personal)):
            raise ScreensaverError('Import your owned games to retrieve personal playtime.','playtime_missing')
        self.cancelled.clear()
        self._save_job(state='running',stage='ranking_games',queue=[],completed=0,total=0,percent=0,error='',history=[])
        def run():
            try:
                from .selection import rank,popular
                rows=(sorted(personal,key=lambda g:(-g['playtime_minutes'],g['appid']))[:100] if kind=='playtime'
                      else rank(self,personal) if kind=='players' else popular(self))
                if self.cancelled.is_set() or self.closed: return
                with self.catalog.lock:
                    if kind=='popular':
                        for g in rows:
                            self.catalog.data['games'].setdefault(str(g['appid']),dict(**g,status='pending',installed=False,excluded=True,origin='popular'))
                    else:
                        included={g['appid'] for g in rows}
                        for g in personal: self.catalog.data['games'][str(g['appid'])]['excluded']=g['appid'] not in included
                    self.catalog.save()
                self._save_job(state='complete',stage='complete',percent=100,current_percent=100)
            except Exception as error:
                if not self.cancelled.is_set() and not self.closed:
                    self._save_job(state='paused',stage='interrupted',error=getattr(error,'code','ranking_unavailable'))
        self.thread=threading.Thread(target=run,name='studio-selection',daemon=True); self.thread.start()
        return self.status()

    def prepare(self,number=None,derivative=False,retry=False,force=False):
        with self.lock:
            if self.closed: raise ScreensaverError('Preparation is unavailable','busy')
            if self._busy():
                if self.thread.name!='animated-screensaver-prepare':
                    raise ScreensaverError('Wait for the library operation to finish','busy')
                # Coalesce repeated clicks; never run two encoders concurrently.
                self._pending_work=('prepare',number,derivative,retry,force)
                self.cancelled.set(); self.compiler.cancel()
                self._save_job(state='paused',stage='restarting',error='')
                return self.status()
            capabilities=self.compiler.capabilities()
            if not capabilities['ffmpeg']: raise ScreensaverError('Install video tools first','ffmpeg_missing')
            if capabilities.get('ffprobe') is False: raise ScreensaverError('Install the video inspection tools','ffprobe_missing')
            ensure=getattr(self.compiler,'ensure_runtime',None)
            if ensure: ensure()
            if not self._scanned: self.refresh_games()
            self._reset_preparation(number,derivative,retry,force)
            self.thread=threading.Thread(target=self._supervise,name='animated-screensaver-prepare',daemon=True); self.thread.start()
        return self.status()

    def _reset_preparation(self,number,derivative,retry,force=False):
        queue=[g['appid'] for g in self.catalog.games() if selected_game(g)
               and (number is None or g['appid']==int(number)) and (not retry or g.get('status')=='error' or bool(skipped_media(g,'background')))]
        self.cancelled.clear()
        self._save_job(state='running',stage='queued',queue=queue,completed=0,total=len(queue),error='',history=[],
            derivative=bool(derivative),force=bool(force),retry=bool(retry),appid=0,percent=0,current_percent=None,skipped_ids=[],skipped_count=0)

    def _supervise(self):
        # Reuse one thread only after the old process group and lease are gone.
        while True:
            self._run()
            with self.lock:
                request=self._pending_work; self._pending_work=None
                if self.closed or request is None:
                    self._finished_thread=threading.current_thread()
                    callback=self.after_prepare if not self.closed and not self.cancelled.is_set() and self.job['state']=='complete' else None
                    # The encoder lease is already released. Invoke under the
                    # queue lock so a restart cannot slip between both phases.
                    if callback:
                        try:callback()
                        except Exception as error:self._event('error',code=getattr(error,'code','faceplate_preparation_failed'))
                    return
                if request[0]=='prepare': self._reset_preparation(*request[1:])
                else:
                    self.cancelled.clear(); self._save_job(state='running',stage='queued',error='')

    def remove(self,number):
        if self._busy(): raise ScreensaverError('Pause preparation first','busy')
        if not self.catalog.get(number): raise ScreensaverError('Unknown game','not_installed')
        with self.catalog.lock:
            before=copy.deepcopy(self.catalog.data)
            self.catalog.data['games'].pop(str(number),None)
            try: self.catalog.save()
            except BaseException: self.catalog.data=before; raise
        self._ready.discard(number)
        # Source/cache bytes and the installed Steam snapshot remain recoverable.
        return self.status()

    def control(self,action):
        if action in {'pause','cancel'}:
            with self.lock:
                self._pending_work=None
                self.cancelled.set(); self.compiler.cancel()
                self._save_job(state='paused' if action=='pause' else 'cancelled',stage=action,
                    **({'queue':[]} if action=='cancel' else {}))
        elif action=='resume':
            with self.lock:
                if self.closed: raise ScreensaverError('Preparation is unavailable','busy')
                if self.job['state'] not in {'paused','paused_game'}: return self.status()
                if self._busy():
                    if self.thread.name!='animated-screensaver-prepare':
                        raise ScreensaverError('Wait for the library operation to finish','busy')
                    self._pending_work=('resume',)
                    self.cancelled.set(); self.compiler.cancel()
                    self._save_job(stage='resuming',error='')
                    return self.status()
                self.cancelled.clear(); self._save_job(state='running',stage='queued',error='')
                self.thread=threading.Thread(target=self._supervise,name='animated-screensaver-prepare',daemon=True); self.thread.start()
        else: raise ScreensaverError('Invalid preparation action','invalid_action')
        return self.status()

    @contextmanager
    def lease(self):
        import fcntl
        path=self.catalog.managed('prepare.lock'); fd=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e: raise ScreensaverError('Another preparation is active','worker_busy') from e
            self.compiler.lease_fd=fd; yield
        finally:
            self.compiler.lease_fd=None; os.close(fd)

    def _admit(self,additional):
        used=self.catalog.usage(); maximum=self.catalog.options()['storage_mib']*1024*1024
        if (maximum and used+additional>maximum) or shutil.disk_usage(self.root).free<additional+64*1024*1024:
            raise ScreensaverError('Storage budget reached','storage_limit')

    def _storage_available(self,reserve=64*1024*1024):
        """Unlimited quota still respects real free disk space."""
        free=max(0,shutil.disk_usage(self.root).free-reserve)
        budget=self.catalog.options()['storage_mib']*1024*1024
        return min(free,max(0,budget-self.catalog.usage())) if budget else free

    def _derivative_options(self,options,source):
        # Reserve disk space and thumbnail/metadata room even without a quota.
        room=max(0,self._storage_available()-1024*1024)
        maximum=options['max_video_mib']*1024*1024
        cap=min(room,maximum) if maximum else room
        if maximum and Path(source).stat().st_size>maximum:
            raise ScreensaverError('Visual exceeds its configured size','visual_size_limit')
        if cap<1024*1024 or Path(source).stat().st_size>cap:
            raise ScreensaverError('Storage budget reached','storage_limit')
        self._admit(cap+1024*1024)
        return {**options,'_storage_output_bytes':cap}

    def _publish_derivative(self,source,target,number,patch):
        self.checkpoint();self._admit(0)
        # Previously committed derivatives are immutable, including those
        # shared by another game or an installed snapshot.
        with self.catalog.lock:
            original=str(target.relative_to(self.root));digest=file_sha256(source)
            if target.is_symlink():raise ScreensaverError('Prepared content conflict','content_conflict')
            if target.exists() and file_sha256(target)!=digest:
                target=target.with_name(target.stem+'-'+digest[:24]+target.suffix)
                patch=copy.deepcopy(patch)
                patch['media']={key:str(target.relative_to(self.root)) if value==original else value for key,value in patch['media'].items()}
            if target.is_symlink() or target.exists() and file_sha256(target)!=digest:
                raise ScreensaverError('Prepared content conflict','content_conflict')
            created=False;relative=str(target.relative_to(self.root))
            try:
                if not target.exists():
                    os.link(source,target);created=True
                    source.unlink()
                self.checkpoint()
                return self.catalog.update(number,patch)
            except BaseException:
                saved=read_object(self.catalog.path) or {}
                referenced=any(relative in game.get('media',{}).values() for game in saved.get('games',{}).values())
                if created and not referenced:target.unlink(missing_ok=True)
                raise

    def _measure_usage(self):
        # Only explicit work calls this. Status after restart uses the receipt.
        self._usage=self.catalog.usage()
        with self.catalog.lock:
            if self.catalog.data.get('storage_bytes')!=self._usage:
                self.catalog.data['storage_bytes']=self._usage; self.catalog.save()

    def _download(self,asset,checkpoint=None,maximum=None,seconds=120,thumbnail=False):
        check=checkpoint or self.checkpoint
        progress=self.progress if checkpoint is None else lambda *args:None
        check()
        configured=maximum is None
        if configured:maximum=self.catalog.options()['max_video_mib']*1024*1024 or None
        size_error='visual_size_limit' if configured else 'source_limit'
        url=asset['url']
        from das.provider import _trusted_thumbnail
        if not (_trusted_thumbnail(url) if thumbnail else _trusted_url(url)): raise ScreensaverError('Untrusted media','invalid_asset')
        sources=self.catalog.managed('sources'); sources.mkdir(exist_ok=True,mode=0o700)
        identity=hashlib.sha256(url.encode()).hexdigest(); index=sources/(identity+'.json')
        try: saved=read_object(index)
        except (ValueError,UnicodeError): saved=None
        if saved:
            cached=None
            try:
                path=self.catalog.managed(saved['path'],True)
                if file_sha256(path)==saved['sha256']:cached=path
            except (OSError,ScreensaverError,KeyError): pass
            if cached is not None:
                if maximum is not None and cached.stat().st_size>maximum:raise ScreensaverError('Source too large',size_error)
                return cached
        available=self._storage_available()
        if available<=0:raise ScreensaverError('Storage budget reached','storage_limit')
        if maximum is None or available<maximum:size_error='storage_limit'
        maximum=min(maximum,available) if maximum is not None else available
        # Migrate a verified old source by local copy only, never change the old library.
        if self.catalog.legacy:
            old_index=self.catalog.legacy/'sources'/(identity+'.json')
            try:
                old=read_object(old_index); old_path=self.catalog.legacy/old['path']
                if old_path.resolve().is_relative_to(self.catalog.legacy) and not old_path.is_symlink() and old_path.is_file() and old_path.stat().st_size<=maximum and file_sha256(old_path)==old['sha256']:
                    self._admit(old_path.stat().st_size); target=sources/old_path.name; shutil.copyfile(old_path,target)
                    atomic_json(index,dict(path=str(target.relative_to(self.root)),sha256=old['sha256'])); return target
            except (TypeError,KeyError,ValueError,OSError,ScreensaverError): pass
        self._admit(maximum); progress('downloading',0)
        temporary=sources/('.download-'+uuid4().hex)
        try:
            request=Request(url,headers={'User-Agent':'GabeCubeAura/AnimatedScreensaverStudio'})
            try: response=self.provider.opener.open(request,timeout=10)
            except OSError as error:
                from das.provider import _certificate_failure
                fallback=getattr(self.provider,'_open_with_system_trust',None)
                if not _certificate_failure(error) or not fallback: raise
                response=fallback(request,error,timeout=10)
            count=0; started=time.monotonic(); head=b''
            with response,temporary.open('xb') as stream:
                expected=self.provider._content_length(response)
                if expected>maximum: raise ScreensaverError('Source too large',size_error)
                while True:
                    check()
                    if time.monotonic()-started>seconds: raise ScreensaverError('Download timed out','download_timeout')
                    block=response.read(65536)
                    if not block: break
                    count+=len(block)
                    if count>maximum: raise ScreensaverError('Source too large',size_error)
                    head=(head+block)[:32] if len(head)<32 else head; stream.write(block)
                    progress('downloading',count/expected if expected else None)
            if not count or expected and count!=expected: raise ScreensaverError('Incomplete media','download_incomplete')
            extension=_source_extension(head); digest=file_sha256(temporary); target=sources/(digest+'.'+extension)
            check(); os.replace(temporary,target)
            atomic_json(index,dict(path=str(target.relative_to(self.root)),sha256=digest)); return target
        finally: temporary.unlink(missing_ok=True)

    def _local_artwork(self,number):
        """Read only Steam's official cache; copy validated stills into our boundary."""
        from das.library import _steam_home
        from .media import signature
        from itertools import islice
        root=_steam_home()
        if not root or number<=0:return None
        cache=(root/'appcache/librarycache').resolve()
        if not cache.is_relative_to(root.resolve()):return None
        names=('library_hero.jpg','library_hero.png','header.jpg','header.png','library_600x900.jpg')
        paths=[cache/(str(number)+'_'+name) for name in names]
        folder=cache/str(number)
        if folder.is_dir() and not folder.is_symlink():
            # Current Steam cache can use one hash directory. Never scan the library.
            paths += [folder/name for name in names]
            try:
                for child in islice(folder.iterdir(),64):
                    if child.is_dir() and not child.is_symlink():paths += [child/name for name in names]
            except OSError:pass
        for path in paths:
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(cache) or not path.is_file() or not 0<path.stat().st_size<=16*1024*1024:continue
                fmt=signature(path)
                if fmt not in {'jpg','png'}:continue
                self._admit(path.stat().st_size)
                target=self.catalog.managed('sources/steam-'+file_sha256(path)+'.'+fmt)
                target.parent.mkdir(exist_ok=True,mode=0o700)
                if not target.exists():shutil.copyfile(path,target)
                return target
            except (OSError,ScreensaverError):continue
        return None

    @staticmethod
    def _asset_key(asset):
        return hashlib.sha256(str((asset.get('id'),asset.get('url'),asset.get('_local'))).encode()).hexdigest()

    def _asset_pool(self,number,role,preferred=None):
        """Try the explicit choice first, then bounded, distinct alternatives."""
        entry=self.catalog.get(number);seen=set()
        rejected=entry.get('rejected_assets',{}).get(role,[]) if isinstance(entry.get('rejected_assets'),dict) else []
        retry=bool(self.job.get('force') or self.job.get('retry'))
        legacy_asset=skipped_media(entry,'background' if role in {'animation','still_tv'} else role).get('asset',{})
        legacy=legacy_asset.get('id') if role not in {'animation','still_tv'} or legacy_asset.get('animated')==(role=='animation') else None
        def accepted(asset,explicit=False):
            key=self._asset_key(asset)
            if key in seen:return False
            seen.add(key)
            return retry or explicit or key not in rejected and (legacy is None or asset.get('id')!=legacy)
        if preferred and accepted(preferred,True):yield preferred
        for asset in self._assets(number,role)[:36]:
            if accepted(asset):yield asset

    def _reject_asset(self,number,role,asset,error):
        """Retain bounded technical evidence without inventing a user task."""
        self.checkpoint();entry=self.catalog.get(number)
        rejected=dict(entry.get('rejected_assets',{})) if isinstance(entry.get('rejected_assets'),dict) else {}
        rows=rejected.get(role,[]);rows=rows if isinstance(rows,list) else []
        key=self._asset_key(asset);rejected[role]=[v for v in rows if isinstance(v,str) and len(v)==64 and v!=key][-35:]+[key]
        self.catalog.update(number,dict(rejected_assets=rejected))
        record=dict(at=int(time.time()),appid=number,stage=self.job.get('stage'),code=error.code,disposition='next-candidate',
            asset=diagnostic_asset(self._active_asset),process=failure_snapshot(getattr(error,'process_failure',{})))
        ledger=self.job.get('failures',[])
        self._save_job(last_failure=record,failures=[*(ledger if isinstance(ledger,list) else []),record][-24:])
        self._event('visual_rejected',appid=number,role=role,code=error.code,asset_id=asset.get('id'))

    def _artwork_source(self,asset):
        if asset.get('_local'):return Path(asset['_local'])
        try:return self._download(asset)
        except OSError as error:
            import errno
            if error.errno in {errno.ENOSPC,errno.EDQUOT}:raise ScreensaverError('Storage unavailable','storage_limit') from error
            if error.errno in {errno.EACCES,errno.EPERM}:raise ScreensaverError('Preparation access unavailable','runtime_isolation') from error
            raise ScreensaverError('Artwork download unavailable','download_failed') from error

    def _background(self,number,entry):
        options=self.catalog.options();allow_still=options['static_fallback'] or entry.get('still_mode') in {'motion','fixed'}
        preferred=entry.get('asset') if entry.get('manual') else None
        still_choice=preferred and not preferred.get('animated')
        last=None;animation_missing=False
        for role in (['still_tv'] if still_choice else ['animation','still_tv'] if allow_still else ['animation']):
            self.checkpoint()
            if role=='still_tv' and not allow_still:break
            chosen=preferred if preferred and bool(preferred.get('animated'))==(role=='animation') else None
            def candidates():
                yield from self._asset_pool(number,role,chosen)
                if role=='still_tv':
                    local=self._local_artwork(number)
                    if local:yield dict(id=0,url='',animated=False,author='Steam',_local=str(local))
            for asset in candidates():
                self._active_asset=diagnostic_asset({**asset,'role':'background'})
                try:
                    source=self._artwork_source(asset);self._admit(64*1024*1024)
                    with tempfile.TemporaryDirectory(prefix='render-',dir=self._staging()) as temporary:
                        current_options={**options,'static_fallback':bool(allow_still)}
                        if not asset['animated'] and not allow_still:raise ScreensaverError('Static playback disabled','static_selection')
                        work=Path(temporary);result=self.compiler.prepare(source,work,current_options,self.checkpoint,self.progress,static=not asset['animated'])
                        self.checkpoint();directory=self.catalog.managed('prepared/'+file_sha256(source)[:24]+'-'+uuid4().hex[:8]);directory.parent.mkdir(exist_ok=True,mode=0o700)
                        media={k:str((directory/Path(result[k]).name).relative_to(self.root)) for k in ('tv','thumbnail')};sha={k:file_sha256(result[k]) for k in media}
                        self._admit(0);os.replace(work,directory)
                        self.catalog.update(number,dict(status='ready',skip_reason='',pending_change=False,asset=None if asset.get('_local') else asset,
                            manual=bool(chosen and asset==chosen),media=media,sha256=sha,source=str(source.relative_to(self.root)),source_sha256=file_sha256(source),
                            animated=bool(result['animated']),animation_unavailable=animation_missing,selection_policy=SELECTION_POLICY,
                            original_preserved=result['original_preserved'],width=result['width'],height=result['height'],duration=result['duration'],
                            format=Path(result['tv']).suffix[1:],credits=dict(author=asset.get('author',''),source_url=asset['url']),error=''))
                        self._ready.add(number);self._clear_media_failure(number,'background');self._clear_media_failure(number,'smoothing')
                    return True
                except ScreensaverError as error:
                    if error.code not in CANDIDATE_FAILURES:raise
                    last=error;self._reject_asset(number,role,asset,error);continue
            if role=='animation':animation_missing=True
        self._skip_image(number,last or ScreensaverError('No readable artwork','animation_missing'),'background')
        self.catalog.update(number,dict(selection_policy=SELECTION_POLICY,animation_unavailable=True,still_fallback_tried=bool(allow_still)))
        return number in self._ready

    def _optional_artwork(self,number,entry,role,options):
        if self._role_blocked(entry,role,role+'_pending'):return
        if not entry.get(role+'_pending') and entry.get('media',{}).get(role):return
        last=None
        for asset in self._asset_pool(number,role,entry.get(role+'_asset')):
            self._active_asset=diagnostic_asset({**asset,'role':role})
            try:
                source=self._artwork_source(asset);bounded=self._derivative_options(options,source)
                with tempfile.TemporaryDirectory(prefix=role+'-',dir=self._staging()) as temporary:
                    result=self.compiler.prepare(source,Path(temporary),bounded,self.checkpoint,self.progress,static=True)
                    target=self.catalog.managed('prepared/'+role+'-'+file_sha256(source)[:24]+'.'+result['format'])
                    current=self.catalog.get(number);current['media'][role]=str(target.relative_to(self.root))
                    self._publish_derivative(result['tv'],target,number,dict(media=current['media'],**{role+'_pending':False,role+'_error':'',role+'_asset':asset,role+'_credits':dict(author=asset.get('author',''),source_url=asset['url'])}))
                    self._clear_media_failure(number,role)
                return
            except ScreensaverError as error:
                if error.code not in CANDIDATE_FAILURES:raise
                last=error;self._reject_asset(number,role,asset,error);continue
        if last:self._skip_image(number,last,role)

    def _one(self,number):
        entry=self.catalog.get(number);self.checkpoint()
        blocked=self._role_blocked(entry,'background','pending_change')
        if blocked or self.catalog.ready(entry,True) and not entry.get('pending_change') and not self.job.get('force'):
            if blocked:self._note_skipped(number)
            if not self.catalog.ready(entry,True):self._ready.discard(number);return
            self._ready.add(number);self._save_job(stage='cache_ready')
        elif not self._background(number,entry):return
        entry=self.catalog.get(number);options=self.catalog.options()
        if options['show_cover']:self._optional_artwork(number,entry,'cover',options)
        mode=entry.get('branding',{}).get('mode','inherit')
        if mode in {'logo','both'} or mode=='inherit' and options['show_logo']:self._optional_artwork(number,entry,'logo',options)
        if not entry.get('animated'):
            # The original was validated above. Still movement is a player
            # transform, never another video/codec pass. Retain legacy files for
            # recoverability, but retire their recipe/error from active use.
            config=still_motion_spec(options)
            if entry.get('still_motion_config')!=config or entry.get('motion_error'):
                self.catalog.update(number,dict(still_motion_config=config,motion_error=''))
        if options['smoothing'] and entry.get('animated'):
            self._active_asset=diagnostic_asset({**(entry.get('asset') or {}),'role':'smoothing'})
            try:
                config=[options[k] for k in ('smoothing_mode','smoothing_fps')]
                if self._role_blocked(entry,'smoothing','pending_change'):self._note_skipped(number)
                elif entry.get('smoothing_config')!=config or not entry.get('media',{}).get('smoothed'):
                    bounded=self._derivative_options(options,self.catalog.managed(entry['media']['tv'],True))
                    with tempfile.TemporaryDirectory(prefix='smooth-',dir=self._staging()) as temporary:
                        result=self.compiler.smooth(self.catalog.managed(entry['media']['tv'],True),Path(temporary),bounded,self.checkpoint,self.progress)
                        if result:
                            target=self.catalog.managed('prepared/'+uuid4().hex+'.webm')
                            current=self.catalog.get(number); current['media']['smoothed']=str(target.relative_to(self.root))
                            self._publish_derivative(result,target,number,dict(media=current['media'],smoothing_config=config,smoothing_error=''))
                            self._clear_media_failure(number,'smoothing')
            except ScreensaverError as error:
                if error.code in IMAGE_FAILURES:self._skip_image(number,error,'smoothing')
                elif error.code in {'runtime_isolation','python_missing','storage_limit'}: raise
                self.catalog.update(number,dict(smoothing_error=error.code))

    def _role_blocked(self,entry,role,pending):
        if role in {'background','cover','logo'} and skipped_media(entry,role).get('selection_policy')!=SELECTION_POLICY:return False
        if role=='background' and self.catalog.options()['static_fallback'] and not entry.get('still_fallback_tried'):return False
        return bool(skipped_media(entry,role) and not entry.get(pending) and not self.job.get('force') and not self.job.get('retry'))

    def _note_skipped(self,number):
        raw=self.job.get('skipped_ids',[]);ids=[n for n in raw if type(n) is int and 0<abs(n)<=0xffffffff] if isinstance(raw,list) else []
        if number not in ids:self._save_job(skipped_ids=[*ids,number],skipped_count=len(ids)+1)

    def _clear_media_failure(self,number,role):
        raw=self.catalog.get(number).get('media_failures',{});failures=dict(raw) if isinstance(raw,dict) else {}
        if role in failures:
            failures.pop(role);self.catalog.update(number,dict(media_failures=failures))

    def _skip_image(self,number,error,role='background'):
        """One failed artwork never cancels other games or retries itself."""
        self.checkpoint()
        record=dict(at=int(time.time()),appid=number,stage=self.job.get('stage'),code=error.code,disposition='skipped',selection_policy=SELECTION_POLICY,
                    asset=diagnostic_asset(self._active_asset),process=failure_snapshot(getattr(error,'process_failure',{})))
        current=self.catalog.get(number);raw=current.get('media_failures',{});failures=dict(raw) if isinstance(raw,dict) else {};failures[role]=record
        patch=dict(media_failures=failures,selection_policy=SELECTION_POLICY)
        if role=='background':
            retained=self.catalog.ready({**current,'status':'ready','pending_change':False},True)
            patch.update(status='ready' if retained else 'skipped',skip_reason='' if retained else 'no_animation',pending_change=False,error='')
            if retained:self._ready.add(number)
            else:self._ready.discard(number)
        else:
            patch[role+'_error']=''
            if role in {'cover','logo'}:patch[role+'_pending']=False
        self.catalog.update(number,patch);self._note_skipped(number)
        self._event('visual_skipped',appid=number,role=role,code=error.code,asset_id=record['asset'].get('id'),phase=record['stage'])
        ledger=self.job.get('failures',[])
        self._save_job(stage='game_error',error=error.code,last_failure=record,
                       failures=[*(ledger if isinstance(ledger,list) else []),record][-24:])
    def _staging(self):
        path=self.catalog.managed('staging');path.mkdir(exist_ok=True,mode=0o700);return path

    def _run(self):
        try:
            with self.lease():
                while self.job['queue'] and not self.closed:
                    if self._playing():
                        self._save_job(state='paused_game',stage='paused_game')
                        while self._playing() and not self.cancelled.wait(.5) and not self.closed: pass
                        if self.cancelled.is_set() or self.closed: raise Interrupted()
                        self._save_job(state='running',stage='queued')
                    self.checkpoint(); number=self.job['queue'][0]; entry=self.catalog.get(number);self._active_asset={}
                    self._save_job(appid=number,name=entry.get('name',''),stage='checking',current_percent=None,error='')
                    try:
                        if selected_game(entry): self._one(number)
                    except Interrupted:
                        if self.job['state']=='paused_game': continue
                        raise
                    except Exception as error:
                        self.checkpoint()
                        code=getattr(error,'code','unexpected_error')
                        self._event('error',appid=number,code=code,phase=self.job.get('stage'),exception=type(error).__name__)
                        if code in IMAGE_FAILURES:
                            self._skip_image(number,error)
                        elif code in {'runtime_isolation','python_missing','storage_limit','steamgriddb_rate_limited','steamgriddb_unauthorized','steamgriddb_forbidden'}:
                            self._save_job(state='paused',stage='interrupted',error=code,
                                last_failure=dict(at=int(time.time()),appid=number,stage=self.job.get('stage'),code=code,
                                                  asset=diagnostic_asset(self._active_asset),process=failure_snapshot(getattr(error,'process_failure',{})))); raise Interrupted()
                        else:
                            # Failed replacement preserves a valid earlier scene.
                            self.catalog.update(number,dict(status='ready' if number in self._ready else 'missing' if code=='animation_missing' else 'error',error=code))
                            self._save_job(stage='game_error',error=code)
                    with self.lock:
                        if self.cancelled.is_set() or self.closed: raise Interrupted()
                        done=self.job['completed']+1
                        self._save_job(stage='game_complete',queue=self.job['queue'][1:],completed=done,percent=round(done*100/max(1,self.job['total'])))
                if not self.cancelled.is_set() and not self.closed:
                    with self.lock:
                        self.checkpoint()
                        self._save_job(state='complete',stage='complete',current_percent=100,percent=100)
        except Interrupted: pass
        except Exception as error:
            if not self.cancelled.is_set() and not self.closed:
                self._save_job(state='paused',stage='interrupted',error=getattr(error,'code','unexpected_error'))
        finally:
            try:
                if not self.cancelled.is_set(): self._measure_usage()
            except OSError: self._event('error',code='storage_receipt_failed')
            if self.closed and self.job['state']=='running': self._save_job(state='paused',stage='interrupted')

    def configure(self,patch):
        if self._busy(): raise ScreensaverError('Pause preparation before editing playback','busy')
        self.catalog.configure(patch); return self.status()
    def tick(self): pass  # Never scan, persist, resume or inspect media on the LED thread.

    def diagnostic_snapshot(self):
        with self.lock:
            # Job files survive Cancel/restart. Keep their fixed metadata only,
            # with bounded history; filenames, argv and stderr never leave here.
            def tag(value):return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',value) else ''
            def number(value,maximum=0xffffffff):return value if type(value) is int and 0<=abs(value)<=maximum else None
            def record(raw):
                if not isinstance(raw,dict) or not tag(raw.get('code')):return {}
                value=dict(code=tag(raw.get('code')),stage=tag(raw.get('stage')),at=number(raw.get('at'),2**63-1),
                           appid=number(raw.get('appid')),asset=diagnostic_asset(raw.get('asset')),process=failure_snapshot(raw.get('process')))
                if raw.get('disposition') in {'skipped','next-candidate'}:value['disposition']=raw['disposition']
                return value
            failure=record(self.job.get('last_failure',{}))
            ledger=self.job.get('failures',[])
            failures=[value for raw in (ledger[-24:] if isinstance(ledger,list) else []) if (value:=record(raw))]
            history=[dict(at=number(h.get('at'),2**63-1),stage=tag(h.get('stage')),code=tag(h.get('code')),
                          appid=number(h.get('appid'))) for h in self.job.get('history',[])[-24:] if isinstance(h,dict)]
            return dict(name='Decky Animated Screensaver',revision='studio-1',state=tag(self.job['state']),stage=tag(self.job['stage']),
                completed=self.job['completed'],total=self.job['total'],error=tag(self.job.get('error','')),history=history,
                appid=number(self.job.get('appid')),last_failure=failure,
                failures=failures,skipped_count=number(self.job.get('skipped_count',0),2000),
                ready_count=len(self._ready),connection=self._connection,candidate_lists=len(self._candidates),
                candidate_assets=sum(len(rows) for rows in self._candidates.values()))

    def maintenance(self,action,confirm=False):
        if self._busy(): raise ScreensaverError('Pause preparation first','busy')
        if action=='verify':
            for entry in self.catalog.games():
                if entry.get('status')=='ready' and not self.catalog.ready(entry,True):
                    self._ready.discard(entry['appid']); self.catalog.update(entry['appid'],dict(status='pending',error='missing_media'))
        elif action in {'unused','purge'}:
            if not confirm: raise ScreensaverError('Confirm media deletion first','confirmation_required')
            removed=0;removed_bytes=0
            used=set()
            if action=='unused':
                for g in self.catalog.games():
                    used.update(g.get('media',{}).values())
                    if g.get('source'): used.add(g['source'])
                # Source mapping JSON is cheap and retained; obsolete downloads are removed.
            import re
            removable=[]
            for folder in ('prepared','sources'):
                path=self.catalog.managed(folder)
                if path.is_dir():
                    for leaf in path.rglob('*'):
                        if leaf.is_symlink(): raise ScreensaverError('Media links were preserved','unsafe_path')
                        if leaf.is_file() and str(leaf.relative_to(self.root)) not in used:
                            # Only Studio-generated names can be removed. Foreign user files survive.
                            generated=(bool(re.fullmatch(r'[a-f0-9]{64}\.(json|gif|webp|webm|png|jpg|jpeg)',leaf.name)) if folder=='sources' else
                                bool(re.fullmatch(r'(?:[a-f0-9]{32}|(?:cover|logo)-[a-f0-9]{24})\.(gif|webp|webm|png|jpg|jpeg)',leaf.name)) or
                                bool(re.fullmatch(r'[a-f0-9]{24}-[a-f0-9]{8}',leaf.parent.name)) and leaf.name in {'original.gif','original.webp','original.webm','compatible.webm','thumbnail.jpg'})
                            if generated and (action=='purge' or leaf.suffix!='.json'): removable.append(leaf)
            for leaf in removable:
                removed_bytes+=leaf.stat().st_size;leaf.unlink();removed+=1
            prepared=self.catalog.managed('prepared')
            if prepared.is_dir():
                for directory in prepared.iterdir():
                    if directory.is_dir() and not directory.is_symlink() and not any(directory.iterdir()): directory.rmdir()
            if action=='purge':
                self._ready.clear()
                for g in self.catalog.games(): self.catalog.update(g['appid'],dict(status='pending',media={},sha256={},source='',smoothing_config=None,error=''))
                self._save_job(state='idle',stage='idle',completed=0,total=0,queue=[],history=[],appid=0,name='',percent=0,current_percent=None,error='')
            imported=self.catalog.managed('imported')
            if imported.is_dir():
                for directory in imported.iterdir():
                    if directory.is_symlink() or not directory.is_dir() or not re.fullmatch(r'[a-f0-9]{32}',directory.name):continue
                    for leaf in directory.iterdir():
                        if (leaf.is_file() and not leaf.is_symlink() and re.fullmatch(r'\d{4}-(?:tv|thumbnail|cover|logo|panel_source)\.(?:gif|webp|webm|png|jpg|jpeg)',leaf.name)
                                and (action=='purge' or str(leaf.relative_to(self.root)) not in used)):
                            removed_bytes+=leaf.stat().st_size;leaf.unlink();removed+=1
                    if not any(directory.iterdir()):directory.rmdir()
            self.last_cleanup=dict(action=action,files=removed,bytes=removed_bytes)
        else: raise ScreensaverError('Unknown maintenance action','invalid_action')
        self._measure_usage(); return self.status()

    def shutdown(self, timeout=3):
        self.closed=True; self.cancelled.set(); self.compiler.cancel()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(timeout=max(0.0, float(timeout)))
