"""Explicit Steam rankings. Bounded HTTP, no key, no partial selection commit."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from .steam_http import public_json
from .storage import component, read_object
from das.core.catalog import ScreensaverError, atomic_json

def request(endpoint,params=None,observer=None):
    url='https://api.steampowered.com/'+endpoint+'/v1/?'+urlencode(params or {})
    result=public_json(url,maximum=8*1024*1024,observer=observer).get('response')
    if not isinstance(result,dict):raise ScreensaverError('Invalid Steam response','steam_response_invalid')
    return result

def rank(service,games):
    path=service.catalog.managed('rankings.json')
    try: saved=read_object(path) or {}
    except (ValueError,ScreensaverError): saved={}
    cache=saved.get('counts',{}); now=time.time()
    def one(game):
        if service.cancelled.is_set() or service.closed: raise ScreensaverError('Selection cancelled','selection_cancelled')
        number=game['appid']; value=cache.get(str(number),{})
        if (type(value.get('at')) not in (int,float) or not 0<=now-value['at']<1800
            or type(value.get('players')) is not int or value['players']<0):
            result=request('ISteamUserStats/GetNumberOfCurrentPlayers',dict(appid=number))
            if result.get('result')!=1 or type(result.get('player_count')) is not int or result['player_count']<0:
                raise ScreensaverError('Incomplete ranking. Previous selection preserved.','ranking_unavailable')
            value=dict(players=result['player_count'],at=now)
        return number,value
    values={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for n,(number,value) in enumerate(pool.map(one,games)):
            values[str(number)]=value; service.progress('ranking_games',(n+1)/max(1,len(games)))
    atomic_json(path,dict(counts={**cache,**values}))
    return sorted(games,key=lambda g:(-values[str(g['appid'])]['players'],g['appid']))[:100]

def popular(service,with_metadata=False,observer=None):
    rows=request('ISteamChartsService/GetGamesByConcurrentPlayers',observer=observer).get('ranks')
    if not isinstance(rows,list) or not 0<len(rows)<=1000: raise ScreensaverError('Invalid Steam ranking','ranking_unavailable')
    ids=[]
    for row in rows[:100]:
        if not isinstance(row,dict):raise ScreensaverError('Invalid Steam ranking','ranking_unavailable')
        number=row.get('appid')
        if type(number) is not int or not 0<number<=0xffffffff or number in ids: raise ScreensaverError('Invalid Steam ranking','ranking_unavailable')
        ids.append(number)
    params=dict(input_json=json.dumps(dict(ids=[dict(appid=n) for n in ids],context=dict(language='english',country_code='US'),data_request=dict(include_basic_info=True))))
    items=request('IStoreBrowseService/GetItems',params,observer=observer).get('store_items',[])
    if not isinstance(items,list) or not all(isinstance(g,dict) for g in items):raise ScreensaverError('Invalid Steam metadata','ranking_unavailable')
    by_id={g.get('appid',g.get('id')):g for g in items}; result=[]
    for number in ids:
        item=by_id.get(number)
        if not item: raise ScreensaverError('Incomplete Steam metadata','ranking_unavailable')
        if item.get('success')!=1 or item.get('type')!=0: continue
        if not isinstance(item.get('name'),str): raise ScreensaverError('Invalid Steam metadata','ranking_unavailable')
        game=dict(appid=number,name=item['name'][:160])
        if with_metadata:
            source=next(row for row in rows[:100] if row['appid']==number)
            place=source.get('rank',ids.index(number)+1);players=source.get('concurrent_in_game',0)
            if type(place) is not int or not 1<=place<=100 or type(players) is not int or not 0<=players<=10**9:
                raise ScreensaverError('Invalid Steam ranking','ranking_unavailable')
            game.update(rank=place,players=players)
        if not component(game): result.append(game)
    return result
