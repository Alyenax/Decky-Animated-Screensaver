"""Bounded SteamGridDB transport. Secrets never leave the backend."""
import json
import os
from pathlib import Path
import re
import ssl
import threading
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from urllib.error import HTTPError, URLError
from .core.catalog import atomic_json

API_BASE='https://www.steamgriddb.com/api/v2'
HERO_DIMENSIONS='1920x620,3840x1240,1600x650'
SYSTEM_CA_BUNDLES=('/etc/ssl/cert.pem','/etc/ca-certificates/extracted/tls-ca-bundle.pem','/etc/ssl/certs/ca-certificates.crt')

class SteamGridDBError(RuntimeError):
    def __init__(self,message,code='request_failed'):
        super().__init__(message);self.code=code

def _certificate_failure(error):
    reason=getattr(error,'reason',error)
    return isinstance(reason,ssl.SSLCertVerificationError) or isinstance(reason,ssl.SSLError) and 'CERTIFICATE_VERIFY_FAILED' in str(reason)

def _trusted_url(value):
    try:
        url=urlsplit(str(value or ''));host=(url.hostname or '').lower()
        return url.scheme=='https' and (host=='steamgriddb.com' or host.endswith('.steamgriddb.com')) and not url.username and not url.password and url.port in (None,443)
    except ValueError:return False

def _trusted_thumbnail(value):
    if _trusted_url(value):return True
    try:
        u=urlsplit(str(value or ''))
        return u.scheme=='https' and not u.username and not u.password and u.port in (None,443) and u.path.lower().endswith(('.png','.jpg','.jpeg','.webp','.gif')) and (
            u.hostname=='s3.amazonaws.com' and u.path.startswith('/steamgriddb/thumb/') or
            u.hostname=='steamgriddb.s3.amazonaws.com' and u.path.startswith('/thumb/'))
    except ValueError:return False

class Redirects(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        if not (_trusted_url(newurl) or _trusted_thumbnail(request.full_url) and _trusted_thumbnail(newurl)):
            raise SteamGridDBError('Untrusted artwork redirect','untrusted_host')
        redirected=super().redirect_request(request,fp,code,msg,headers,newurl)
        if redirected and urlsplit(request.full_url).hostname!=urlsplit(newurl).hostname:
            redirected.remove_header('Authorization')
        return redirected

def _source_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'png'
    if data.startswith(b'\xff\xd8'):return 'jpg'
    if data[:6] in (b'GIF87a',b'GIF89a'):return 'gif'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP':return 'webp'
    if data.startswith(b'\x1a\x45\xdf\xa3'):return 'webm'
    raise SteamGridDBError('Unsupported artwork format','invalid_media')

class Provider:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock();self.key=''
        self.opener=build_opener(Redirects())
        try:
            if self.path.is_symlink() or self.path.stat().st_size>2048:raise ValueError()
            value=json.loads(self.path.read_text()).get('key','')
            if re.fullmatch(r'[A-Za-z0-9._~-]{16,512}',value):self.key=value
            os.chmod(self.path,0o600)
        except (OSError,ValueError,TypeError):pass

    def status(self):return dict(configured=bool(self.key))

    def save(self,key):
        if not isinstance(key,str):raise ValueError('Invalid API key')
        key=key.strip()
        if key and not re.fullmatch(r'[A-Za-z0-9._~-]{16,512}',key):raise ValueError('Invalid API key format')
        with self.lock:
            atomic_json(self.path,dict(key=key));self.key=key

    def _fallback_opener(self):
        # Use actual system CAs after a certificate failure, never disable TLS.
        for path in SYSTEM_CA_BUNDLES:
            if Path(path).is_file():
                return build_opener(Redirects(),HTTPSHandler(context=ssl.create_default_context(cafile=path)))
        return None

    def _open_with_system_trust(self,request,error,timeout=10):
        opener=self._fallback_opener() if _certificate_failure(error) else None
        if not opener:raise error
        return opener.open(request,timeout=timeout)

    @staticmethod
    def _content_length(response):
        value=response.headers.get('Content-Length')
        if value is None:return 0
        try:return int(value)
        except ValueError:raise SteamGridDBError('Invalid artwork length','invalid_media') from None

    def _json_request(self,url):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname!='www.steamgriddb.com' or not parsed.path.startswith('/api/v2/'):
            raise SteamGridDBError('Invalid API route','untrusted_host')
        if not self.key:raise SteamGridDBError('Add a SteamGridDB key','unauthorized')
        request=Request(url,headers={'Authorization':'Bearer '+self.key,'Accept':'application/json','User-Agent':'Decky-Animated-Screensaver/0.1.0'})
        try:
            try:response=self.opener.open(request,timeout=10)
            except URLError as error:
                fallback=self._fallback_opener() if _certificate_failure(error) else None
                if not fallback:raise
                response=fallback.open(request,timeout=10)
            with response:raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError()
            value=json.loads(raw)
            if not isinstance(value,dict) or value.get('success') is not True:raise ValueError()
            return value
        except HTTPError as error:
            code={401:'unauthorized',403:'forbidden',429:'rate_limited',404:'not_found'}.get(error.code,'http_error')
            raise SteamGridDBError('SteamGridDB request failed',code) from error
        except (URLError,OSError,ValueError):
            raise SteamGridDBError('SteamGridDB connection failed','request_failed') from None

    @staticmethod
    def _asset(raw,kind,requested_type=None):
        if not isinstance(raw,dict) or not _trusted_url(raw.get('url')):return None
        # SGDB animated assets are WebP. Individual response rows need not
        # repeat the query's `types=animated`; WebP alone can also be static.
        # Preserve the trusted search context, as the desktop provider does.
        animated=(requested_type=='animated' if requested_type in {'animated','static'} else
            raw.get('type')=='animated' or bool(raw.get('animated')) or str(raw.get('mime','')).lower() in ('image/gif','video/webm') or urlsplit(raw['url']).path.lower().endswith(('.gif','.webm')))
        return dict(id=raw.get('id'),kind=kind,url=raw['url'],thumb=raw.get('thumb',''),
            width=raw.get('width',0),height=raw.get('height',0),score=raw.get('score',0),
            animated=animated,
            author=str((raw.get('author') or {}).get('name','SteamGridDB')))

    def _search_kind(self,number,kind,dimensions,types):
        endpoint='heroes' if kind=='hero' else 'grids'
        params=dict(types=types,nsfw='false',humor='false',epilepsy='false',limit=50)
        if dimensions:params['dimensions']=dimensions
        rows=self._json_request(f'{API_BASE}/{endpoint}/steam/{number}?'+urlencode(params)).get('data',[])
        return [asset for raw in rows if (asset:=self._asset(raw,kind,types))]
