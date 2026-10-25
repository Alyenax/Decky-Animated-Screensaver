"""In-process loopback-only player transport. No media, UI, USB or shell route."""
import errno
import hmac
import http.client
import json
import re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import socket
import secrets
import threading
import time
from urllib.parse import urlsplit
from .protocol import BrokerError,decode,identifier
from .player_debug import PlayerDebugJournal,REASONS

PATH='/jsaux/v1/player'
DEBUG_PATH='/jsaux/v1/diagnostic'
PORT=37679
SCREEN_HOSTS=frozenset(('uioverride-decky-animated-screensaver.steamscreensavers.host',
    'decky-animated-screensaver.steamscreensavers.host'))

def trusted_origin(value):
    try:
        if not isinstance(value,str) or not value.isascii() or len(value)>253:return False
        url=urlsplit(value)
        host=url.hostname or ''
        return bool(value=='https://'+host and not url.port and
            (host in SCREEN_HOSTS or re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*steamloopback\.host',host)))
    except (ValueError,AttributeError,TypeError):return False

def origin_evidence(origins):
    """Fixed categories only, never log a foreign host, URL or header value."""
    out=dict(header_count=min(len(origins),9),category='missing',scheme='none',port=0,allowed=False,reason='missing')
    if len(origins)!=1:
        if origins:out.update(category='multiple',reason='multiple')
        return out
    value=origins[0]
    if value=='null':return {**out,'category':'opaque','reason':'opaque'}
    try:
        url=urlsplit(value);host=url.hostname or '';port=url.port
        category=('screensaver-plugin' if host in SCREEN_HOSTS else 'screensaver-other' if host.endswith('.steamscreensavers.host') else
            'steamloopback' if host=='steamloopback.host' or host.endswith('.steamloopback.host') else 'foreign')
        allowed=trusted_origin(value)
        return dict(header_count=1,category=category,scheme=url.scheme if url.scheme in ('http','https') else 'other',
            port=(port or 0) if category!='foreign' else 0,allowed=allowed,
            reason='allowed' if allowed else 'scheme' if url.scheme!='https' else 'port' if port else
                'host' if category in ('foreign','screensaver-other') else 'noncanonical')
    except (ValueError,AttributeError,TypeError):return {**out,'category':'malformed','reason':'malformed'}

def safe_reply(value):
    out={}
    if isinstance(value.get('reason'),str) and value['reason'] in REASONS:out['reason']=value['reason']
    alignment=value.get('alignment_ms')
    if type(alignment) is int and -10000<=alignment<=10000 and alignment%100==0:out['alignment_ms']=alignment
    timing=value.get('timing')
    if (isinstance(timing,dict) and timing.get('basis')=='broker-confirmation-event'
            and type(timing.get('reference_mono_ms')) is int and 0<=timing['reference_mono_ms']<=2**53-1
            and type(timing.get('uncertainty_ms')) is int and 0<=timing['uncertainty_ms']<=26):
        out['timing']={key:timing[key] for key in ('reference_mono_ms','uncertainty_ms','basis')}
    remaining=value.get('lease_remaining_ms')
    if type(remaining) is int and 0<=remaining<=8000:out['lease_remaining_ms']=remaining
    for key in ('accepted','tv_only','gate_accepted','retryable'):
        if type(value.get(key)) is bool:out[key]=value[key]
    for key in ('broker_mono_ms','deadline_mono_ms'):
        item=value.get(key)
        if type(item) is int and 0<=item<=2**53-1:out[key]=item
    candidate=value.get('candidate')
    if isinstance(candidate,dict):
        try:
            identifier(candidate.get('candidate_id'));deadline=candidate.get('deadline_mono_ms')
            if (type(deadline) is int and 0<=deadline<=2**53-1 and candidate.get('phase_basis')=='gif-end-ack-assumption'
                and candidate.get('optical_alignment')=='unknown'):
                out['candidate']={key:candidate[key] for key in ('candidate_id','deadline_mono_ms','phase_basis','optical_alignment')}
        except BrokerError:pass
    return out

class _Server(ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False
    allow_reuse_address=True
    request_queue_size=4
    def __init__(self,address,handler):
        self.slots=threading.BoundedSemaphore(4)
        super().__init__(address,handler)
    def get_request(self):
        connection,address=super().get_request();connection.settimeout(4)
        return connection,address
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()
    def handle_error(self,*args):pass # Never emit payloads/paths into stderr.

class PlayerRelay:
    def __init__(self,manager,port=PORT,debug_path=None):
        self.manager=manager;self.port=port;self.server=None;self.thread=None
        self.lock=threading.RLock();self.metrics_lock=threading.Lock()
        self.metrics=dict(kind='http-loopback-v1',running=False,started_at=None,requests=0,preflights=0,
            accepted=0,refused=0,errors=0,last_error='',last_status=0,last_event='',diagnostic_requests=0,diagnostic_accepted=0)
        self.debug=PlayerDebugJournal(debug_path);self.timeline=[]
        self.probe_key=secrets.token_hex(16)

    def descriptor(self):
        return dict(kind='http-loopback-v1',url=f'http://127.0.0.1:{self.port}{PATH}')

    def snapshot(self):
        with self.metrics_lock:return dict(self.metrics)

    def debug_snapshot(self):
        with self.metrics_lock:timeline=[dict(item) for item in self.timeline[-40:]]
        return dict(browser=self.debug.snapshot(),http=timeline)

    def diagnostic_check(self):
        """Explicit local OPTIONS only. Not browser/Steam or USB evidence."""
        result=dict(browser_evidence=False)
        for route,label in ((PATH,'control_preflight'),(DEBUG_PATH,'diagnostic_preflight')):
            client=http.client.HTTPConnection('127.0.0.1',self.port,timeout=.4)
            try:
                client.request('OPTIONS',route,headers={'Origin':'https://decky-animated-screensaver.steamloopback.host',
                    'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type','X-DAS-Probe':self.probe_key})
                response=client.getresponse();response.read(2048);result[label]=response.status
            except OSError:result[label]=0
            finally:client.close()
        return result

    def _trace(self,stage,**fields):
        # Call sites pass only fixed labels/status/counters, never request data.
        with self.metrics_lock:
            self.timeline=(self.timeline+[dict(at=int(time.time()),stage=stage,**fields)])[-80:]

    def _record(self,counter=None,**fields):
        with self.metrics_lock:
            if counter:self.metrics[counter]=min(999999,self.metrics[counter]+1)
            self.metrics.update(fields)

    def start(self):
        with self.lock:
            if self.server:return
            relay=self
            class Handler(BaseHTTPRequestHandler):
                server_version='DASRelay/1'
                sys_version=''
                def log_message(self,*args):pass
                def own_probe(self):
                    value=self.headers.get('X-DAS-Probe','')
                    return value.isascii() and hmac.compare_digest(value,relay.probe_key)
                def respond(self,status,value=None,origin=None):
                    raw=json.dumps(value or {},separators=(',',':')).encode()
                    self.send_response(status)
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(raw)))
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Connection','close')
                    if origin:
                        self.send_header('Access-Control-Allow-Origin',origin)
                        self.send_header('Vary','Origin')
                        self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
                        self.send_header('Access-Control-Allow-Headers','Content-Type')
                        self.send_header('Access-Control-Allow-Private-Network','true')
                        self.send_header('Access-Control-Max-Age','600')
                    self.end_headers()
                    if self.command!='HEAD':self.wfile.write(raw)
                def boundary(self):
                    origins=self.headers.get_all('Origin',[]);hosts=self.headers.get_all('Host',[])
                    origin=origins[0] if len(origins)==1 else ''
                    route='diagnostic' if self.path==DEBUG_PATH else 'control' if self.path==PATH else 'other'
                    own_probe=self.own_probe()
                    evidence=origin_evidence(origins)
                    relay._trace('http-received',route=route,method=self.command,source='backend-check' if own_probe else 'external',origin=evidence)
                    if route=='other' or hosts!=[f'127.0.0.1:{relay.port}']:
                        relay._trace('http-refused',reason='ROUTE_REFUSED')
                        relay._record('refused',last_error='ROUTE_REFUSED',last_status=403);self.respond(403);return None
                    if not trusted_origin(origin):
                        relay._trace('http-refused',reason='ORIGIN_REFUSED',origin=evidence)
                        relay._record('refused',last_error='ORIGIN_REFUSED',last_status=403);self.respond(403);return None
                    return origin
                def do_OPTIONS(self):
                    if not self.own_probe():relay._record('preflights')
                    origin=self.boundary()
                    if not origin:return
                    if (self.headers.get('Access-Control-Request-Method')!='POST'
                        or any(item.strip().lower()!='content-type' for item in self.headers.get('Access-Control-Request-Headers','content-type').split(','))):
                        relay._trace('http-refused',reason='PREFLIGHT_REFUSED')
                        relay._record('refused',last_error='PREFLIGHT_REFUSED',last_status=403);self.respond(403,origin=origin);return
                    relay._trace('preflight-accepted')
                    relay._record(last_status=200);self.respond(200,origin=origin)
                def do_POST(self):
                    diagnostic=self.path==DEBUG_PATH
                    relay._record('diagnostic_requests' if diagnostic else 'requests')
                    origin=self.boundary()
                    if not origin:return
                    lengths=self.headers.get_all('Content-Length',[])
                    maximum=16384 if diagnostic else 4096
                    types={'application/json','text/plain'} if diagnostic else {'application/json'}
                    if (len(lengths)!=1 or not 1<=len(lengths[0])<=5 or not lengths[0].isdigit() or not 1<=int(lengths[0])<=maximum
                        or self.headers.get('Transfer-Encoding') is not None
                        or self.headers.get('Content-Type','').split(';',1)[0].strip().lower() not in types):
                        relay._trace('http-refused',reason='BODY_REFUSED')
                        relay._record('refused',last_error='BODY_REFUSED',last_status=400);self.respond(400,origin=origin);return
                    try:
                        length=int(lengths[0]);raw=self.rfile.read(length)
                        if len(raw)!=length:raise ValueError()
                        payload=decode(raw)
                        if not isinstance(payload,dict):raise ValueError()
                    except (BrokerError,ValueError,UnicodeError,socket.timeout):
                        relay._trace('http-refused',reason='JSON_REFUSED')
                        relay._record('refused',last_error='JSON_REFUSED',last_status=400);self.respond(400,origin=origin);return
                    event=payload.get('event')
                    if isinstance(event,str) and event in {'open','clock','ready','started','heartbeat','stop'}:relay._record(last_event=event)
                    if not relay.metrics['running']:
                        relay._record('refused',last_error='STOPPING',last_status=503);self.respond(503,origin=origin);return
                    token=payload.get('token');expected=relay.manager.installer.token
                    if not isinstance(token,str) or not token.isascii() or not isinstance(expected,str) or not expected or not hmac.compare_digest(token,expected):
                        relay._trace('http-refused',reason='AUTH_REFUSED')
                        relay._record('refused',last_error='AUTH_REFUSED',last_status=403);self.respond(403,origin=origin);return
                    if diagnostic:
                        accepted=relay.debug.receive(payload.get('report'))
                        relay._record('diagnostic_accepted' if accepted else 'refused',last_status=200 if accepted else 400)
                        self.respond(200 if accepted else 400,dict(accepted=accepted),origin);return
                    try:
                        began=time.monotonic()
                        result=safe_reply(relay.manager.player(payload))
                        relay._record('refused' if result.get('accepted') is False else 'accepted',last_status=200)
                        relay._trace('control-result',event=event if event in ('open','clock','ready','started','heartbeat','stop') else 'invalid',
                            accepted=result.get('accepted'),reason=result.get('reason'),elapsed_ms=round((time.monotonic()-began)*1000))
                        self.respond(200,result,origin)
                    except (BrokenPipeError,ConnectionResetError):pass
                    except Exception:
                        relay._trace('http-refused',reason='BACKEND_FAILED')
                        relay._record('errors',last_error='BACKEND_FAILED',last_status=503);self.respond(503,origin=origin)
            try:
                server=_Server(('127.0.0.1',self.port),Handler)
            except OSError as error:
                self._record('errors',last_error='ADDRESS_IN_USE' if error.errno==errno.EADDRINUSE else 'BIND_FAILED')
                raise BrokerError('JSAUX_RELAY_UNAVAILABLE') from None
            self.port=server.server_address[1];self.server=server
            self._record(running=True,started_at=int(time.time()),last_error='')
            self._trace('listener-started')
            self.thread=threading.Thread(target=server.serve_forever,kwargs=dict(poll_interval=.25),name='das-player-relay',daemon=True)
            try:self.thread.start()
            except RuntimeError:
                server.server_close();self.server=None;self.thread=None
                self._record('errors',running=False,last_error='START_FAILED')
                raise BrokerError('JSAUX_RELAY_UNAVAILABLE') from None

    def close(self,timeout=1):
        with self.lock:
            self._record(running=False)
            self._trace('listener-stopped')
            if self.server:
                self.server.shutdown();self.server.server_close();self.server=None
            if self.thread:self.thread.join(max(0,timeout));self.thread=None
