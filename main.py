"""Decky entry point. No serial driver, idle media worker or standalone app."""
import asyncio
import base64
import json
import os
from pathlib import Path
import threading
import time
import decky
from das.display_name import migrate as migrate_display_name
from das.settings_backup import SettingsBackup, recover as recover_settings
from das.provider import Provider,SteamGridDBError
from das.library import _steam_home
from das.core.catalog import ScreensaverError, atomic_json
from das.core.resources import Resources
from das.studio.service import StudioService
from das.studio.installer import Installer
from das.studio.preview import Preview
from das.jsaux.manager import Delegation
from das.jsaux.player_relay import PlayerRelay
from das.jsaux.player_debug import collect_cef
from das.jsaux.protocol import BrokerError
from das.updates import Updater,UnavailableUpdater
from das.github import UpdateError
from das.studio.migration import start as import_gca_studio
from das.studio.workspace import CollectionWorkspace
from das.studio.discovery import Discovery,thumbnail,image_diagnostic

VERSION='1.0.0'

class Plugin:
    async def _main(self):
        self._lock=threading.RLock();self._closed=False;self._running={};self._events=[];self._generation=None
        self.root=Path(decky.DECKY_PLUGIN_SETTINGS_DIR)/'library'
        recover_settings(self.root)
        self.provider=Provider(self.root.parent/'steamgriddb-secret.json')
        self.tools=Resources(self.root.parent,event_callback=self._event)
        self.service=StudioService(self.root,self.provider,current_game=self._current,event_callback=self._event)
        assets=Path(decky.DECKY_PLUGIN_DIR)/'assets/player'
        self.installer=Installer(self.service.catalog,_steam_home() or Path(os.environ.get('DECKY_USER_HOME','/home/deck'))/'.local/share/Steam',assets)
        self.preview=Preview(self.service.catalog,assets,self.service)
        self.gca_import_root=Path(os.environ.get('DECKY_USER_HOME','/home/deck'))/'.local/share/gabecubeaura/animated-screensaver-studio'
        self.jsaux=Delegation(self.service,self.installer)
        self.workspace=CollectionWorkspace(self.service,self.installer,self.jsaux)
        self.settings_backup=SettingsBackup(self.service,self.workspace,self.jsaux,os.environ.get('DECKY_USER_HOME','/home/deck'))
        self.discovery=Discovery(self.service)
        self.player_relay=PlayerRelay(self.jsaux,debug_path=self.root.parent/'jsaux-player-debug.json')
        self.jsaux.player_relay=self.player_relay
        self.installer.delegation=self.jsaux
        self.service.after_prepare=self.jsaux.after_tv_prepare
        # Decky schedules _main and its RPC server concurrently. Expose every
        # dependency of _status() before the first await: on a Steam Deck,
        # state/jsaux_refresh/update_status can arrive during initial discovery.
        try:
            self.updater=Updater(self.root.parent/'updates',Path(decky.DECKY_PLUGIN_DIR),VERSION,
                blocked=lambda:bool(self._activity()['update_blockers']),install_lock=self._lock)
        except (OSError,ValueError,UpdateError):
            # A broken optional updater must not prevent TV/preview operation.
            self.updater=UnavailableUpdater(VERSION)
        await asyncio.to_thread(self.installer.status,True)
        if self.jsaux.options['enabled'] and (self.installer.jsaux_export or {}).get('relay')==self.player_relay.descriptor():
            try:await asyncio.to_thread(self.player_relay.start)
            except BrokerError as error:self.jsaux.reason=error.code # Optional JSAUX cannot prevent the TV plugin loading.
        # One bounded discovery at load, not a periodic background scan.
        await asyncio.to_thread(self.jsaux.refresh)
        self.jsaux.recover()
        try:migrate_display_name(Path(decky.DECKY_PLUGIN_DIR))
        except (OSError,ValueError,UpdateError,ScreensaverError):self._event('display_name_migration_deferred')
        self.updater.start()

    def _event(self,kind,**fields):
        # Allowlisted labels and numeric metadata only, not URLs, keys or speech.
        safe={k:v for k,v in fields.items() if k in {'code','stage','phase','appid','percent','exit_code','reason','exception','received','accepted'} and isinstance(v,(str,int,float,type(None)))}
        self._events=(self._events+[dict(at=int(time.time()),event=str(kind)[:80],**safe)])[-80:]

    def _current(self):
        return dict(appid=next(iter(self._running),0))

    def _activity(self):
        """Read-only busy evidence shared by updater and both diagnostic routes."""
        tv=self.service._busy();workspace=self.workspace.busy();panel=self.jsaux.busy();display=self.jsaux.display_busy()
        tv_alive=bool(self.service.thread and self.service.thread.is_alive())
        task=self.workspace.data['task'];job=self.service.job
        blockers=[code for code,active in (
            ('game_running',self.service._playing()),('tv_preparation',tv or tv_alive or job.get('state') in {'paused','paused_game'}),
            ('collection_workflow',workspace or task.get('state')=='paused'),
            ('faceplate_preparation',panel),('faceplate_display_or_return',display)) if active]
        return dict(schema='das-activity-v1',update_blockers=blockers,
            tv=dict(worker_active=tv,worker_alive=tv_alive,state=job.get('state'),stage=job.get('stage'),
                    completed=job.get('completed'),total=job.get('total'),queue_count=len(job.get('queue',[]))),
            workspace=dict(worker_active=workspace,state=task.get('state'),stage=task.get('stage'),outcome=task.get('outcome')),
            faceplate=self.jsaux.activity())

    def _detail_thumbnail(self,entry):
        entry=dict(entry)
        number=entry.get('appid',0)
        entry['installed_in_collection']=self.installer.contains(number)
        if number>0:entry.setdefault('thumbnail_url',f'https://cdn.akamai.steamstatic.com/steam/apps/{number}/header.jpg')
        relative=entry.get('media',{}).get('thumbnail')
        if relative:
            try:
                path=self.service.catalog.managed(relative,True)
                if path.stat().st_size<=256*1024:
                    raw=path.read_bytes()
                    mime='image/jpeg' if raw.startswith(b'\xff\xd8') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else None
                    if mime:entry['thumbnail_url']='data:'+mime+';base64,'+base64.b64encode(raw).decode()
            except (OSError,ScreensaverError):pass
        return entry

    def _status(self):
        tools=self.tools.status();generation=(tools.get('ready'),tools.get('phase'),tools.get('error'))
        if generation!=self._generation:
            executable=self.tools.executable() if tools.get('ready') else None
            self.service.compiler.configure_runtime(executable,self.tools.library_path() if executable else None)
            self._generation=generation
        state=self.service.status()
        state.update(version=VERSION,installation=self.installer.status(),
            media_tools={**tools,'installed':tools.get('ready',False),'state':tools.get('phase','idle')})
        state['media_tools']['available']=bool(state['capabilities'].get('ffmpeg') and state['capabilities'].get('ffprobe'))
        state['jsaux']=self.jsaux.status()
        state['cleanup']=self.service.last_cleanup
        state['updates']=self.updater.status()
        state['workspace']=self.workspace.summary()
        state['activity']=self._activity()
        state['display_name_restart_required']=os.environ.get('DECKY_PLUGIN_NAME')=='Decky-Animated-Screensaver'
        return state

    async def studio(self,action:str,payload:dict=None):
        if not hasattr(self,'service') or self._closed:raise ValueError('Screensaver is starting or stopping. Try again.')
        payload={} if payload is None else payload
        if not isinstance(action,str) or not isinstance(payload,dict) or len(json.dumps(payload))>8192:raise ValueError('Invalid request')
        if action=='jsaux_player':return await asyncio.to_thread(self.jsaux.player,payload)
        return await asyncio.to_thread(self._apply,action,payload)

    def _apply(self,action,payload):
        if action=='close_preview':
            self.preview.close(request_id=payload.get('request_id'),nonce=payload.get('nonce'));return None
        if action=='preview_installed':
            try:
                number=payload.get('appid');request_id=payload.get('request_id')
                if number is not None and (type(number) is not int or not 0<abs(number)<=0xffffffff):raise ScreensaverError('Invalid game','invalid_setting')
                if request_id is not None and (not isinstance(request_id,str) or not 16<=len(request_id)<=100 or not request_id.isalnum()):raise ScreensaverError('Invalid preview request','invalid_setting')
                if self.workspace.busy() or self.service._busy():raise ScreensaverError('Wait for the update','busy')
                return self.preview.installed(self.installer,number,request_id)
            except (ScreensaverError,OSError,ValueError,KeyError,TypeError) as error:
                code=getattr(error,'code','installation_conflict');self._event('installed_preview_error',code=code,appid=number)
                return dict(schema='das-discovery-error-v1',ok=False,error=code)
        if action=='candidate_preview':
            try:
                number=payload.get('appid');role=payload.get('role');asset_id=payload.get('asset_id');motion=payload.get('motion',False);request_id=payload.get('request_id')
                if (type(number) is not int or not 0<abs(number)<=0xffffffff or not isinstance(role,str) or role not in {'animation','still_tv','cover','logo','panel'}
                    or type(asset_id) is not int or asset_id<=0 or type(motion) is not bool
                    or not isinstance(request_id,str) or not 16<=len(request_id)<=100 or not request_id.isalnum()):raise ScreensaverError('Invalid candidate request','invalid_setting')
                if self.workspace.busy() or self.jsaux.busy():raise ScreensaverError('Wait for preparation','busy')
                return self.preview.candidate(number,role,asset_id,motion,request_id)
            except (ScreensaverError,SteamGridDBError,OSError,ValueError,KeyError) as error:
                code=getattr(error,'code','download_failed')
                self._event('candidate_preview_error',code=code,stage='motion' if payload.get('motion') else 'still',appid=payload.get('appid'))
                return dict(schema='das-discovery-error-v1',ok=False,error=code)
        if action=='preview_recipe':
            try:
                number=payload.get('appid')
                if type(number) is not int or not 0<abs(number)<=0xffffffff:raise ScreensaverError('Invalid game','invalid_setting')
                if self.service._busy() or self.workspace.busy() or self.jsaux.busy():raise ScreensaverError('Wait for preparation','busy')
                patch=self.workspace.draft_patch(number,payload.get('patch',{}))
                with self.workspace.lock:
                    saved=self.workspace.data['drafts'].get(str(number),{}).get('patch',{})
                    patch={**self.workspace._validated_patch(saved),**patch}
                request_id=payload.get('request_id')
                if request_id is not None and (not isinstance(request_id,str) or not 16<=len(request_id)<=100 or not request_id.isalnum()):raise ScreensaverError('Invalid preview request','invalid_setting')
                artwork_only=payload.get('artwork_only',False)
                if type(artwork_only) is not bool:raise ScreensaverError('Invalid preview mode','invalid_setting')
                return self.preview.open(number,patch,request_id=request_id,artwork_only=artwork_only)
            except ScreensaverError as error:
                self._event('preview_error',code=error.code,appid=payload.get('appid'))
                return dict(schema='das-discovery-error-v1',ok=False,error=error.code)
            except (OSError,ValueError,KeyError) as error:
                self._event('preview_error',code='download_failed',exception=type(error).__name__,appid=payload.get('appid'))
                return dict(schema='das-discovery-error-v1',ok=False,error='download_failed')
        # Read-only network operations must not hold the mutation/installation
        # lock. Discovery bounds its concurrency; late UI replies are discarded.
        if action in {'browse_search','browse_top','browse_candidates'}:
            if self._closed:raise ValueError('Screensaver is stopping')
            try:
                if action in {'browse_search','browse_top'}:
                    result=self.discovery.search(payload.get('query','')) if action=='browse_search' else self.discovery.ranking(payload.get('force') is True)
                    rows=[]
                    for row in result['items']:
                        current=self.service.catalog.get(row['appid'])
                        rows.append({**row,**self.workspace.overlay(current)} if current else row)
                    return {**result,'items':rows}
                number=payload.get('appid')
                if type(number) is not int or not 0<abs(number)<=0xffffffff:raise ValueError('Invalid game ID')
                role=payload.get('role','animation')
                if not isinstance(role,str) or role not in {'animation','still_tv','cover','logo','panel'}:raise ValueError('invalid_setting')
                return self.discovery.candidates(number,role)
            except ScreensaverError as error:
                self._event('discovery_error',code=error.code,stage=getattr(error,'stage',action))
                # Decky hides Python exception text. Expected discovery errors
                # cross RPC as data so the UI can display their useful code.
                return dict(schema='das-discovery-error-v1',ok=False,error=error.code)
        if action=='update_status':
            # Cheap cached metadata. No Studio/media/hardware discovery, network
            # request or wait behind the library RPC lock while QAM is closed.
            if self._closed:raise ValueError('Screensaver is stopping')
            return self.updater.status()
        if action in {'settings_snapshot','settings_export','settings_import'}:
            try:
                with self._lock:
                    if self._closed:raise ScreensaverError('Plugin is stopping','busy')
                    if action=='settings_snapshot':
                        updates=self.updater.status()
                        return dict(backup=self.settings_backup.snapshot(),updates={k:updates[k] for k in ('channel','auto_check','interval_minutes')},
                            calibration=self.jsaux.status().get('calibration'),home=str(self.settings_backup.home))
                    if action=='settings_export':return self.settings_backup.export()
                    if payload.get('confirm') is not True:raise ScreensaverError('Confirm the action first','confirmation_required')
                    if action=='settings_import':
                        if self.updater.phase=='installing':raise ScreensaverError('Wait for the update','busy')
                        return self.settings_backup.restore(payload.get('path'))
            except (ScreensaverError,UpdateError,OSError,ValueError,TypeError) as error:
                self._event('settings_backup_error',code=getattr(error,'code','backup_failed'))
                return dict(schema='das-action-error-v1',ok=False,error=getattr(error,'code','backup_failed'))
        # Controls must not queue behind a slow library/API RPC.
        if action in {'pause','cancel','resume'}:
            if self._closed:raise ValueError('Screensaver is stopping')
            if action=='resume' and self.updater.phase=='installing':raise UpdateError('update_busy')
            if self.workspace.busy() and self.workspace.data['task']['state']=='applying':raise ValueError('busy')
            if action!='resume' or not self.workspace.resume(payload.get('language','en')):self.service.control(action)
            if action=='cancel':self.workspace.cancel()
            if action in {'pause','cancel'}:self.jsaux.cancelled.set()
            return self._status()
        with self._lock:
            if self._closed:raise ValueError('Screensaver is stopping')
            service=self.service;number=payload.get('appid')
            if number is not None and (type(number) is not int or not 0<abs(number)<=0xffffffff):raise ValueError('Invalid game ID')
            try:
                if action=='workspace_order':return self.workspace.order_snapshot()
                if action=='workspace_reorder':
                    if self.updater.phase=='installing':raise UpdateError('update_busy')
                    try:self.workspace.reorder(payload.get('appids'),payload.get('revision'))
                    except OSError as error:
                        self._event('collection_change_error',exception=type(error).__name__)
                        raise ScreensaverError('Could not save collection order','collection_change_failed') from None
                    return self._status()
                if action in {'workspace_select_all','workspace_deselect_all','workspace_undo_selection','workspace_delete_collection'}:
                    if self.updater.phase=='installing':raise UpdateError('update_busy')
                    if action=='workspace_delete_collection' and payload.get('confirm') is not True:
                        raise ScreensaverError('Confirm collection deletion','confirmation_required')
                    self.workspace.ensure_idle()
                    try:
                        if action=='workspace_select_all':
                            source=payload.get('source')
                            if source=='installed':self.workspace.select_all(payload.get('query',''))
                            elif source in {'online','top'}:
                                ids=payload.get('appids')
                                if not isinstance(ids,list) or len(ids)>100 or any(type(n) is not int or not 0<n<=0xffffffff for n in ids):raise ScreensaverError('Invalid result set','invalid_setting')
                                with self.discovery.lock:
                                    if any(not service.catalog.get(n) and n not in self.discovery.known for n in ids):raise ScreensaverError('Search for this game first','not_installed')
                                for n in dict.fromkeys(ids):self.discovery.open(n)
                                self.workspace.select_all(appids=ids)
                            else:raise ScreensaverError('Invalid game source','invalid_setting')
                        elif action=='workspace_deselect_all':self.workspace.deselect_all()
                        elif action=='workspace_undo_selection':self.workspace.undo_selection(payload.get('token'))
                        else:
                            self.preview.quiesce();self.jsaux.stop()
                            self.workspace.delete_collection();self.player_relay.close()
                    except OSError as error:
                        self._event('collection_change_error',exception=type(error).__name__)
                        raise ScreensaverError('Could not change collection','collection_change_failed') from None
                    return self._status()
                if action=='workspace_preferences':self.workspace.preferences(payload.get('patch',{}));return self._status()
                if action=='workspace_draft':self.workspace.save_draft(number,payload.get('patch',{}),reconcile_membership=payload.get('reconcile_membership') is True);return self._status()
                if action=='workspace_discard':self.workspace.discard(number);return self._status()
                if action=='workspace_details':return self._detail_thumbnail(self.workspace.overlay(service.game_details(number)))
                if action=='browse_open':return self._detail_thumbnail(self.workspace.overlay(self.discovery.open(number)))
                if action in {'workspace_prepare','workspace_install'}:
                    if self.updater.phase=='installing':raise UpdateError('update_busy')
                    if payload.get('confirm') is not True:raise ScreensaverError('Confirm file installation','confirmation_required')
                    self.preview.quiesce();self._status()
                    self.workspace.start(payload.get('language','en'),action=='workspace_install',mode=payload.get('mode','missing'),repair_faceplate=payload.get('repair_faceplate',False),independent=payload.get('independent',False));return self._status()
                if self.workspace.busy() and action in {'scan','workspace_scan','add','select','import_owned','import_gca','choose','game','remove','configure','jsaux_configure','jsaux_prepare','prepare','retry','install','repair','uninstall','verify','unused','purge','tools','save_key','update_install'}:
                    raise ScreensaverError('Finish or cancel the task first','busy')
                if action=='workspace_scan':service.refresh_games(include_new=False);return self._status()
                if self.jsaux.busy() and action in {'scan','save_key','add','select','import_owned','import_gca','choose','game','remove','verify','unused','purge','tools'}:
                    raise ValueError('Wait for identities preparation, or cancel it first')
                if action=='state':return self._status()
                if self.updater.phase=='installing' and action in {'prepare','retry','install','repair','jsaux_prepare','tools'}:
                    raise UpdateError('update_busy')
                if action.startswith('update_'):
                    updater=self.updater
                    if action=='update_configure':updater.configure(payload.get('patch',{}))
                    elif action=='update_check':updater.check()
                    elif action=='update_prepare':updater.prepare()
                    elif action=='update_cancel':updater.cancel()
                    elif action=='update_install':
                        if payload.get('confirm') is not True:raise ValueError('Confirm the Decky restart first')
                        if self.service._playing() or self.service._busy() or self.jsaux.busy():raise UpdateError('update_game_or_preparation')
                        if updater.phase!='ready' or payload.get('confirmation')!=updater.confirmation:raise UpdateError('update_confirmation')
                        self.preview.close();self.jsaux.stop();updater.install(payload.get('confirmation',''))
                    else:raise ValueError('Unknown update action')
                    return self._status()
                if action=='session':
                    ids=payload.get('ids')
                    if not isinstance(ids,list) or len(ids)>32 or any(type(n) is not int or not 0<n<=0xffffffff for n in ids):raise ValueError('Invalid game session')
                    self._running={n:True for n in ids};return None
                if action=='jsaux_recover':self.jsaux.recover();return self._status()
                if action=='suspend':
                    service.control('pause');self.jsaux.cancelled.set();self.jsaux.stop();self.preview.close();return None
                if action == 'jsaux_refresh':
                    self.jsaux.refresh(max_age=0 if payload.get('force') is True else 5)
                    if self.jsaux.options['enabled'] and (self.installer.jsaux_export or {}).get('relay')==self.player_relay.descriptor():self.player_relay.start()
                    return self._status()
                if action=='jsaux_configure':self.jsaux.configure(payload.get('patch',{}));return self._status()
                if action=='jsaux_prepare':self.jsaux.prepare();return self._status()
                if action=='jsaux_preview':return self.jsaux.preview()
                if action=='jsaux_game_preview':return self.jsaux.game_preview(number)
                if action=='import_gca':
                    if payload.get('confirm') is not True:raise ValueError('Confirm import first')
                    import_gca_studio(service,self.gca_import_root);return self._status()
                if action=='scan':service.refresh_games()
                elif action in {'library','workspace_library'}:
                    result=(self.workspace.library(payload.get('page',0),payload.get('page_size',8),payload.get('query',''),payload.get('filter','collection'),limit=payload.get('limit')) if action=='workspace_library'
                            else service.library(payload.get('page',0),6,payload.get('query',''),payload.get('filter','all')))
                    for entry in result['items']:
                        entry['thumbnail_url']=thumbnail(entry)
                        relative=entry.get('media',{}).get('thumbnail')
                        if relative:
                            try:
                                path=service.catalog.managed(relative,True)
                                if path.stat().st_size<=256*1024:
                                    raw=path.read_bytes()
                                    if raw.startswith(b'\xff\xd8'):entry['thumbnail_url']='data:image/jpeg;base64,'+base64.b64encode(raw).decode()
                            except (OSError,ScreensaverError):pass
                    if action=='workspace_library':result['items']=[self.workspace.overlay(g) for g in result['items']]
                    return result
                elif action=='save_key':
                    if service._busy():raise ValueError('Pause preparation before changing the key')
                    self.provider.save(payload.get('key'));service.refresh_key_state()
                elif action=='validate_key':service.validate_key()
                elif action=='search':return service.search(payload.get('query',''))
                elif action=='add':service.add(payload.get('id'))
                elif action=='select':service.select(payload.get('kind'),payload.get('query',''),payload.get('filter','all'))
                elif action=='import_owned':service.import_owned(payload.get('key'),payload.get('profile',''))
                elif action=='candidates':return service.candidates(number,payload.get('role','animation'))
                elif action=='details':return service.game_details(number)
                elif action=='choose':service.choose(number,payload.get('asset_id'),payload.get('role','animation'))
                elif action=='game':service.update_game(number,payload.get('patch',{}))
                elif action=='configure':
                    patch=payload.get('patch',{})
                    # Preserve the user's TV preference; a synced EXPORT inhibits
                    # shuffle without rewriting this setting.
                    if self.jsaux.busy():raise ValueError('Wait for identities preparation')
                    service.configure(patch)
                elif action in {'prepare','retry'}:
                    if self.jsaux.busy():raise ValueError('Wait for identities preparation')
                    self.preview.quiesce()
                    self.jsaux.refresh()
                    self._status();service.prepare(number,retry=action=='retry')
                elif action in {'pause','resume','cancel'}:service.control(action)
                elif action=='remove':
                    if payload.get('confirm') is not True:raise ValueError('Confirm removal first')
                    service.remove(number)
                elif action=='inspect_installation':
                    if service._busy() or self.jsaux.busy():raise ValueError('Finish preparation first')
                    self.installer.status(True,True)
                elif action in {'install','repair','uninstall'}:
                    if service._busy() or self.jsaux.busy():raise ValueError('Finish preparation first')
                    if payload.get('confirm') is not True:raise ValueError('Confirm installation changes first')
                    self.preview.quiesce()
                    self.jsaux.stop()
                    if action=='uninstall':self.installer.uninstall();self.player_relay.close()
                    else:self.installer.install(payload.get('language','en'))
                elif action=='preview':
                    request_id=payload.get('request_id')
                    if request_id is not None and (not isinstance(request_id,str) or not 16<=len(request_id)<=100 or not request_id.isalnum()):raise ScreensaverError('Invalid preview request','invalid_setting')
                    return self.preview.open(number,request_id=request_id)
                elif action=='close_preview':self.preview.close()
                elif action in {'verify','unused','purge'}:
                    self.preview.quiesce()
                    jsaux_cleanup=None
                    if action=='purge':
                        if payload.get('confirm') is not True:raise ValueError('Confirm deletion first')
                        if service._busy():raise ValueError('Finish preparation first')
                        self.installer.uninstall()
                        self.player_relay.close()
                        jsaux_cleanup=self.jsaux.purge()
                    service.maintenance(action,payload.get('confirm') is True)
                    if jsaux_cleanup:
                        for key in ('files','bytes'):service.last_cleanup[key]+=jsaux_cleanup[key]
                elif action=='tools':
                    if service._busy():raise ValueError('Finish preparation first')
                    method={'install':self.tools.start,'verify':self.tools.verify,'cancel':self.tools.cancel}.get(payload.get('action'))
                    if not method:raise ValueError('Invalid tools action')
                    method()
                elif action=='diagnostic':
                    report=dict(version=VERSION,activity=self._activity(),discovery=self.discovery.diagnostic_snapshot(),studio=service.diagnostic_snapshot(),workspace=self.workspace.summary(),jsaux=self.jsaux.status(),jsaux_delivery=self.jsaux.diagnostic_snapshot(payload.get('relay')),tools=self.tools.status(),installation=self.installer.status(),events=self._events)
                    report['jsaux_delivery']['steam_browser']=collect_cef(self.installer.boundary.steam_root)
                    report['artwork']=image_diagnostic(payload.get('artwork'))
                    report['jsaux_delivery']['local_checks']=self.player_relay.diagnostic_check() if self.player_relay.snapshot()['running'] else dict(listener=False,browser_evidence=False)
                    update=self.updater.status();report['updates']={k:update[k] for k in ('channel','phase','error','installed_version','available_version','repository_state','repository_error','repository_checked_at')}
                    # Preserve every field formerly sent in the online JSAUX
                    # report, alongside the wider local plugin diagnostics.
                    delivery=report['jsaux_delivery']
                    report.update({key:value for key,value in delivery.items() if key not in report})
                    report['workflow']=report['activity']
                    path=self.root.parent/'diagnostic.json';atomic_json(path,report)
                    return dict(saved=True,path=str(path),report=report)
                else:raise ValueError('Unknown action')
                return self._status()
            except (ScreensaverError,BrokerError,UpdateError) as error:
                self._event('request_error',code=error.code)
                # Decky replaces Python exception messages with a generic
                # "Unexpected error". Carry this expected admission refusal
                # as bounded data so the UI can explain how to continue.
                if error.code in {'GAME_RUNNING','game_running'} or action in {'workspace_select_all','workspace_deselect_all','workspace_undo_selection','workspace_delete_collection','workspace_reorder'}:
                    return dict(schema='das-action-error-v1',ok=False,error='GAME_RUNNING' if error.code=='game_running' else error.code)
                raise ValueError(error.code) from None

    async def _unload(self):
        self._closed=True
        def close():
            deadline=time.monotonic()+3
            for obj,method in ((getattr(self,'workspace',None),'shutdown'),(getattr(self,'updater',None),'shutdown'),(getattr(self,'jsaux',None),'shutdown'),(getattr(self,'player_relay',None),'close'),(getattr(self,'service',None),'shutdown'),(getattr(self,'tools',None),'shutdown'),(getattr(self,'preview',None),'close')):
                if obj:
                    try:getattr(obj,method)(timeout=max(0,deadline-time.monotonic()))
                    except Exception:pass
        await asyncio.to_thread(close)
