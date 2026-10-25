"""Public Steam JSON only, verified TLS and redacted per-stage diagnostics."""
import json
from pathlib import Path
import socket
import ssl
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPSHandler
from .account import NoRedirect
from das.provider import SYSTEM_CA_BUNDLES,_certificate_failure
from das.core.catalog import ScreensaverError

ROUTES={
 ('store.steampowered.com','/api/storesearch/'): 'store_search',
 ('api.steampowered.com','/ISteamChartsService/GetGamesByConcurrentPlayers/v1/'): 'steam_chart',
 ('api.steampowered.com','/IStoreBrowseService/GetItems/v1/'): 'steam_names',
 ('api.steampowered.com','/ISteamUserStats/GetNumberOfCurrentPlayers/v1/'): 'steam_players',
}

class SteamHTTPError(ScreensaverError):
    def __init__(self,code,stage,http_status=0):
        super().__init__('Public Steam request failed',code)
        self.stage=stage;self.http_status=http_status

def public_json(url,maximum=1024*1024,timeout=8,observer=None):
    parsed=urlsplit(url);stage=ROUTES.get((parsed.hostname,parsed.path))
    if (parsed.scheme!='https' or not stage or parsed.username or parsed.password or parsed.port not in (None,443)
        or parsed.fragment or type(maximum) is not int or not 1<=maximum<=8*1024*1024):
        raise SteamHTTPError('steam_response_invalid','route')
    started=time.monotonic();deadline=started+timeout;trust='default';http_status=0
    def report(result,code=''):
        if observer:observer(dict(stage=stage,result=result,code=code,tls_trust=trust,http_status=http_status,
                                  duration_ms=min(120000,int((time.monotonic()-started)*1000))))
    request=Request(url,headers={'Accept':'application/json','User-Agent':'Decky-Animated-Screensaver/0.1'})
    try:
        try:response=build_opener(NoRedirect()).open(request,timeout=timeout)
        except (URLError,ssl.SSLError) as error:
            if not _certificate_failure(error):raise
            # Decky's embedded Python may not find SteamOS system certificates.
            # Try verified system CA bundles, never an unverified SSL context.
            response=None
            for path in SYSTEM_CA_BUNDLES:
                if not Path(path).is_file():continue
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError()
                try:context=ssl.create_default_context(cafile=path)
                except (OSError,ValueError):continue
                try:
                    trust='system'
                    response=build_opener(NoRedirect(),HTTPSHandler(context=context)).open(request,timeout=remaining)
                    break
                except (OSError,URLError) as fallback:
                    if not _certificate_failure(fallback) and not isinstance(fallback,ssl.SSLError):raise
            if response is None:raise SteamHTTPError('steam_tls_unavailable',stage)
        with response:
            http_status=int(getattr(response,'status',200) or 200)
            raw=response.read(maximum+1)
        if len(raw)>maximum:raise SteamHTTPError('steam_response_invalid',stage,http_status)
        value=json.loads(raw)
        if not isinstance(value,dict):raise SteamHTTPError('steam_response_invalid',stage,http_status)
        report('ok');return value
    except Exception as error:
        if isinstance(error,SteamHTTPError):failure=error
        elif isinstance(error,HTTPError):
            http_status=error.code;failure=SteamHTTPError('steam_rate_limited' if error.code==429 else 'steam_http_error',stage,http_status)
        elif _certificate_failure(error):failure=SteamHTTPError('steam_tls_unavailable',stage)
        elif isinstance(getattr(error,'reason',error),(TimeoutError,socket.timeout)):failure=SteamHTTPError('steam_timeout',stage)
        elif isinstance(error,(ValueError,UnicodeError)):failure=SteamHTTPError('steam_response_invalid',stage,http_status)
        else:failure=SteamHTTPError('steam_network_unavailable',stage)
        report('error',failure.code);raise failure from None
