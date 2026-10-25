"""On-demand discovery. No decoder, USB, inventory selection or idle worker."""
import copy
import threading
import time
import unicodedata
from urllib.parse import urlencode, urlsplit
from .steam_http import public_json
from .storage import read_object, component
from das.core.catalog import ScreensaverError, atomic_json

def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold().replace('’',"'")) if not unicodedata.combining(c)).strip()

def steam_image(value):
    try:
        u=urlsplit(value)
        return (u.scheme=='https' and u.hostname in {'shared.akamai.steamstatic.com','shared.fastly.steamstatic.com','cdn.akamai.steamstatic.com','cdn.cloudflare.steamstatic.com'}
                and not u.username and not u.password and u.port in (None,443)
                and u.path.startswith(('/steam/apps/','/store_item_assets/steam/apps/')) and u.path.lower().endswith(('.jpg','.png')))
    except (ValueError,TypeError):return False

def thumbnail(game):
    if steam_image(game.get('thumbnail_url','')):return game['thumbnail_url']
    number=game.get('appid')
    return f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{number}/header.jpg' if type(number) is int and 0<number<=0xffffffff else ''

def valid_top(value,now):
    if not isinstance(value,dict) or type(value.get('at')) is not int or not 0<=now-value['at']<=7*86400:return False
    rows=value.get('items')
    if not isinstance(rows,list) or not 0<len(rows)<=100:return False
    ids=set()
    for g in rows:
        if not isinstance(g,dict):return False
        if set(g)-{'appid','name','rank','players','excluded','collection_member','installed','status','origin','thumbnail_url'}:return False
        n=g.get('appid');rank=g.get('rank');players=g.get('players')
        if (type(n) is not int or not 0<n<=0xffffffff or n in ids or not isinstance(g.get('name'),str)
            or not 0<len(g['name'])<=160 or type(rank) is not int or not 1<=rank<=100
            or type(players) is not int or not 0<=players<=10**9 or not steam_image(g.get('thumbnail_url',''))):return False
        ids.add(n)
    return value.get('total')==len(rows) and value.get('source')=='steam-current-players'

def image_diagnostic(value):
    if not isinstance(value,dict) or value.get('schema')!='das-artwork-load-v1':return {}
    stages={'blocked','load','ready','error','timeout','snapshot','snapshot_failed'}
    raw=value.get('counts',{});counts={k:v for k,v in raw.items() if k in stages and type(v) is int and 0<=v<=999999} if isinstance(raw,dict) else {}
    events=[]
    raw=value.get('events',[])
    for e in raw[-24:] if isinstance(raw,list) else []:
        if (isinstance(e,dict) and all(isinstance(e.get(k),str) for k in ('stage','source','format')) and e.get('stage') in stages and e.get('source') in {'local','sgdb','sgdb_legacy','steam','other'}
            and e.get('format') in {'data','png','jpg','jpeg','webp','gif','other'}):events.append({k:e[k] for k in ('stage','source','format')})
    return dict(schema='das-artwork-load-v1',counts=counts,events=events)

class Discovery:
    def __init__(self,service):
        self.service=service;self.lock=threading.RLock();self.gate=threading.BoundedSemaphore(2)
        self.searches={};self.known={};self.path=service.catalog.managed('discovery-top-v1.json')
        self.candidate_cache={};self.events=[]
        try:self.top=read_object(self.path,1024*1024) or {}
        except (OSError,ValueError,ScreensaverError):self.top={}

    def record(self,event):
        safe={k:v for k,v in event.items() if k in {'stage','result','code','tls_trust','http_status','duration_ms'}
              and type(v) in (str,int) and (not isinstance(v,str) or len(v)<=80 and all(c.isalnum() or c=='_' for c in v))}
        with self.lock:self.events=(self.events+[dict(at=int(time.time()),**safe)])[-32:]

    def diagnostic_snapshot(self):
        self._prune_candidates()
        with self.lock:return dict(events=copy.deepcopy(self.events),top_cached=valid_top(self.top,int(time.time())),
                                   cached_queries=len(self.searches),cached_candidate_lists=len(self.candidate_cache))

    def _remember(self,rows):
        with self.lock:
            for g in rows:self.known[g['appid']]=copy.deepcopy(g)
            while len(self.known)>2000:self.known.pop(next(iter(self.known)))

    def search(self,query):
        query=' '.join(str(query).split())[:160];key=normalized(query)
        if len(key)<3:return dict(items=[],total=0,source='steam',minimum=3)
        with self.lock:
            saved=self.searches.get(key)
            if saved and time.time()-saved['at']<300:return copy.deepcopy(saved['value'])
        if not self.gate.acquire(False):raise ScreensaverError('Discovery busy','read_busy')
        try:
            url='https://store.steampowered.com/api/storesearch/?'+urlencode(dict(term=query,l='english',cc='FR'))
            try:
                data=public_json(url,observer=self.record);values=data.get('items',[])
                if not isinstance(values,list):raise ValueError()
                rows=[]
                for g in values[:24]:
                    if not isinstance(g,dict):continue
                    number=g.get('id')
                    if type(number) is int and 0<number<=0xffffffff and isinstance(g.get('name'),str) and not component(g):
                        entry=dict(appid=number,name=g['name'][:160],installed=False,status='pending',excluded=True,collection_member=False,origin='steam-search')
                        entry['thumbnail_url']=g.get('tiny_image') if steam_image(g.get('tiny_image','')) else thumbnail(entry)
                        rows.append(entry)
                result=dict(items=rows,total=len(rows),source='steam')
            except ScreensaverError:raise
            except Exception as error:raise ScreensaverError('Steam search unavailable','search_unavailable') from error
            self._remember(rows)
            with self.lock:
                self.searches[key]=dict(at=time.time(),value=copy.deepcopy(result))
                while len(self.searches)>24:self.searches.pop(next(iter(self.searches)))
            return result
        finally:self.gate.release()

    def ranking(self,force=False):
        with self.lock:
            cached=copy.deepcopy(self.top)
        now=int(time.time())
        valid=valid_top(cached,now)
        if valid and not force and 0<=now-cached['at']<1800:
            self._remember(cached['items']);return {**cached,'cached':True,'stale':False}
        if not self.gate.acquire(False):raise ScreensaverError('Discovery busy','read_busy')
        try:
            try:
                from .selection import popular
                rows=popular(self.service,with_metadata=True,observer=self.record)
                rows=[dict(**g,excluded=True,collection_member=False,installed=False,status='pending',origin='steam-top',thumbnail_url=thumbnail(g)) for g in rows]
                result=dict(items=rows,total=len(rows),source='steam-current-players',at=now,source_entries=100)
                if not valid_top(result,now):raise ScreensaverError('Invalid Steam ranking','ranking_unavailable')
                try:atomic_json(self.path,result)
                except OSError:self.record(dict(stage='ranking_cache',result='error',code='steam_cache_unavailable'))
                with self.lock:self.top=copy.deepcopy(result)
                self._remember(rows);return {**result,'cached':False,'stale':False}
            except Exception as error:
                code=error.code if isinstance(error,ScreensaverError) else 'ranking_unavailable'
                self.record(dict(stage='ranking',result='error',code=code))
                if valid:self._remember(cached['items']);return {**cached,'cached':True,'stale':True,'error':'ranking_unavailable'}
                if isinstance(error,ScreensaverError):raise
                raise ScreensaverError('Steam ranking unavailable','ranking_unavailable') from None
        finally:self.gate.release()

    def open(self,number):
        current=self.service.catalog.get(number)
        if current:return current
        with self.lock:known=copy.deepcopy(self.known.get(number))
        if not known:raise ScreensaverError('Search for this game first','not_installed')
        # Opening a result only records metadata; it does not select the game,
        # change the running recipe, prepare a source or touch hardware.
        with self.service.catalog.lock:
            if not self.service.catalog.get(number):self.service.catalog.update(number,known)
        return self.service.catalog.get(number)

    def _prune_candidates(self):
        with self.lock:
            for key,(stamp,_) in list(self.candidate_cache.items()):
                if time.time()-stamp>=300:self.candidate_cache.pop(key,None)

    def candidates(self,number,role):
        self._prune_candidates()
        key=(number,role)
        with self.lock:
            cached=self.candidate_cache.get(key)
            if cached and time.time()-cached[0]<300:
                self.service._candidates[key]=copy.deepcopy(cached[1])
                return copy.deepcopy(cached[1])
        if not self.gate.acquire(False):raise ScreensaverError('Discovery busy','read_busy')
        try:
            rows=self.service.candidates(number,role)
            with self.lock:
                self.service._candidates[key]=copy.deepcopy(rows)
                self.candidate_cache[key]=(time.time(),copy.deepcopy(rows))
                while len(self.candidate_cache)>24:self.candidate_cache.pop(next(iter(self.candidate_cache)))
                while len(self.service._candidates)>24:self.service._candidates.pop(next(iter(self.service._candidates)))
            return rows
        finally:self.gate.release()
