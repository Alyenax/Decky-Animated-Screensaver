"""Bounded, metadata-only player traces. Never store arbitrary browser text."""
import copy
import json
import os
from pathlib import Path
import re
import threading
import time
import stat
from das.core.catalog import atomic_json, ScreensaverError
from das.studio.storage import read_object

SCHEMA='das-player-debug-v1'
EVENTS=set('boot configured dom-ready window-load script-loaded script-error runtime-start catalog-loaded '
    'catalog-missing catalog-filtered presentation-check lifecycle-check lifecycle-disabled transport-selected '
    'request response request-failed request-timeout open-result clock-result media-ready gate-result '
    'tv-start stop visibility pagehide paused media-error js-error js-rejection csp-violation '
    'diagnostic-send diagnostic-result diagnostic-failed'.split())
REASONS=set('none preview config-disabled config-missing mode-invalid collection-invalid token-invalid '
    'origin-refused relay-invalid fetch-missing transport-unavailable presentation-invalid '
    'http-failed timeout rejected accepted tv-only independent software-coordinated '
    'clock-unavailable deadline-expired hidden player-ended unknown '
    'bootstrap config catalog runtime stylesheet media loopback-player loopback-diagnostic other inline eval '
    'script-src script-src-elem connect-src img-src media-src default-src style-src '
    'Error TypeError ReferenceError RangeError SyntaxError DOMException AbortError SecurityError NotAllowedError '
    'steam-host steam-subdomain screensaver-host http-host file other-origin'.split())
EVENTS.add('first-frame-held');REASONS.add('matrix-start')
EVENTS.add('alignment-reference')
EVENTS.update(('heartbeat-degraded','heartbeat-recovered','gca-handoff'))
REASONS.update(('transport-lost','lease-expired','BROKER_UNAVAILABLE','STALE_BOOT','DISPLAY_OFF','SUSPENDED','AUTH_DENIED'))
FLAGS=set('secure top hidden installed fetch native config_enabled token_valid collection_valid relay_valid '
    'preview presentation_valid version_match duration_match orientation_match transition_match '
    'order_match count_match catalog_match build_match accepted gate_accepted candidate mapping_valid online '
    'origin_valid path_expected port_default has_parent reference_valid calibrated'.split())
EVENTS.update('scene-attempt scene-visible scene-timeout media-waiting media-stalled media-ended player-state lifecycle-exit input-observed freeze beforeunload broker-refused'.split())
REASONS.update('visibility-hidden page-hidden frozen unloading destroyed catalog-replaced manual-pause coordinated-ended broker-refused keydown pointerdown gamepad-connected gamepad-disconnected STEAM_INACTIVE STEAM_STATE_STALE LEASE_EXPIRED SESSION_UNKNOWN OPERATION_UNKNOWN PRIORITY_ACTIVE DISPLAY_DISABLED SYSTEM_SUSPENDED FLASH_PROTECTED INTERNAL_ERROR'.split())
FLAGS.update('playing loading coordinated video paused connected persisted focused'.split())
NUMBERS=('status','count','expected','actual','line','column','sequence','scene','slot','age_ms','media_ms','ready_state','network_state','media_error','gap_ms')
CRITICAL=set('stop pagehide visibility freeze beforeunload lifecycle-exit broker-refused js-error js-rejection media-error scene-timeout'.split())
MILESTONES=CRITICAL|set('first-frame-held gate-result alignment-reference tv-start'.split())

def compact_events(events,limit=32):
    if len(events)<=limit:return events[:]
    selected={e['seq']:e for e in events[:8]+[e for e in events if e['event'] in MILESTONES][-12:]+events[-12:]}
    for event in events:
        if len(selected)>=limit:break
        selected[event['seq']]=event
    return sorted(selected.values(),key=lambda e:e['seq'])

def clean_event(value):
    if not isinstance(value,dict) or not isinstance(value.get('event'),str) or value['event'] not in EVENTS:return None
    if any(type(value.get(k)) is not int or not 0<=value[k]<=2**31-1 for k in ('seq','ms')):return None
    out={k:value[k] for k in ('event','seq','ms')}
    for key in ('reason','resource'):
        if isinstance(value.get(key),str) and value[key] in REASONS:out[key]=value[key]
    if value.get('action') in ('open','clock','ready','started','heartbeat','stop'):out['action']=value['action']
    for key in NUMBERS:
        if type(value.get(key)) is int and 0<=value[key]<=2**31-1:out[key]=value[key]
    if isinstance(value.get('flags'),dict):out['flags']={k:v for k,v in value['flags'].items() if k in FLAGS and type(v) is bool}
    return out

def clean_report(value):
    if not isinstance(value,dict) or value.get('schema')!=SCHEMA:return None
    run=value.get('run');build=value.get('build')
    if not isinstance(run,str) or not re.fullmatch('[a-f0-9]{16}',run):return None
    if not isinstance(build,str) or not re.fullmatch('[a-f0-9]{12}|unknown',build):return None
    if not isinstance(value.get('events'),list) or len(value['events'])>64:return None
    out=dict(schema=SCHEMA,run=run,build=build,events=[item for raw in value['events'] if (item:=clean_event(raw)) is not None])
    for key in ('began_at_ms','sent_at_ms'):
        if type(value.get(key)) is int and 0<=value[key]<=2**53-1:out[key]=value[key]
    return out

def bounded_runs(runs):
    out=copy.deepcopy(runs[-3:])
    for run in out:
        events=run['events']
        run['events']=compact_events(events)
    while len(json.dumps(out).encode())>12000:
        if len(out)>1:out.pop(0)
        elif len(out[0]['events'])>1:out[0]['events'].pop(1)
        else:return []
    return out

class PlayerDebugJournal:
    def __init__(self,path=None):
        self.path=Path(path) if path else None;self.lock=threading.RLock();self.runs=[];self.io_error=False;self.io_error_kind=None
        if self.path:
            try:
                saved=read_object(self.path,128*1024) or {}
                for raw in saved.get('runs',[])[:4]:
                    item=clean_report(raw)
                    if item:self.runs.append({**item,'received_at':0,'recovered':True})
            except (OSError,ValueError,TypeError,ScreensaverError) as error:self._storage_failure(error)

    def _storage_failure(self,error):
        self.io_error=True
        self.io_error_kind=('permission-denied' if isinstance(error,PermissionError) else 'no-space' if getattr(error,'errno',None)==28 else
            'unsafe-or-invalid' if isinstance(error,(ValueError,TypeError,ScreensaverError)) else 'io-error')

    def receive(self,value):
        item=clean_report(value)
        if item is None:return False
        with self.lock:
            old=next((run for run in self.runs if run['run']==item['run']),None)
            events={e['seq']:e for e in (old or {}).get('events',[])}
            events.update({e['seq']:e for e in item['events']})
            ordered=[events[n] for n in sorted(events)]
            if len(ordered)>64:
                # Preserve recent terminal milestones even after late healthy
                # traffic or an out-of-order POST; never grow an append log.
                selected={e['seq']:e for e in compact_events(ordered)+ordered[-32:]}
                ordered=sorted(selected.values(),key=lambda e:e['seq'])
            item.update(events=ordered,received_at=int(time.time()),recovered=False)
            self.runs=[run for run in self.runs if run['run']!=item['run']][-3:]+[item]
            self._save()
        return True

    def _save(self):
        if not self.path:return
        try:
            # No append-only growth; atomic replacement is private (0600).
            if self.path.is_symlink():raise ValueError()
            if self.path.exists():
                info=self.path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid():raise ValueError()
            value=dict(schema=SCHEMA,runs=self.runs)
            if len(json.dumps(value).encode())>128*1024:raise ValueError()
            atomic_json(self.path,value)
        except (OSError,ValueError,ScreensaverError) as error:self._storage_failure(error)

    def snapshot(self):
        with self.lock:return dict(schema=SCHEMA,runs=bounded_runs(self.runs),storage_error=self.io_error,
            storage_error_kind=self.io_error_kind,
            sessions=[self._session_summary(run) for run in self.runs[-3:]],
            browser_evidence='received' if self.runs else 'not-received',
            fallback='Steam cef_log: [DAS-JSAUX-DEBUG]',physical_playback='not-measured')

    @staticmethod
    def _session_summary(run):
        events=run['events'];last=events[-1] if events else {};terminal=[e for e in events if e['event'] in {'stop','pagehide','freeze','beforeunload','lifecycle-exit','broker-refused'}
            or e['event']=='visibility' and e.get('flags',{}).get('hidden') is True]
        scenes=[e for e in events if e['event'] in {'scene-visible','player-state'} and type(e.get('scene')) is int]
        return dict(run=run['run'],build=run['build'],began_at_ms=run.get('began_at_ms'),received_at=run.get('received_at'),last_ms=last.get('ms',0),last_sequence=last.get('seq',0),
            last_scene=scenes[-1].get('scene') if scenes else None,terminal=terminal[-4:],
            conclusion='terminal-observed' if terminal else 'no-terminal-received',physical_cause='not-established')


def collect_cef(steam_root):
    """Explicit report only; tail two fixed Steam logs, export no raw log text.

    This is the independent escape hatch when Chrome blocks every local fetch.
    Never search the filesystem or retain unrelated browser/Steam activity.
    """
    result=dict(reads=[],runs=[],network=[],engine=[])
    if not steam_root:return result
    groups={};network=[];engine=[]
    for name in ('cef_log.txt','cef_log.previous.txt'):
        path=Path(steam_root)/'logs'/name;entry=dict(source='current' if name=='cef_log.txt' else 'previous',state='missing')
        try:
            fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):raise ValueError()
                stream.seek(max(0,info.st_size-256*1024));raw=stream.read(256*1024).decode('utf-8','replace')
            entry['state']='read'
            for line in raw.splitlines():
                if '[DAS-JSAUX-DEBUG] ' in line:
                    tail=line.split('[DAS-JSAUX-DEBUG] ',1)[1]
                    value=None
                    for text in (tail,tail.replace('\\"','"')):
                        try:value=json.JSONDecoder().raw_decode(text)[0];break
                        except (ValueError,RecursionError):continue
                    if not isinstance(value,dict):continue
                    event=clean_event(value)
                    checked=clean_report(dict(schema=SCHEMA,run=value.get('run'),build=value.get('build'),events=[event] if event else []))
                    if checked and event:
                        key=(checked['run'],checked['build'])
                        groups.setdefault(key,[]).append(event)
                elif 'decky-animated-screensaver' in line.lower() or '127.0.0.1:37679' in line:
                    lowered=line.lower();code=None
                    for pattern,label in (('render process gone','renderer-gone'),('render process exited','renderer-exited'),
                        ('out of memory','out-of-memory'),('context lost','context-lost'),('gpu process crashed','gpu-crashed'),
                        ('pipeline_error','media-pipeline-error'),('demuxer_error','media-demuxer-error'),('media_err_decode','media-decode-error')):
                        if pattern in lowered:engine.append(dict(source=entry['source'],code=label));break
                    for pattern,label in (('mixed content','mixed-content'),('private network','private-network'),
                        ('local network','local-network'),('address space','address-space'),('content security policy','csp'),
                        ('connect-src','csp'),('cors','cors'),('access-control','cors'),('syntaxerror','script-syntax')):
                        if pattern in lowered:code=label;break
                    for error in ('ERR_CONNECTION_REFUSED','ERR_CONNECTION_RESET','ERR_BLOCKED_BY_CLIENT','ERR_FAILED','ERR_TIMED_OUT','ERR_INSECURE_RESPONSE'):
                        if error in line:code=error;break
                    if code:
                        metadata=dict(source=entry['source'],code=code)
                        resource=re.search(r'(?:/|\b)(diagnostic-config\.js|diagnostic\.js|catalog\.js|player\.js)(?:[?\s:("\]]|$)',line)
                        if resource:metadata['resource']={'diagnostic-config.js':'config','diagnostic.js':'bootstrap','catalog.js':'catalog','player.js':'runtime'}[resource[1]]
                        number=re.search(r'CONSOLE\((\d{1,7})\)',line)
                        if number:metadata['line']=int(number[1])
                        if code=='script-syntax':
                            metadata['syntax']=('unexpected-token' if 'unexpected token' in lowered else 'invalid-token' if 'invalid or unexpected' in lowered else
                                'redeclaration' if 'already been declared' in lowered else 'unterminated' if 'unterminated' in lowered else 'other')
                        network.append(metadata)
        except FileNotFoundError:pass
        except PermissionError:entry['state']='permission-denied'
        except (OSError,ValueError):entry['state']='unreadable'
        result['reads'].append(entry)
    for (run,build),events in list(groups.items())[-4:]:
        by_seq={e['seq']:e for e in events}
        result['runs'].append(dict(schema=SCHEMA,run=run,build=build,events=[by_seq[n] for n in sorted(by_seq)[-64:]]))
    result['runs']=bounded_runs(result['runs']);result['network']=network[-24:];result['engine']=engine[-16:]
    return result
