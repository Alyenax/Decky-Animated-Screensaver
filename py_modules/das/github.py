"""Anonymous, read-only access to public release metadata and assets."""
import json
import os
from pathlib import Path
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from das.core.catalog import atomic_json

REPO='Alyenax/Decky-Animated-Screensaver'
API='https://api.github.com/repos/'+REPO
HOSTS={'api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com','github-releases.githubusercontent.com'}

class UpdateError(RuntimeError):
    def __init__(self, code):
        self.code=code
        super().__init__(code)

def trusted(url):
    p=urlparse(url)
    return p.scheme=='https' and p.hostname in HOSTS and not p.username and not p.password and p.port in (None,443)

class Redirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        if not trusted(newurl):raise UpdateError('update_unsafe_redirect')
        result=super().redirect_request(request,fp,code,msg,headers,newurl)
        if result and urlparse(newurl).hostname!=urlparse(request.full_url).hostname:result.remove_header('Authorization')
        return result

def verified_open(request,timeout=10):
    if not trusted(request.full_url):raise UpdateError('update_unsafe_url')
    contexts=[ssl.create_default_context()]
    for path in ('/etc/ssl/cert.pem','/etc/ssl/certs/ca-certificates.crt','/etc/ssl/certs/ca-bundle.crt'):
        if os.path.isfile(path):
            try:contexts.append(ssl.create_default_context(cafile=path))
            except OSError:pass
    for n,context in enumerate(contexts):
        try:return build_opener(HTTPSHandler(context=context),Redirect()).open(request,timeout=timeout)
        except URLError as error:
            if not isinstance(error.reason,ssl.SSLCertVerificationError) or n==len(contexts)-1:raise

def read_json(path,default=None):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):raise UpdateError('update_unsafe_path')
    try:
        if path.stat().st_size>512*1024:raise UpdateError('update_metadata')
        value=json.loads(path.read_text());return value if isinstance(value,dict) else dict(default or {})
    except (OSError,ValueError):return dict(default or {})

def save(path,value):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):raise UpdateError('update_unsafe_path')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);atomic_json(path,value);path.chmod(0o600)

class GitHub:
    def __init__(self,opener=verified_open):self.open=opener
    def request(self,url,asset=False):
        if not (url==API+'/releases?per_page=50' or re.fullmatch(re.escape(API)+r'/releases/assets/[1-9][0-9]*',url)):
            raise UpdateError('update_unsafe_url')
        return Request(url,headers={'Accept':'application/octet-stream' if asset else 'application/vnd.github+json',
            'User-Agent':'Decky-Animated-Screensaver updater','X-GitHub-Api-Version':'2022-11-28'})
    def fetch(self,url,limit,asset=False):
        try:
            with self.open(self.request(url,asset),timeout=10) as response:raw=response.read(limit+1)
            if len(raw)>limit:raise UpdateError('update_metadata')
            return raw
        except HTTPError as error:raise UpdateError('update_repository_access' if error.code in {401,403,404} else 'update_network') from None
        except OSError:raise UpdateError('update_network') from None
