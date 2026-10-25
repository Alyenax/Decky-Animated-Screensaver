"""Optional, explicit Steam library import. The personal key is never stored."""
import json
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .storage import component
from das.core.catalog import ScreensaverError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def profile(value):
    value=str(value).strip()
    if re.fullmatch(r'7656119\d{10}',value): return {'steamid':value}
    url=urlsplit(value)
    if url.scheme!='https' or url.netloc!='steamcommunity.com' or url.query or url.fragment:
        raise ScreensaverError('Enter a SteamID64 or HTTPS Steam Community profile URL','invalid_profile')
    match=re.fullmatch(r'/(profiles|id)/([A-Za-z0-9_-]{1,100})/?',url.path)
    if not match: raise ScreensaverError('Invalid Steam profile','invalid_profile')
    if match[1]=='profiles': return profile(match[2])
    return {'vanityurl':match[2]}

def owned(key,value,opener=None):
    if not isinstance(key,str) or not re.fullmatch('[A-Fa-f0-9]{32}',key):
        raise ScreensaverError('Enter your personal Steam Web API key','steam_key_missing')
    parsed=profile(value); opener=opener or build_opener(NoRedirect())
    def request(endpoint,params):
        # No redirect, logging, generic exception text, persistence, or SGDB bearer header.
        url='https://api.steampowered.com/'+endpoint+'/v1/?'+urlencode({**params,'key':key})
        try:
            with opener.open(Request(url,headers={'Accept':'application/json'}),timeout=12) as response:
                body=response.read(8*1024*1024+1)
            if len(body)>8*1024*1024: raise ValueError()
            result=json.loads(body).get('response')
            if not isinstance(result,dict): raise ValueError()
            return result
        except Exception:
            raise ScreensaverError('Steam library unavailable. Check the key and Game details privacy.','steam_library_unavailable') from None
    if 'vanityurl' in parsed:
        parsed={'steamid':request('ISteamUser/ResolveVanityURL',parsed).get('steamid','')}
        profile(parsed['steamid'])
    result=request('IPlayerService/GetOwnedGames',{**parsed,'include_appinfo':1,'include_played_free_games':1})
    rows=result.get('games',[]); count=result.get('game_count')
    if type(count) is not int or not isinstance(rows,list) or len(rows)!=count or count>10000:
        raise ScreensaverError('Steam did not expose a complete library','steam_library_unavailable')
    clean=[]; seen=set()
    for row in rows:
        if not isinstance(row,dict): raise ScreensaverError('Steam returned an invalid library','steam_library_unavailable')
        number=row.get('appid'); name=row.get('name')
        if type(number) is not int or not 0<number<=0xffffffff or number in seen or not isinstance(name,str) or not name.strip():
            raise ScreensaverError('Steam returned an invalid library','steam_library_unavailable')
        seen.add(number); game=dict(appid=number,name=name.strip()[:160])
        if type(row.get('playtime_forever')) is int and row['playtime_forever']>=0: game['playtime_minutes']=row['playtime_forever']
        if not component(game): clean.append(game)
    return clean
