"""DAS delegation orchestration. GCA alone decides hardware admission/restoration."""
from __future__ import annotations
import base64
import copy
import hashlib
import hmac
import threading
import time
from das.core.catalog import ScreensaverError, file_sha256
from das.studio.presentation import ready_games
from das.core.media import _decoder_environment
from das.core.process_guard import capture
from .client import BrokerClient
from .protocol import BrokerError, identifier, digest
from .collection import compile_pages, compile_batches, batch_identity, fingerprint, index_rgb, presentation, transfer_estimate_ms, preparation_spec
from .power import POWER_POLICY,POWER_BUDGET_PPM
from .alignment import calibration_key, correction, saved_calibrations, reference, MAX_CALIBRATIONS
from .timing import admits, SYNC_MAX_BYTES, MODEL
from .framing import framing_filter

DEFAULTS=dict(configured=False,enabled=False,mode='sync',transition='fade',page_seconds=24,framing='square')
TERMINAL={'released','expired','preempted','rejected','revoking'}
NORMAL_RELEASE_REASONS={'PLAYER_ENDED','USER_DISABLED','CLIENT_STOPPING'}
PLAYER_HEARTBEAT_TIMEOUT=8.0
PLAYER_END_REASONS={'player-ended','visibility-hidden','unloading','frozen','destroyed',
    'manual-pause','catalog-replaced','coordinated-ended','broker-refused','transport-lost','lease-expired'}

class Delegation:
    def __init__(self,service,installer,broker=None):
        self.service=service;self.store=service.catalog;self.installer=installer;self.broker=broker or BrokerClient()
        self.lock=threading.RLock();self.player_lock=threading.Lock();self.closed=False;self.thread=None
        self.cancelled=threading.Event();self.session=None;self.phase='idle';self.reason='';self.compatible=False
        self.controller_state={};self.hardware='absent';self.detected=False;self.retry=0;self.seen=set();self.epoch=0;self.events=[];self.last_transfer='not-started';self.last_player=0
        self.discovery_at=None;self.discovery_state=None;self.discovery_lock=threading.Lock()
        self.recovery_thread=None;self.recovery_stop=threading.Event();self.registration_lock=threading.Lock()
        self.watchdog_thread=None;self.watchdog_stop=threading.Event()
        self.return_thread=None;self.return_stop=threading.Event()
        self.opening_thread=None;self.opening_stop=threading.Event()
        self.registered_boot=None;self.validation='unknown';self.last_operation=None
        self.last_evidence={}
        self.alignment='not-requested';self.restore_state='not-needed';self.first_player=False;self.opening=None
        saved=self.store.data.get('jsaux',{})
        self.options=dict(DEFAULTS)
        self.calibrations=saved_calibrations(self.store.data.get('jsaux_alignment',{}))
        self.last_alignment={}
        if isinstance(saved,dict):
            try:self.options.update(self._valid(saved,internal=True))
            except BrokerError:pass
        self.receipt=copy.deepcopy(self.store.data.get('jsaux_collection',{}))
        if not isinstance(self.receipt,dict):self.receipt={}
        self.player_end_reason=''
        self.started_at=int(time.time())
        self.preparation_stage='idle'
        self.player_relay=None
        self.preparation_error='';self.controller_status_error='';self.preparation_percent=0
        self.record('runtime-started')

    def _valid(self,patch,internal=False):
        allowed=set(DEFAULTS) if internal else set(DEFAULTS)-{'configured'}
        if not isinstance(patch,dict) or set(patch)-allowed:raise BrokerError('INVALID_REQUEST')
        for k,v in patch.items():
            if k in {'enabled','configured'} and type(v) is not bool:raise BrokerError('INVALID_REQUEST')
            if k=='mode' and v not in {'sync','async'}:raise BrokerError('INVALID_REQUEST')
            if k=='transition' and v not in {'fade','wipe','slide','dissolve','none'}:raise BrokerError('INVALID_REQUEST')
            if k=='framing' and v not in ('square','fill'):raise BrokerError('INVALID_REQUEST')
            if k=='page_seconds' and (type(v) is not int or not 2<=v<=180):raise BrokerError('INVALID_REQUEST')
        return dict(patch)

    def games(self):
        # Same stable insertion order as the installed TV player.
        return ready_games(self.store)

    def _identity_policy(self):
        return dict(mode_policy=self.receipt.get('mode_policy')==64,batched=bool(self.receipt.get('batches')))

    def effective_mode(self):
        # Requested settings survive automatic capacity fallback. Legacy lots
        # are always independent, even without this explicit receipt field.
        if self.receipt.get('batches'):return 'async'
        return self.receipt.get('effective_mode',self.options['mode'])

    def identity(self):
        source=fingerprint(self.games(),self.options,self.store.options(),**self._identity_policy())
        rows=self.receipt.get('batches')
        if isinstance(rows,list) and rows and self.receipt.get('source_identity')==source:
            try:return batch_identity(source,rows)
            except (KeyError,TypeError,ValueError):return source
        return source

    def sync_wait_ms(self):
        # Before discovery, keep a recovered export's fixed start budget. The
        # actual broker is checked again at acquisition; never extend a gate.
        hello=getattr(self.broker,'hello',None) or {}
        value=hello.get('limits',{}).get('sync_wait_ms',self.receipt.get('sync_wait_ms',2500))
        return value if type(value) is int and value in (2500,15000) else 2500

    def prepared_sync_wait_ms(self):
        value=self.receipt.get('sync_wait_ms',2500)
        return value if type(value) is int and value in (2500,15000) else 2500

    def readiness(self):
        """Metadata only. Report why a GIF cannot be used, without exposing its sources."""
        current=self.identity();saved=self.receipt.get('collection_id')
        spec=self.receipt.get('input_spec');changed=[]
        if isinstance(spec,dict):
            now=preparation_spec(self.games(),self.options,self.store.options(),**self._identity_policy())
            changed=[key for key in ('version','profile','games','playback','framing','power','startup_target_bytes','maximum_bytes','requested_mode') if spec.get(key)!=now.get(key)]
        power_current=(self.receipt.get('power_policy')==POWER_POLICY and
            type(self.receipt.get('peak_load_ppm')) is int and 0<=self.receipt['peak_load_ppm']<=POWER_BUDGET_PPM)
        reason=('NOT_PREPARED' if not saved else 'PREPARATION_STALE' if saved!=current else
                'PREPARATION_POWER_REQUIRED' if not power_current else
                'PREPARED_FILE_MISSING' if not self.receipt.get('path') else
                'REGISTRATION_MISSING' if not self.receipt.get('content_id') else '')
        return dict(ready=not reason,reason=reason,changed=changed,
                    identity_matches=bool(saved and saved==current),
                    file_referenced=bool(self.receipt.get('path')),
                    registered=bool(self.receipt.get('content_id')),
                    input_schema=self.receipt.get('input_spec',{}).get('version') if isinstance(spec,dict) else None,
                    power_upgrade_required=bool(saved and not power_current))

    def status(self):
        with self.lock:
            readiness=self.readiness();ready=readiness['ready']
            power={key:self.receipt.get(key) if type(self.receipt.get(key)) is int and 0<=self.receipt[key]<=1000000 else None
                   for key in ('peak_load_ppm','source_peak_load_ppm','power_limited_frames')}
            return {**self.options,'compatible':self.compatible,'detected':self.detected,'hardware':self.hardware,
                    'calibration':self.calibration_status(),
                    'connection_id':hashlib.sha256(repr((getattr(self.broker,'boot',None),(self.discovery_state or {}).get('ownership',{}).get('device_key'),self.detected,self.compatible)).encode()).hexdigest()[:16],
                    'phase':self.phase if self.busy() else self.controller_state.get('phase',self.phase),'worker_active':self.busy(),'reason':self.reason or self.controller_state.get('batch_error') or self.controller_state.get('reason',''),'retry_after_ms':self.retry,
                    'preparation_error':self.preparation_error,'controller_status_error':self.controller_status_error,
                    'connection':self.broker.diagnostic_snapshot() if callable(getattr(self.broker,'diagnostic_snapshot',None)) else None,
                    'installed':bool(ready and self.options['enabled'] and self.installer.cached.get('installed') and getattr(self.installer,'jsaux_export',None)==self.export_descriptor(ready)),
                    'relay_enabled':bool(self.options['enabled'] and self.installer.cached.get('installed') and self.installer.jsaux_export),
                    'controller':(self.installer.jsaux_export or {}).get('controller','DAS'),
                    'relay_transport':(self.installer.jsaux_export or {}).get('relay',{}).get('kind','legacy'),
                    'player_relay':self.player_relay.snapshot() if self.player_relay else None,
                    'validation_state':self.validation,'alignment_state':self.alignment,'restore_state':self.controller_state.get('restore_state',self.restore_state),
                    'first_player_observed':self.controller_state.get('first_player',self.first_player),'steam_selection':'unknown',
                    'last_transfer':self.controller_state.get('last_transfer',self.last_transfer),'events':copy.deepcopy(self.events[-20:]),
                    'prepared':dict(**readiness,bytes=self.receipt.get('bytes',0),percent=self.preparation_percent if self.busy() else self.receipt.get('percent',0),
                        pages=self.receipt.get('pages',0),frames=self.receipt.get('frames',0),orientation=0,
                        batch_count=(len(self.receipt['batches']) if isinstance(self.receipt.get('batches'),list) else 0) or 1,total_bytes=self.receipt.get('total_bytes',self.receipt.get('bytes',0)),
                        automatic_independent=bool(self.receipt.get('automatic_independent')),effective_mode=self.effective_mode(),
                        estimate_ms=transfer_estimate_ms(self.receipt.get('bytes',0)),
                        timing_model=MODEL,sync_max_bytes=SYNC_MAX_BYTES,
                        sync_wait_ms=self.prepared_sync_wait_ms(),transition_steps=self.receipt.get('transition_steps',8),
                        transition_optimized=bool(self.receipt.get('transition_optimized')),
                        power_policy=self.receipt.get('power_policy') if self.receipt.get('power_policy')==POWER_POLICY else None,
                        power_budget_ppm=POWER_BUDGET_PPM,
                        **power,
                        sync_admissible=bool(ready and self.effective_mode()=='sync' and self.prepared_sync_wait_ms()<=self.sync_wait_ms()
                            and admits(self.receipt.get('bytes',0),self.prepared_sync_wait_ms())))}

    def export_descriptor(self,ready):
        if not self.options['enabled'] or not ready:return None
        value=dict(enabled=True,mode=self.effective_mode(),collection_id=self.receipt['collection_id'],
                    sync_wait_ms=self.prepared_sync_wait_ms())
        installed=getattr(self.installer,'jsaux_export',None) or {}
        if installed.get('controller')=='GabeCubeAura' and installed.get('collection_id')==value['collection_id'] and installed.get('mode')==value['mode']:
            value.update(controller='GabeCubeAura',relay=installed['relay'])
        elif self.player_relay:value['relay']=self.player_relay.descriptor()
        return value

    def publish_installed_player(self,descriptor,token):
        """Studio-only registration; the installed player later talks directly to GCA."""
        self.refresh()
        if not descriptor or not (getattr(self.broker,'hello',None) or {}).get('capabilities',{}).get('autonomous_player'):return descriptor
        rows=self.receipt.get('batches',[])
        if rows:
            if not self.broker.hello.get('capabilities',{}).get('autonomous_batches'):raise BrokerError('BATCHES_REQUIRE_GCA_UPDATE')
            try:
                for index,row in enumerate(rows):
                    self.checkpoint();path=self.store.managed(row['path'],True)
                    if file_sha256(path)!=row['sha256']:raise BrokerError('CONTENT_INVALID')
                    result=self.broker.register(path,descriptor['collection_id']);validation=result.get('validation_id');deadline=time.monotonic()+12
                    while not result.get('content_id'):
                        if result.get('state')=='rejected':raise BrokerError(result.get('reason') or 'CONTENT_INVALID')
                        if time.monotonic()>=deadline:raise BrokerError('VALIDATION_LIMIT')
                        self.checkpoint();self.cancelled.wait(.05)
                        result=self.broker.operation(validation_id=result.get('validation_id') or validation)
                        if result.get('validation_id'):validation=result['validation_id']
                    reply=self.broker.request('publish_player_batch',dict(content_id=result['content_id'],collection_id=descriptor['collection_id'],
                        token=token,alignment_ms=0,index=index,count=len(rows)))
                    if reply.get('next_index')!=index+1 or bool(reply.get('published'))!=(index==len(rows)-1):raise BrokerError('PROTOCOL_INVALID')
            except BaseException:
                try:self.broker.request('remove_player',dict(token=token))
                except (BrokerError,OSError):pass
                raise
        else:
            content_id=self._registered(time.monotonic()+10)
            reply=self.broker.request('publish_player',dict(content_id=content_id,collection_id=descriptor['collection_id'],token=token,
                mode=descriptor['mode'],alignment_ms=self.calibration_status()['offset_ms']))
        relay=reply.get('relay',{})
        if reply.get('controller')!='GabeCubeAura' or relay.get('kind')!='http-loopback-v1' or relay.get('url')!='http://127.0.0.1:37680/jsaux/v1/player':raise BrokerError('PROTOCOL_INVALID')
        return {**descriptor,'controller':'GabeCubeAura','relay':relay}

    def remove_installed_player(self,token):
        if token and (getattr(self.broker,'hello',None) or {}).get('capabilities',{}).get('autonomous_player'):
            self.broker.request('remove_player',dict(token=token))

    def calibration_identity(self):
        state=self.discovery_state or {}
        device=(state.get('ownership') or {}).get('device_key')
        return calibration_key(device,self.identity()) if self.detected and self.compatible else None

    def calibration_status(self):
        key=self.calibration_identity()
        return dict(available=key is not None,offset_ms=self.calibrations.get(key,0),
                    saved=key in self.calibrations if key else False,
                    scope='connection-and-collection',last=dict(self.last_alignment))

    def record(self,event,reason='',**fields):
        safe={k:v for k,v in fields.items() if k in {'ready','bytes','pages','frames','elapsed_ms','included','identity_matches','registered','file_referenced','observation_age_ms','activation_closed','active','peak_load_ppm','source_peak_load_ppm','power_limited_frames','power_budget_ppm'} and type(v) in (bool,int)}
        if fields.get('stage') in {'source','decode','compile','save','register','complete'}:safe['stage']=fields['stage']
        if fields.get('exception') in {'OSError','ValueError','TypeError','KeyError','AttributeError','TimeoutError','BrokerError','ScreensaverError'}:safe['exception']=fields['exception']
        self.events=(self.events+[dict(at=int(time.time()),event=event,reason=reason,**safe)])[-40:]

    def _remember_operation(self,value,operation_id):
        self.last_evidence=dict(correlation_id=hashlib.sha256(operation_id.encode()).hexdigest()[:16],captured_at=int(time.time()),
            **{key:value.get(key) for key in ('lease_state','transfer_state','alignment_state','restore_state','reason','retry_after_ms')},
            event_ages_ms=dict(value.get('event_ages_ms',{})),optical_playback='not-measured')

    def diagnostic_snapshot(self,relay=None):
        """Complete local JSAUX evidence allowlist; no media/key/path."""
        state=self.status();discovery=self.discovery_state or {}
        from .diagnostics import relay_snapshot
        installed=getattr(self.installer,'jsaux_export',None) or {}
        return dict(schema='das-jsaux-diagnostic-v1',diagnostic_revision=7,at=int(time.time()),activity=self.activity(),
            controller=(self.installer.jsaux_export or {}).get('controller','DAS'),controller_state=dict(self.controller_state),
            player_end_reason=self.player_end_reason,heartbeat=self._heartbeat_diagnostic(),
            runtime_started_at=self.started_at,relay=relay_snapshot(relay),
            player_relay=self.player_relay.snapshot() if self.player_relay else dict(kind='legacy',running=False),
            player_debug=self.player_relay.debug_snapshot() if self.player_relay else dict(browser_evidence='not-configured'),
            settings={k:state[k] for k in ('enabled','mode','transition','page_seconds')},
            calibration=state['calibration'],
            stages=dict(prepared=state['prepared']['ready'],included_in_steam=state['installed'],
                installed_listener=state['relay_enabled'],steam_player_observed=state['first_player_observed'],
                usb_receipt=state['last_transfer'],alignment=self.alignment,restoration=state['restore_state']),
            prepared=state['prepared'],broker=dict(compatible=self.compatible,detected=self.detected,
                hardware=self.hardware,connection=state['connection'],
                observation_cache_age_ms=None if self.discovery_at is None else round((time.monotonic()-self.discovery_at)*1000),
                policy=dict(discovery.get('policy',{})),
                steam={k:discovery.get('steam',{}).get(k) for k in ('observed','observation_age_ms','activation_closed')}),
            installation=dict(export_exists=bool(self.installer.cached.get('installed')),
                player_current=bool(self.installer.cached.get('player_current')),
                needs_update=bool(self.installer.status().get('needs_update')),
                descriptor_present=bool(installed),mode=installed.get('mode') if installed.get('mode') in {'sync','async'} else None,
                collection_matches=bool(installed.get('collection_id') and installed.get('collection_id')==self.identity()),
                prepared_collection_matches=bool(installed.get('collection_id') and installed.get('collection_id')==self.receipt.get('collection_id')),
                relay_current=bool(installed.get('controller')=='GabeCubeAura' and installed.get('relay',{}).get('url')=='http://127.0.0.1:37680/jsaux/v1/player' or self.player_relay and installed.get('relay')==self.player_relay.descriptor()),
                expected_player_build=getattr(self.installer,'expected',{}).get('player.js','')[:12],
                sync_wait_ms=installed.get('sync_wait_ms') if installed.get('sync_wait_ms') in (2500,15000) else None),
            phase=self.phase,reason=self.reason,preparation_stage=self.preparation_stage,preparation_error=self.preparation_error,controller_status_error=self.controller_status_error,retry_after_ms=self.retry,
            last_operation=dict(self.last_evidence),events=copy.deepcopy(self.events[-24:]),
            privacy=dict(api_keys=False,authorization_tokens=False,media=False,personal_paths=False))

    def after_tv_prepare(self):
        if self.detected and self.compatible and self.options['enabled'] and self.games():
            if self.readiness()['ready'] and self.reason not in {'CONTENT_INVALID','PREPARATION_POWER_REQUIRED','PREPARED_FILE_MISSING'} and (self.effective_mode()!='sync' or self.status()['prepared']['sync_admissible']):return
            try:self.prepare()
            except BrokerError as error:self.reason=error.code;self.record('preparation-failed',error.code)

    def purge(self):
        if self.busy():raise BrokerError('PREPARATION_BUSY')
        installed=getattr(self.installer,'jsaux_export',None) or {}
        if installed.get('controller')=='GabeCubeAura':self.remove_installed_player(self.installer.token)
        self.stop('user-disabled')
        directory=self.store.managed('jsaux');removed=0;removed_bytes=0
        if directory.is_dir():
            for path in directory.iterdir():
                if len(path.stem)==64 and all(c in '0123456789abcdef' for c in path.stem) and path.suffix=='.gif' and path.is_file() and not path.is_symlink():
                    removed_bytes+=path.stat().st_size;path.unlink();removed+=1
        with self.store.lock:
            self.store.data.pop('jsaux_collection',None);self.store.save()
        self.receipt={};self.reason='';self.phase='idle';self.events=[];self.last_transfer='not-started'
        return dict(files=removed,bytes=removed_bytes)

    def busy(self):return bool(self.thread and self.thread.is_alive())

    def display_busy(self):
        """A retained terminal session is evidence, not an active display lease."""
        return bool(self.opening or self.session and not self.session.get('terminal')
                    or self.phase in {'acquiring','waiting','transferring','active','restoring','releasing'}
                    or self.last_operation and self.restore_state in {'pending','deferred'})

    def activity(self):
        with self.lock:
            return dict(worker_active=self.busy(),phase=self.phase,
                session_present=self.session is not None,terminal=bool(self.session and self.session.get('terminal')),
                heartbeat_age_ms=min(86400000,max(0,round((time.monotonic()-self.last_player)*1000))) if self.session else None,
                heartbeat_timeout_ms=round(PLAYER_HEARTBEAT_TIMEOUT*1000),display_busy=self.display_busy(),
                watchdog_active=bool(self.watchdog_thread and self.watchdog_thread.is_alive()),
                restoration_pending=bool(self.last_operation and self.restore_state in {'pending','deferred'}))

    def expire_session(self,expected=None):
        """Expire the matching silent player only; never acquire or upload."""
        with self.lock:
            session=self.session;last=self.last_player
            age=time.monotonic()-last
            if not session or expected is not None and session is not expected or age<PLAYER_HEARTBEAT_TIMEOUT:return False
        return self.stop('player-ended',expected_session=session,expected_last_player=last)

    def _watch_session(self,session):
        with self.lock:
            if self.closed or self.session is not session:return
            self.watchdog_stop.set();stop=threading.Event();self.watchdog_stop=stop
            def watch():
                while not stop.wait(min(1,PLAYER_HEARTBEAT_TIMEOUT/4)):
                    with self.lock:
                        if self.closed or self.session is not session:return
                    if self.expire_session(session):return
            self.watchdog_thread=threading.Thread(target=watch,name='das-player-lease-watchdog',daemon=True)
            self.watchdog_thread.start()

    def _save_options(self):
        with self.store.lock:
            self.store.data['jsaux']=dict(self.options)
            self.store.save()

    def configure(self,patch):
        if not isinstance(patch,dict):raise BrokerError('INVALID_REQUEST')
        patch=dict(patch)
        if 'alignment_ms' in patch:
            if len(patch)!=1 or not correction(patch['alignment_ms']):raise BrokerError('INVALID_REQUEST')
            if self.busy():raise BrokerError('PREPARATION_BUSY')
            key=self.calibration_identity()
            if key is None:raise BrokerError('DEVICE_ABSENT')
            # Configure after leaving the screensaver. Never issue an upload or
            # revoke a live display merely to adjust a calibration slider.
            if self.session and not self.session.get('terminal'):raise BrokerError('PREPARATION_BUSY')
            installed=getattr(self.installer,'jsaux_export',None) or {}
            if installed.get('controller')=='GabeCubeAura':
                self.broker.request('calibrate_player',dict(token=self.installer.token,alignment_ms=patch['alignment_ms']))
            with self.lock:
                self.calibrations.pop(key,None);self.calibrations[key]=patch['alignment_ms']
                while len(self.calibrations)>MAX_CALIBRATIONS:self.calibrations.pop(next(iter(self.calibrations)))
                with self.store.lock:
                    self.store.data['jsaux_alignment']=dict(self.calibrations);self.store.save()
                self.record('alignment-saved',elapsed_ms=abs(patch['alignment_ms']))
            return self.status()
        valid=self._valid(patch)
        # Native controls may report their already selected value again. A
        # no-op must not stop playback, clear an error or dirty the export.
        if self.options['configured'] and all(self.options[k]==v for k,v in valid.items()):
            return self.status()
        if self.busy():raise BrokerError('PREPARATION_BUSY')
        installed=getattr(self.installer,'jsaux_export',None) or {}
        if installed.get('controller')=='GabeCubeAura' and valid.get('enabled') is False:self.remove_installed_player(self.installer.token)
        self.stop('user-disabled')
        with self.lock:
            self.options.update(valid,configured=True);self._save_options();self.preparation_error='';self.reason='';self.phase='idle'
            readiness=self.readiness()
            self.record('settings-changed',readiness['reason'],ready=readiness['ready'])
        if self.player_relay:
            if not self.options['enabled']:self.player_relay.close()
            elif (self.installer.jsaux_export or {}).get('relay')==self.player_relay.descriptor():self.player_relay.start()
        return self.status()

    def installation_blocker(self):
        # TV-only remains independent when no compatible panel is available.
        # Never silently drop a requested, connected faceplate from a new export.
        if self.options['enabled'] and self.detected and self.compatible:
            status=self.status()
            if not status['prepared']['ready']:return 'JSAUX_PREPARATION_REQUIRED'
            if self.effective_mode()=='sync' and not status['prepared']['sync_admissible']:return 'JSAUX_SYNC_WINDOW'
        return ''

    def installation_event(self,event):
        state=self.status();self.record(event,state['prepared']['reason'],
            ready=state['prepared']['ready'],included=state['installed'])

    def refresh(self,max_age=0):
        state = self._discover(max_age)
        self.poll_return()
        return state

    def _discover(self,max_age=0):
        # A dedicated I/O coordinator coalesces reads without holding state
        # while the broker is unavailable. Stop remains immediately responsive.
        with self.discovery_lock:
            with self.lock:
                epoch=self.epoch
                if self.closed:return None
                if self.discovery_at is not None and time.monotonic()-self.discovery_at<max_age:
                    return copy.deepcopy(self.discovery_state)
            try:
                state=self.broker.discover(True)
            except BrokerError as error:
                with self.lock:
                    if epoch!=self.epoch or self.closed:return None
                    self.discovery_at=time.monotonic()
                    self.compatible=False;self.detected=False;self.hardware='unknown';self.discovery_state=None;self.controller_state={}
                    self.reason=error.code;self.retry=error.retry_after_ms
                return None
            # The primary status confirms hardware independently of an optional
            # installed-player read. A failure of the latter is not absence.
            installed=getattr(self.installer,'jsaux_export',None) or {}
            controller_state={};controller_error=''
            if installed.get('controller')=='GabeCubeAura' and (getattr(self.broker,'hello',None) or {}).get('capabilities',{}).get('autonomous_player'):
                try:controller_state=self.broker.request('player_status',dict(token=self.installer.token))
                except BrokerError as error:controller_error=error.code
            with self.lock:
                if epoch!=self.epoch or self.closed:return None
                self.controller_state=controller_state;self.controller_status_error=controller_error
                self.discovery_at=time.monotonic()
                self.compatible=True;self.hardware=state['hardware'];self.retry=0
                self.detected=self.hardware!='absent'
                self.reason=self.preparation_error or controller_error or state['policy'].get('reason') or ('DEVICE_ABSENT' if self.hardware=='absent' else '')
                self.discovery_state=copy.deepcopy(state)
                return state

    def recover(self):
        """Finite metadata/cache recovery. No serial, media scan or encoder."""
        with self.lock:
            if self.closed or self.recovery_thread and self.recovery_thread.is_alive():return
            self.recovery_stop.clear()
            def work():
                for delay in (0,1,2,4,10):
                    if self.recovery_stop.wait(delay) or self.closed:return
                    if self.refresh():
                        try:
                            self.poll_return()
                            if self.options['enabled'] and self.receipt.get('path') and self.receipt.get('collection_id')==self.identity():
                                self._registered(time.monotonic()+10)
                            if self.last_operation and self.restore_state in {'pending','deferred'}:self.follow_return()
                            return
                        except (BrokerError,ScreensaverError,OSError):pass
            self.recovery_thread=threading.Thread(target=work,name='das-jsaux-recovery',daemon=True)
            self.recovery_thread.start()

    def _registered(self,deadline,epoch=None,force=False):
        receipt=None
        def check():
            if self.closed or self.recovery_stop.is_set() or epoch is not None and epoch!=self.epoch:
                raise BrokerError('STALE_GENERATION')
            if self.busy() and self.cancelled.is_set():raise BrokerError('PREPARATION_CANCELLED')
            if receipt is not None and self.receipt is not receipt:raise BrokerError('STALE_GENERATION')
            if time.monotonic()>=deadline:raise BrokerError('VALIDATION_LIMIT')
        if not self.registration_lock.acquire(timeout=max(0,deadline-time.monotonic())):raise BrokerError('VALIDATION_LIMIT')
        try:
            receipt=self.receipt
            check();boot=getattr(self.broker,'boot',None)
            if not force and self.registered_boot is not None and self.registered_boot==boot and self.receipt.get('content_id'):
                return self.receipt['content_id']
            path=self.store.managed(receipt['path'],True);self.validation='validating'
            while True:
                check()
                try:content=self.broker.register(path,receipt['collection_id']);break
                except BrokerError as error:
                    if error.code!='RATE_LIMITED':raise
                    self.retry=error.retry_after_ms
                    self.recovery_stop.wait(min(.25,max(.05,error.retry_after_ms/1000)))
            if not content.get('content_id'):
                validation=identifier(content.get('validation_id'))
                while True:
                    check();content=self.broker.operation(validation_id=validation)
                    if content.get('content_id'):break
                    if content.get('state')=='rejected':raise BrokerError(content.get('reason') or 'CONTENT_INVALID')
                    self.recovery_stop.wait(.05)
            check();receipt['content_id']=identifier(content['content_id']);self.registered_boot=getattr(self.broker,'boot',None) or 'test-client'
            self.validation='ready';self.retry=0
            return self.receipt['content_id']
        except (BrokerError,ScreensaverError,OSError):
            self.validation='pending';raise
        finally:self.registration_lock.release()

    def prepare(self):
        self.expire_session()
        with self.lock:
            if self.closed:raise BrokerError('STALE_GENERATION')
            if getattr(self,'_preparing_intent',None) or self.busy() or self.service._busy() or self.session:raise BrokerError('PREPARATION_BUSY')
            epoch=self.epoch;intent=object();self._preparing_intent=intent
        try:
            # Lock order is discovery_lock -> state lock. Never wait for broker
            # I/O while holding state, including this admission path.
            state=self.refresh()
            with self.lock:
                if self.closed or epoch!=self.epoch:raise BrokerError('STALE_GENERATION')
                if self.busy() or self.service._busy() or self.session or self.opening:raise BrokerError('PREPARATION_BUSY')
                if self.service._playing():raise BrokerError('GAME_RUNNING')
                if not self.options['enabled']:raise BrokerError('FACEPLATE_DISABLED')
                if not state or not self.detected:return self.status()
                if not self.games():raise BrokerError('CONTENT_MISSING')
                if len(self.games())>2000:raise BrokerError('CONTENT_TOO_LARGE')
                self.service.cancelled.clear()
                self.cancelled.clear();self.phase='preparing';self.preparation_error='';self.preparation_percent=0;self.reason=''
                self.last_transfer='not-started';self.first_player=False;self.last_evidence={};self.alignment='not-requested'
                self.record('preparation-started')
                self._preparation_epoch=epoch
                self.thread=threading.Thread(target=self._prepare,name='das-identities-prepare',daemon=True);self.thread.start()
        finally:
            with self.lock:
                if self._preparing_intent is intent:self._preparing_intent=None
        return self.status()

    def checkpoint(self):
        if self.closed or self.cancelled.is_set() or self.service._playing() or (threading.current_thread() is self.thread and getattr(self,'_preparation_epoch',self.epoch)!=self.epoch):raise BrokerError('PREPARATION_CANCELLED')

    def _identity_page(self,game,options,cached_power_repair):
        from das.studio.service import CANDIDATE_FAILURES
        number=game['appid'];pending=game.get('panel_pending');media=game.get('media',{});runner=self.service.compiler.runner
        def existing(role):
            relative=media.get(role)
            if relative:yield None,relative,game.get('sha256',{}).get(role)
        def candidates():
            if not pending:yield from existing('panel_source')
            if cached_power_repair and not pending and not media.get('panel_source'):
                yield from existing('cover');yield from existing('thumbnail')
            for asset in self.service._asset_pool(number,'panel',game.get('panel_asset') if pending else None):yield asset,None,None
            yield from existing('cover');yield from existing('thumbnail');yield from existing('tv')
        seen=set();last=None
        for asset,relative,expected in candidates():
            self.checkpoint();self.preparation_stage='source'
            evidence=asset or dict(id=0,_local=relative)
            self.service._active_asset={**evidence,'role':'panel'}
            try:
                source=self.service._artwork_source(asset) if asset else self.store.managed(relative,True)
                if str(source) in seen:continue
                seen.add(str(source));sha=file_sha256(source)
                if isinstance(expected,str) and len(expected)==64 and sha!=expected:raise BrokerError('CONTENT_INVALID')
                self.preparation_stage='decode'
                raw=capture([runner.ffmpeg,'-v','error','-xerror','-nostdin','-threads','2','-filter_threads','2',
                    '-protocol_whitelist','file,pipe','-i',str(source),'-vf',framing_filter(options['framing'],game.get('faceplate_crop')),
                    '-frames:v','1','-an','-sn','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
                    environment=_decoder_environment(runner.library_path),timeout=15,maximum=10368,
                    checkpoint=self.checkpoint,lease_fd=self.service.compiler.lease_fd)
                page=index_rgb(raw);self.checkpoint()
                current=self.store.get(number);current_media=dict(current.get('media',{}));current_sha=dict(current.get('sha256',{}))
                relative=str(source.relative_to(self.store.root));current_media['panel_source']=relative;current_sha['panel_source']=sha
                patch=dict(media=current_media,sha256=current_sha,panel_pending=False)
                if asset:patch.update(panel_asset=asset,panel_manual=bool(pending and asset==game.get('panel_asset')))
                elif relative!=media.get('panel_source'):patch.update(panel_asset=None,panel_manual=False)
                self.store.update(number,patch);game.update(patch)
                return page,copy.deepcopy(game)
            except (ScreensaverError,BrokerError) as error:
                if error.code not in CANDIDATE_FAILURES|{'CONTENT_INVALID','missing_media'}:raise
                last=error;self.service._reject_asset(number,'panel',evidence,error)
                self.record('panel-candidate-rejected',error.code)
        raise last or BrokerError('CONTENT_MISSING')

    def _prepare(self):
        epoch=getattr(self,'_preparation_epoch',self.epoch)
        previous_ref=self.receipt;previous=copy.deepcopy(self.receipt);receipt=None;created=[];committed=False
        try:
            with self.service.lease():
                pages=[];decoded_games=[];games=self.games();options=dict(self.options);tv=self.store.options()
                cached_power_repair=bool(self.receipt.get('collection_id') and self.receipt.get('power_policy')!=POWER_POLICY)
                maximum=min(196608,self.broker.hello['limits']['max_content_bytes'])
                for n,game in enumerate(games):
                    page,decoded=self._identity_page(game,options,cached_power_repair)
                    pages.append(page);decoded_games.append(decoded);self.preparation_percent=round((n+1)*75/len(games))
                self.checkpoint()
                origin=fingerprint(decoded_games,options,tv)
                def current():return options==self.options and origin==fingerprint(self.games(),self.options,self.store.options())
                if not current():raise BrokerError('STALE_GENERATION')
                effective_mode=options['mode'];automatic=False;batched=False
                seconds=tv['scene_seconds'] if options['mode']=='sync' else options['page_seconds']
                self.preparation_stage='compile'
                try:
                    if len(pages)>120:raise BrokerError('CONTENT_TOO_LARGE')
                    single=compile_pages(pages,seconds,options['transition'],maximum,self.checkpoint,prefer_small=True)
                    compiled=[single]
                except BrokerError as error:
                    if error.code not in {'CONTENT_TOO_LARGE','JSAUX_SYNC_WINDOW'}:raise
                    if not self.broker.hello.get('capabilities',{}).get('autonomous_batches'):raise BrokerError('BATCHES_REQUIRE_GCA_UPDATE')
                    effective_mode='async';automatic=options['mode']=='sync';batched=True
                    # Independent lots have a stable shuffled order, preserving
                    # every selected identity without recoding them on wake.
                    import random
                    random.Random(origin).shuffle(pages)
                    compiled=compile_batches(pages,options['page_seconds'],options['transition'],maximum,self.checkpoint)
                if not current():raise BrokerError('STALE_GENERATION')
                source_identity=fingerprint(decoded_games,options,tv,mode_policy=True,batched=batched)
                input_spec=preparation_spec(decoded_games,options,tv,mode_policy=True,batched=batched)
                directory=self.store.managed('jsaux');directory.mkdir(exist_ok=True,mode=0o700)
                rows=[];paths=[]
                for data,details in compiled:
                    self.checkpoint()
                    sha=hashlib.sha256(data).hexdigest();path=directory/(sha+'.gif')
                    if path.exists():
                        if path.is_symlink() or path.read_bytes()!=data:raise BrokerError('CONTENT_INVALID')
                    else:
                        self.service._admit(len(data))
                        with path.open('xb') as stream:
                            created.append(path);stream.write(data)
                        path.chmod(0o600)
                    paths.append(path)
                    rows.append(dict(path=str(path.relative_to(self.store.root)),sha256=sha,bytes=len(data),pages=details['pages'],duration_cs=details['duration_cs']))
                identity=batch_identity(source_identity,rows) if batched else source_identity
                details=dict(compiled[0][1])
                details.update(pages=len(pages),frames=sum(d['frames'] for _,d in compiled),
                    peak_load_ppm=max(d['peak_load_ppm'] for _,d in compiled),
                    source_peak_load_ppm=max(d['source_peak_load_ppm'] for _,d in compiled),
                    power_limited_frames=sum(d['power_limited_frames'] for _,d in compiled))
                self.record('power-checked',**{key:details[key] for key in ('peak_load_ppm','source_peak_load_ppm','power_limited_frames','power_budget_ppm')})
                receipt=dict(details,collection_id=identity,path=rows[0]['path'],percent=90,sync_wait_ms=self.sync_wait_ms(),
                    presentation=presentation(self.games(),tv),input_spec=input_spec,orientation=0,
                    total_bytes=sum(row['bytes'] for row in rows),automatic_independent=automatic,
                    mode_policy=64,requested_mode=options['mode'],effective_mode=effective_mode)
                if batched:receipt.update(batches=rows,source_identity=source_identity)
                with self.lock:
                    self.checkpoint();self.phase='registering';self.preparation_percent=90;self.receipt=receipt
                    self.preparation_stage='register';self.registered_boot=None
                content_id=self._registered(time.monotonic()+12,epoch=epoch)
                if not current():raise BrokerError('STALE_GENERATION')
                receipt.update(content_id=content_id,percent=100)
                with self.lock:
                    self.checkpoint()
                    with self.store.lock:
                        before=copy.deepcopy(self.store.data)
                        self.store.data['jsaux_collection']=dict(receipt)
                        try:self.store.save()
                        except BaseException:self.store.data=before;raise
                    self.receipt=receipt;self.phase='idle';self.preparation_percent=100;self.preparation_error='';self.reason='';committed=True
                self.preparation_stage='complete'
                readiness=self.readiness()
                self.record('collection-registered',readiness['reason'],ready=readiness['ready'],bytes=receipt['total_bytes'],pages=receipt['pages'],frames=receipt['frames'])
                keep=set(paths)
                for old in directory.glob('*.gif'):
                    if old not in keep and not old.is_symlink() and len(old.stem)==64:old.unlink()
        except Exception as error:
            if not committed:
                for path in created:path.unlink(missing_ok=True)
            with self.lock:
                if self.receipt is previous_ref or receipt is not None and self.receipt is receipt:self.receipt=previous
                if epoch==self.epoch and not self.closed:
                    self.phase='idle';self.preparation_error=getattr(error,'code','PREPARATION_FAILED');self.reason=self.preparation_error
                    self.record('preparation-failed',self.reason,stage=self.preparation_stage,exception=type(error).__name__)

    def preview(self):
        if not self.status()['prepared']['ready']:raise BrokerError('CONTENT_MISSING')
        path=self.store.managed(self.receipt['path'],True)
        if path.stat().st_size>196608:raise BrokerError('CONTENT_TOO_LARGE')
        return dict(data_url='data:image/gif;base64,'+base64.b64encode(path.read_bytes()).decode(),width=64,height=54,bytes=path.stat().st_size)

    def _wait_return(self,stop,delay):
        return stop.wait(delay)

    def follow_return(self):
        """Follow exactly one retained receipt. No discovery or registration."""
        with self.lock:
            operation, epoch = self.last_operation, self.epoch
            if self.closed or not operation or self.restore_state not in {'pending','deferred'}:return
            if self.return_thread and self.return_thread.is_alive() and getattr(self,'_return_identity',None)==(epoch,operation):return
            self.return_stop.set();stop=threading.Event();self.return_stop=stop
            self._return_identity=(epoch,operation)
            def work():
                delay=0
                while not self._wait_return(stop,delay):
                    with self.lock:
                        if self.closed or epoch!=self.epoch or operation!=self.last_operation:return
                    self.poll_return()
                    with self.lock:
                        if operation!=self.last_operation:return
                    delay=min(10,1 if not delay else delay*2)
            self.return_thread=threading.Thread(target=work,name='das-return-receipt',daemon=True)
            self.return_thread.start()

    def poll_return(self):
        with self.lock:
            operation,epoch=self.last_operation,self.epoch
            if not operation or self.closed:return
        try:
            value=self.broker.operation(operation_id=operation)
            with self.lock:
                if operation!=self.last_operation or epoch!=self.epoch or self.closed:return
                self._remember_operation(value,operation)
                self.last_transfer=value.get('transfer_state',self.last_transfer)
                self.alignment=value.get('alignment_state',self.alignment)
                self.restore_state=value.get('restore_state',self.restore_state)
                self.retry=value.get('retry_after_ms',0);reason=value.get('reason') or ''
                self.reason=reason if isinstance(reason,str) and reason.isupper() and reason not in NORMAL_RELEASE_REASONS else ''
                if value.get('lease_state') in TERMINAL and self.restore_state not in {'pending','deferred'}:
                    self.last_operation=None;self.phase='idle';self.return_stop.set()
        except BrokerError as error:
            with self.lock:
                if operation!=self.last_operation or epoch!=self.epoch or self.closed:return
                self.reason=error.code;self.retry=error.retry_after_ms
                if error.code in {'LEASE_EXPIRED','STALE_BOOT','AUTH_DENIED'}:
                    # The broker can no longer prove this receipt. End tracking
                    # honestly, without claiming restoration or replaying media.
                    self.restore_state='unconfirmed';self.last_operation=None;self.phase='idle';self.return_stop.set()
                    self.record('return-receipt-unavailable',error.code)

    def _adopt_return(self,receipt,operation):
        self.restore_state=receipt.get('restore_state','pending')
        self.last_operation=operation if self.restore_state in {'pending','deferred'} else None
        self.phase='restoring' if self.last_operation else 'idle'
        if self.last_operation and not self.closed:self.follow_return()
        else:self.return_stop.set()

    def reconcile_opening(self,session_id,epoch):
        """Bounded metadata reconciliation after an acquire reply was lost."""
        self.opening_stop.set();stop=threading.Event();self.opening_stop=stop
        def work():
            for delay in (0,1,2,4,8):
                if stop.wait(delay):return
                with self.lock:
                    if self.closed or self.epoch!=epoch or self.opening!=session_id:return
                try:
                    state=self.broker.discover(True);lease=state.get('lease')
                    if lease and lease.get('session_id')==session_id:
                        reply=self.broker.release(lease_id=lease['lease_id'],generation=lease['generation'],reason='client-stopping')
                        with self.lock:
                            if self.epoch!=epoch or self.opening!=session_id:return
                            self.opening=None
                            self._adopt_return(reply,lease['operation_id'])
                        return
                    if lease is None or lease.get('session_id')!=session_id:
                        with self.lock:
                            if self.epoch==epoch and self.opening==session_id:
                                self.opening=None;self.phase='idle'
                        return
                except BrokerError:pass
            with self.lock:
                if self.epoch==epoch and self.opening==session_id:
                    self.opening=None;self.phase='idle';self.restore_state='unconfirmed'
                    self.reason='ACQUISITION_UNCONFIRMED'
        self.opening_thread=threading.Thread(target=work,name='das-open-reconcile',daemon=True)
        self.opening_thread.start()

    def game_preview(self,number):
        """Explicit, software-only native-pixel crop; never registration or USB."""
        game=self.store.get(number);media=game.get('media',{})
        relative=media.get('panel_source') or media.get('cover') or media.get('thumbnail')
        if not relative:raise BrokerError('CONTENT_MISSING')
        runner=self.service.compiler.runner;source=self.store.managed(relative,True)
        filter_spec=framing_filter(self.options['framing'],game.get('faceplate_crop'))
        with self.service.lease():
            raw=capture([runner.ffmpeg,'-v','error','-xerror','-nostdin','-threads','2','-filter_threads','2',
                '-protocol_whitelist','file,pipe','-i',str(source),'-vf',
                filter_spec,
                '-frames:v','1','-an','-sn','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
                environment=_decoder_environment(runner.library_path),timeout=15,maximum=10368,
                checkpoint=lambda:None,lease_fd=self.service.compiler.lease_fd)
        data,_=compile_pages([index_rgb(raw)],2,'none')
        return dict(data_url='data:image/gif;base64,'+base64.b64encode(data).decode(),width=64,height=54)

    def export(self):
        return self.export_descriptor(self.readiness()['ready'])

    def _validate_player(self,p):
        base={'event','token','collection_id','session_id','mode','sequence'}
        fields={'open':set(),'clock':set(),'heartbeat':set(),'ready':{'ready_mono_ms','deadline_mono_ms','clock_uncertainty_ms'},
                'started':{'started_mono_ms','outcome','candidate_id'},'stop':{'reason'}}
        event=p.get('event')
        if event not in fields or set(p)!=base|fields[event]:raise BrokerError('INVALID_REQUEST')
        identifier(p['session_id']);digest(p['collection_id'])
        if type(p['sequence']) is not int or not 1<=p['sequence']<=9007199254740991:raise BrokerError('INVALID_REQUEST')
        if event=='stop' and (not isinstance(p['reason'],str) or p['reason'] not in PLAYER_END_REASONS):raise BrokerError('INVALID_REQUEST')
        if event=='started':
            if p['outcome'] not in {'software-coordinated','tv-only','independent'}:raise BrokerError('INVALID_REQUEST')
            if p['mode']=='sync':
                if type(p['started_mono_ms']) is not int or p['started_mono_ms']<0 or p['outcome']=='independent':raise BrokerError('INVALID_REQUEST')
            elif p['started_mono_ms'] is not None or p['outcome']!='independent':raise BrokerError('INVALID_REQUEST')
            if p['outcome']=='software-coordinated':identifier(p['candidate_id'])
            elif p['candidate_id'] is not None:raise BrokerError('INVALID_REQUEST')
        if (not isinstance(p['token'],str) or not self.installer.token
                or not hmac.compare_digest(p['token'],self.installer.token)):raise BrokerError('AUTH_DENIED')
        exported=getattr(self.installer,'jsaux_export',None)
        if (not self.installer.cached.get('installed') or self.installer.cached.get('error') or (event!='stop' and not self.export()) or not exported or p['collection_id']!=exported.get('collection_id')
                or p['mode']!=exported.get('mode') or event!='stop' and p['collection_id']!=self.identity()):raise BrokerError('CONTENT_MISSING')
        return event

    def player(self,p):
        if p.get('event') in {'open','ready','started','stop'}:self.record('player-message-'+p['event'])
        # Stop must invalidate a pending read/acquisition without queuing behind
        # player_lock; authentication still uses the installed immutable export.
        if p.get('event')=='stop':
            try:
                self._validate_player(p)
                with self.lock:
                    current=self.session
                    if current and (p['session_id']!=current['id'] or p['sequence']<=current['sequence']):raise BrokerError('STALE_GENERATION')
                    if not current and self.opening not in (None,p['session_id']):raise BrokerError('STALE_GENERATION')
                    stop_epoch=self.epoch
                accepted=self.stop('player-ended',expected_epoch=stop_epoch,player_reason=p['reason'])
                self.record('player-stop' if accepted else 'player-stop-refused',p['reason'] if accepted else 'STALE_GENERATION');return dict(accepted=accepted)
            except (BrokerError,ScreensaverError) as error:
                self.record('player-stop-refused',getattr(error,'code','INTERNAL_ERROR'));return dict(accepted=False)
        with self.player_lock:
            attempt_epoch=self.epoch
            try:
                result=self._player(p)
                if p.get('event') in {'open','ready','started','stop'}:self.record('player-'+p['event'],'' if result.get('accepted') else self.reason)
                return result
            except (BrokerError,ScreensaverError) as error:
                with self.lock:
                    if p.get('event')=='open' and self.opening==p.get('session_id') and self.epoch==getattr(self,'_opening_epoch',attempt_epoch):
                        attempt_epoch=self._opening_epoch
                        if getattr(error,'uncertain',False):self.reconcile_opening(self.opening,attempt_epoch)
                        else:self.opening=None;self.phase='idle'
                with self.lock:
                    if self.closed or self.epoch!=attempt_epoch:return dict(accepted=False,tv_only=True,reason='STALE_GENERATION')
                    session=self.session
                    self.reason=getattr(error,'code','INTERNAL_ERROR');self.retry=getattr(error,'retry_after_ms',0)
                    if (p.get('event')=='heartbeat' and self.reason=='BROKER_UNAVAILABLE' and session
                            and session.get('id')==p.get('session_id') and not session.get('terminal')
                            and self._lease_remaining(session)>0):
                        session['transport_uncertain']=True
                        session['heartbeat_failures']=session.get('heartbeat_failures',0)+1
                        self.record('heartbeat-degraded',self.reason)
                        return dict(accepted=False,retryable=True,reason=self.reason,lease_remaining_ms=self._lease_remaining(session))
                    self.record('player-refused',self.reason)
                    read_evidence=p.get('event')=='heartbeat' and self.reason=='LEASE_EXPIRED' and session
                evidence=None
                if read_evidence:
                    try:evidence=self.broker.operation(operation_id=session['operation_id'])
                    except (BrokerError,ScreensaverError):pass
                with self.lock:
                    if self.closed or self.epoch!=attempt_epoch or self.session is not session:
                        return dict(accepted=False,tv_only=True,reason='STALE_GENERATION')
                    if evidence:
                        self._remember_operation(evidence,session['operation_id'])
                        actual=evidence.get('reason')
                        if evidence.get('lease_state') in TERMINAL and isinstance(actual,str) and actual.isupper():
                            self.reason=actual;self.record('player-revocation',actual)
                    if session:session['terminal']=True
                    return dict(accepted=False,tv_only=True,reason=self.reason)

    def _lease_remaining(self,session):
        return max(0,min(8000,int((session.get('lease_deadline',0)-time.monotonic())*1000)))

    def _lease_evidence(self,session,value,sent):
        ttl=value.get('expires_in_ms')
        if type(ttl) is int and 0<=ttl<=8000:
            session['lease_deadline']=sent+ttl/1000

    def _heartbeat_diagnostic(self):
        with self.lock:
            session=self.session
            if not session:return dict(state='inactive')
            now=time.monotonic()
            return dict(state='terminal' if session.get('terminal') else 'degraded' if session.get('transport_uncertain') else 'available',
                remaining_ms=self._lease_remaining(session),failures=min(999,session.get('heartbeat_failures',0)),
                last_success_age_ms=None if session.get('heartbeat_ok_at') is None else max(0,round((now-session['heartbeat_ok_at'])*1000)))

    def _require_session(self,session,epoch):
        if self.closed or self.epoch!=epoch or self.session is not session:
            raise BrokerError('STALE_GENERATION')

    def _player(self,p):
        event=self._validate_player(p);session=self.session
        if event=='stop' and not session:return dict(accepted=True)
        if event=='open':
            epoch=self.epoch
            if session and (session.get('terminal') or time.monotonic()-self.last_player>=8):
                self.stop();session=None;epoch=self.epoch
            if session or p['session_id'] in self.seen:return dict(accepted=False,tv_only=True)
            installed_wait=self.installer.jsaux_export.get('sync_wait_ms',2500)
            if p['mode']=='sync' and (installed_wait>self.sync_wait_ms()
                    or not admits(self.receipt.get('bytes',0),installed_wait)):
                # Reject old oversized exports before registration/acquisition.
                # Reopening cannot write the same unsafe collection repeatedly.
                raise BrokerError('JSAUX_SYNC_WINDOW')
            self.seen.add(p['session_id'])
            self.opening=p['session_id']
            self._opening_epoch=epoch
            if len(self.seen)>64:self.seen={p['session_id']}
            # GCA's independent fallback observer samples every two seconds.
            # New HTTP exports allow that observation to arrive, without
            # extending the TV's immutable readiness deadline or forcing USB.
            http=(self.installer.jsaux_export or {}).get('relay',{}).get('kind')=='http-loopback-v1'
            began=time.monotonic();self.first_player=True;state=None;wait_until=began+(2.3 if http else 1.7)
            self.record('steam-observation-wait')
            while not self.closed and self.epoch==epoch and time.monotonic()<wait_until:
                state=self.refresh()
                if state and state['steam']['observed']=='active' and state['steam'].get('activation_id'):break
                if state and state['steam'].get('activation_closed') and state['steam']['observed']=='active':raise BrokerError('ACTIVATION_CLOSED')
                self.recovery_stop.wait(.075)
            if self.closed or self.epoch!=epoch:raise BrokerError('STALE_GENERATION')
            active=bool(state and state['steam']['observed']=='active' and state['steam'].get('activation_id'))
            self.record('steam-observation-result',active=active,elapsed_ms=round((time.monotonic()-began)*1000),
                observation_age_ms=(state or {}).get('steam',{}).get('observation_age_ms'))
            if not active:raise BrokerError('STEAM_INACTIVE')
            activation=state['steam']['activation_id']
            # Rediscover the immutable content after a broker restart, without USB.
            self.record('content-registration-start')
            content_id=self._registered(max(time.monotonic()+.01,began+2.8 if http else wait_until),epoch,force=True)
            self.record('content-registration-ready',elapsed_ms=round((time.monotonic()-began)*1000))
            installed_wait=self.installer.jsaux_export.get('sync_wait_ms',2500)
            if p['mode']=='sync' and (installed_wait>self.sync_wait_ms()
                    or not admits(self.receipt.get('bytes',0),installed_wait)):
                raise BrokerError('JSAUX_SYNC_WINDOW')
            self.record('gca-acquire-start')
            acquire_sent=time.monotonic()
            lease=self.broker.acquire(activation_id=activation,session_id=p['session_id'],content_id=content_id,
                                      collection_id=p['collection_id'],mode=p['mode'])
            self.record('gca-acquire-accepted',elapsed_ms=round((time.monotonic()-began)*1000))
            with self.lock:
                if not self.closed and self.epoch==epoch:
                    session=dict(id=p['session_id'],sequence=p['sequence'],lease_id=identifier(lease['lease_id']),generation=lease['generation'],
                        operation_id=identifier(lease['operation_id']),alignment_attempt_id=lease.get('alignment_attempt_id'),
                        terminal=False,renew_sequence=0,renew_at=time.monotonic()+2,mode=p['mode'],sync_wait_ms=installed_wait,
                        alignment_ms=self.calibration_status()['offset_ms'],reference=None,
                        broker_boot=getattr(self.broker,'boot',None),lease_deadline=acquire_sent+lease.get('expires_in_ms',0)/1000,
                        heartbeat_ok_at=None,heartbeat_failures=0,transport_uncertain=False)
                    self.session=session;self.last_alignment={};self.player_end_reason=''
                    self._remember_operation({},session['operation_id'])
                    self.opening=None
                    self.last_player=time.monotonic();self.last_transfer='not-started'
                    self.phase='waiting';self._watch_session(session)
                    return dict(accepted=True,alignment_ms=session['alignment_ms'],lease_remaining_ms=self._lease_remaining(session))
            # Stop may arrive while acquisition is in flight. Never bind its
            # late reply, and keep cleanup failure separate from a newer session.
            try:
                self.broker.release(lease_id=lease['lease_id'],generation=lease['generation'],reason='client-stopping')
            except BrokerError as error:self.record('stale-acquisition-release-failed',error.code)
            return dict(accepted=False,tv_only=True)
        with self.lock:
            if not session or self.session is not session or session['id']!=p['session_id'] or p['sequence']<=session['sequence']:raise BrokerError('STALE_GENERATION')
            session['sequence']=p['sequence'];epoch=self.epoch
            self.last_player=time.monotonic()
        if event=='stop':self.stop('player-ended');return dict(accepted=True)
        if session['terminal']:return dict(accepted=False,tv_only=True,reason=self.reason)
        common=dict(lease_id=session['lease_id'],generation=session['generation'])
        if event=='clock':return dict(broker_mono_ms=time.monotonic_ns()//1000000)
        if event=='ready':
            if p['mode']=='sync':
                for k in ('ready_mono_ms','deadline_mono_ms','clock_uncertainty_ms'):
                    if type(p[k]) is not int or p[k]<0:raise BrokerError('INVALID_REQUEST')
                if p['deadline_mono_ms']!=p['ready_mono_ms']+session['sync_wait_ms'] or p['clock_uncertainty_ms']>50:raise BrokerError('CLOCK_UNAVAILABLE')
                if transfer_estimate_ms(self.receipt.get('bytes',0))>p['deadline_mono_ms']-time.monotonic_ns()//1000000:
                    self.stop('tv-timeout');raise BrokerError('ALIGNMENT_EXPIRED')
            elif any(p[k] is not None for k in ('ready_mono_ms','deadline_mono_ms','clock_uncertainty_ms')):raise BrokerError('INVALID_REQUEST')
            self.record('gca-ready-start')
            value=self.broker.ready(**common,alignment_attempt_id=session['alignment_attempt_id'],
                **{k:p[k] for k in ('ready_mono_ms','deadline_mono_ms','clock_uncertainty_ms')})
            with self.lock:
                self._require_session(session,epoch)
                self.record('gca-ready-result',ready=value.get('gate_accepted') is True)
                self.phase='transferring';return dict(accepted=True,**value)
        if event=='started':
            self.record('gca-tv-started-start')
            value=self.broker.tv_started(**common,alignment_attempt_id=session['alignment_attempt_id'],
                **{k:p[k] for k in ('started_mono_ms','outcome','candidate_id')})
            with self.lock:
                self._require_session(session,epoch)
                self.record('gca-tv-started-result')
                self.phase='active' if p['outcome']!='tv-only' else 'idle'
                if p['outcome']=='tv-only':session['terminal']=True
                return dict(accepted=True)
        if event=='heartbeat':
            if self._lease_remaining(session)<=0:raise BrokerError('LEASE_EXPIRED')
            if session.get('transport_uncertain'):
                # Reconnect/read first: an ambiguous renewal is never an
                # excuse to reacquire/replay ready or an upload.
                check_sent=time.monotonic()
                check=self.broker.operation(operation_id=session['operation_id'])
                with self.lock:
                    self._require_session(session,epoch)
                    if session.get('broker_boot')!=getattr(self.broker,'boot',None):raise BrokerError('STALE_BOOT')
                    self._lease_evidence(session,check,check_sent)
                    if check.get('lease_state') in TERMINAL:
                        self._remember_operation(check,session['operation_id'])
                        raise BrokerError(check.get('reason') or 'LEASE_EXPIRED')
            if time.monotonic()>=session['renew_at']:
                session['renew_sequence']+=1
                renew_sent=time.monotonic()
                renewal=self.broker.renew(**common,sequence=session['renew_sequence'])
                with self.lock:
                    self._require_session(session,epoch)
                    if session.get('broker_boot')!=getattr(self.broker,'boot',None):raise BrokerError('STALE_BOOT')
                    self._lease_evidence(session,renewal,renew_sent)
                    session['renew_at']=time.monotonic()+2
            sent=time.monotonic_ns()//1000000
            operation_sent=time.monotonic()
            value=self.broker.operation(operation_id=session['operation_id'])
            received=time.monotonic_ns()//1000000
            with self.lock:
                self._require_session(session,epoch)
                if session.get('broker_boot')!=getattr(self.broker,'boot',None):raise BrokerError('STALE_BOOT')
                self._lease_evidence(session,value,operation_sent)
                if session.get('transport_uncertain'):self.record('heartbeat-recovered')
                session['transport_uncertain']=False;session['heartbeat_ok_at']=time.monotonic()
                self._remember_operation(value,session['operation_id'])
                reason=value.get('reason') or '';self.reason=reason if isinstance(reason,str) and reason.isupper() and reason not in NORMAL_RELEASE_REASONS else ''
                self.retry=value.get('retry_after_ms',0);self.alignment=value.get('alignment_state',self.alignment)
                self.restore_state=value.get('restore_state',self.restore_state)
                self.last_transfer=value.get('transfer_state','not-started')
                if self.last_transfer in {'confirmed','unconfirmed','failed','deferred'} and not any(e['event']=='transfer-'+self.last_transfer for e in self.events[-4:]):
                    self.record('transfer-'+self.last_transfer,self.reason)
                if value.get('lease_state') in TERMINAL:
                    self.record('player-terminal',self.reason)
                    session['terminal']=True;self.phase='idle';return dict(accepted=False,tv_only=True,reason=self.reason)
                candidate=value.get('candidate')
                if candidate and session.get('reference') is None:
                    measured=reference(value,sent,received)
                    if measured:
                        session['reference']=measured
                        self.last_alignment=dict(reference_basis=measured['basis'],uncertainty_ms=measured['uncertainty_ms'],
                            offset_ms=session.get('alignment_ms',0),optical='not-measured')
                        self.record('alignment-reference',elapsed_ms=measured['uncertainty_ms'])
                return dict(accepted=True,candidate=candidate,timing=session.get('reference'),lease_remaining_ms=self._lease_remaining(session))
        raise BrokerError('INVALID_REQUEST')

    def stop(self,reason='client-stopping',expected_session=None,expected_last_player=None,expected_epoch=None,player_reason=None):
        with self.lock:
            if expected_epoch is not None and self.epoch!=expected_epoch:return False
            if expected_session is not None and (self.session is not expected_session or self.last_player!=expected_last_player):return False
            if self.session is None and self.opening is None and (
                    self.phase=='releasing' or self.last_operation and self.restore_state in {'pending','deferred'}):
                # Duplicate Stop must not invalidate the first release reply
                # or erase a still-pending return after the session is detached.
                self.watchdog_stop.set();return True
            if player_reason in PLAYER_END_REASONS:self.player_end_reason=player_reason
            self.epoch+=1;epoch=self.epoch
            session=self.session;self.session=None;self.opening=None
            self.phase='releasing' if session else 'restoring' if self.last_operation and self.restore_state in {'pending','deferred'} else 'idle'
            self.watchdog_stop.set()
            if expected_session is not None:self.record('player-heartbeat-timeout',elapsed_ms=max(0,round((time.monotonic()-self.last_player)*1000)))
        if session:
            try:
                self.record('gca-release-start')
                receipt=self.broker.release(lease_id=session['lease_id'],generation=session['generation'],reason=reason)
                self.record('gca-release-result')
                with self.lock:
                    # A late release of the old lease cannot overwrite a new
                    # activation's phase or restoration state.
                    if self.epoch!=epoch or self.session is not None:return True
                    self._adopt_return(receipt,session['operation_id'])
            except BrokerError as error:
                with self.lock:
                    if self.epoch==epoch:
                        self.reason=error.code;self.restore_state='pending'
                        self.last_operation=session['operation_id'];self.phase='restoring'
                        if not self.closed:self.follow_return()
        return True

    def shutdown(self,timeout=3):
        self.closed=True;self.recovery_stop.set();self.return_stop.set();self.opening_stop.set();self.cancelled.set();self.stop();self.broker.close()
        if self.return_thread:self.return_thread.join(max(0,timeout))
        if self.opening_thread:self.opening_thread.join(max(0,timeout))
        if self.thread:self.thread.join(max(0,timeout))
        if self.recovery_thread:self.recovery_thread.join(max(0,timeout))
        if self.watchdog_thread and self.watchdog_thread is not threading.current_thread():self.watchdog_thread.join(max(0,timeout))
