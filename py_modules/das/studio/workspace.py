"""Reversible UI preferences and versioned drafts. No decoder/USB in status."""
import copy
import hashlib
import json
import re
import threading
from uuid import uuid4
from das.core.catalog import ScreensaverError, atomic_json
from .storage import read_object, crop
from .problems import game_problem,skipped_media
from .media import still_motion_spec
from .membership import member, included
from das.core.jobs import _safe_asset
from .discovery import normalized, thumbnail


class CollectionWorkspace:
    def __init__(self, service, installer, delegation):
        self.service=service;self.store=service.catalog;self.installer=installer;self.delegation=delegation
        self.lock=threading.RLock();self.stop=threading.Event();self.thread=None
        self.path=self.store.managed('workspace-v1.json')
        self._selection_undo=None
        self.data=dict(schema=1,mode='collection',layout='comfort',drafts={},task=dict(state='idle',error=''))
        try:
            saved=read_object(self.path,8*1024*1024)
            if saved and saved.get('schema')==1:
                if saved.get('mode') in {'collection','classic'}:self.data['mode']=saved['mode']
                if saved.get('layout') in {'comfort','compact','list'}:self.data['layout']=saved['layout']
                drafts=saved.get('drafts',{})
                if isinstance(drafts,dict) and len(drafts)<=2000:
                    for key,value in drafts.items():
                        if isinstance(key,str) and key.lstrip('-').isdigit() and isinstance(value,dict) and isinstance(value.get('patch'),dict):
                            try:
                                self.data['drafts'][key]=dict(revision=str(value.get('revision',''))[:64],patch=self._validated_patch(value['patch']))
                            except (ValueError,TypeError,KeyError,OverflowError,ScreensaverError):
                                self.data['task']=dict(state='error',error='workspace_recovered')
                task=saved.get('task',{})
                if isinstance(task,dict) and task.get('state') in {'preparing','applying','paused','partial','done','error','cancelled'}:
                    self.data['task']=dict(state='paused' if task['state'] in {'preparing','applying'} else task['state'],error='interrupted' if task['state'] in {'preparing','applying'} else str(task.get('error',''))[:80],**self._task_details(task))
        except (ValueError,TypeError,OSError,ScreensaverError):
            # Keep the old file for recovery. A corrupt optional UI cannot break
            # the existing Studio or authorize an export.
            self.data['task']=dict(state='error',error='workspace_recovered')

    def _save(self):atomic_json(self.path,self.data)

    @staticmethod
    def _validated_patch(raw):
        patch=copy.deepcopy(raw)
        if not isinstance(patch,dict) or set(patch)-{'asset','manual','pending_change','still_mode','cover_asset','cover_manual','cover_pending','logo_asset','logo_manual','logo_pending','panel_asset','panel_manual','panel_pending','excluded','collection_member','crop','branding','cover_position','faceplate_crop'}:raise ScreensaverError('Invalid saved draft','invalid_setting')
        for key in ('asset','cover_asset','logo_asset','panel_asset'):
            if key in patch:patch[key]=_safe_asset(patch[key])
        if 'crop' in patch:patch['crop']=crop(patch['crop'])
        for key in ('manual','pending_change','cover_manual','cover_pending','logo_manual','logo_pending','panel_manual','panel_pending','excluded','collection_member'):
            if key in patch and type(patch[key]) is not bool:raise ScreensaverError('Invalid saved flag','invalid_setting')
        if 'still_mode' in patch and patch['still_mode'] not in ('inherit','motion','fixed'):raise ScreensaverError('Invalid saved motion','invalid_setting')
        branding=patch.get('branding')
        if isinstance(branding,dict) and branding.get('position')=='beside-title':branding['position']='inherit'
        if branding is not None and (not isinstance(branding,dict) or set(branding)!={'mode','position'} or branding['mode'] not in ('inherit','title','logo','both','hidden') or branding['position'] not in ('inherit','top-left','top-right','bottom-left','bottom-right')):raise ScreensaverError('Invalid saved branding','invalid_setting')
        if 'cover_position' in patch and patch['cover_position'] not in ('bottom-left','bottom-right','top-left','top-right'):raise ScreensaverError('Invalid saved cover position','invalid_setting')
        point=patch.get('faceplate_crop')
        if point is not None and (not isinstance(point,dict) or set(point)!={'x','y'} or any(type(point[k]) not in (int,float) or not 0<=point[k]<=100 for k in point)):raise ScreensaverError('Invalid saved crop','invalid_setting')
        return patch

    def busy(self):return bool(self.thread and self.thread.is_alive())

    def ensure_idle(self):
        if (self.busy() or self.service._busy() or self.delegation.busy()
                or self.data['task'].get('state')=='paused'
                or self.service.job.get('state') in {'paused','paused_game'}):
            raise ScreensaverError('Finish or cancel preparation first','busy')

    def selection_undo(self):
        value=self._selection_undo
        if value and value['catalog_revision']!=self.store.revision:
            self._selection_undo=None;value=None
        return dict(count=value['count'],token=value['token']) if value else None

    def deselect_all(self):
        """One global draft transaction; never uninstall, decode or transfer."""
        with self.lock:
            self.ensure_idle()
            entries=[g for g in self.store.games() if included(self.overlay(g))]
            if not entries:return
            before=copy.deepcopy(self.data)
            try:
                for game in entries:
                    key=str(game['appid']);previous=self.data['drafts'].get(key,{}).get('patch',{})
                    merged={**previous,'collection_member':False,'excluded':False}
                    if merged:self.data['drafts'][key]=dict(revision=uuid4().hex,patch=merged)
                    else:self.data['drafts'].pop(key,None)
                if len(self.data['drafts'])>2000:raise ScreensaverError('Collection metadata is too large','storage_limit')
                self._save()
            except BaseException:self.data=before;raise
            self._selection_undo=dict(token=uuid4().hex,count=len(entries),drafts=before['drafts'],catalog_revision=self.store.revision)

    def select_all(self,query='',appids=None):
        """Select a complete result set in one draft write, without preparing it."""
        with self.lock:
            self.ensure_idle()
            if appids is None:
                if not isinstance(query,str) or len(query)>160:raise ScreensaverError('Invalid search','invalid_setting')
                entries=[g for g in self.store.games() if g.get('installed') and normalized(query) in normalized(g.get('name',''))]
            else:
                if not isinstance(appids,list) or len(appids)>100 or any(type(n) is not int or not 0<n<=0xffffffff for n in appids):
                    raise ScreensaverError('Invalid result set','invalid_setting')
                entries=[self.store.get(n) for n in dict.fromkeys(appids)]
                if any(not g for g in entries):raise ScreensaverError('Search for this game first','not_installed')
            before=copy.deepcopy(self.data)
            try:
                for game in entries:
                    if included(self.overlay(game)):continue
                    key=str(game['appid']);merged={**self.data['drafts'].get(key,{}).get('patch',{}),'collection_member':True,'excluded':False}
                    for flag in ('collection_member','excluded'):
                        base=self.member(game) if flag=='collection_member' else bool(game.get(flag))
                        if merged.get(flag)==base:merged.pop(flag,None)
                    if merged:self.data['drafts'][key]=dict(revision=uuid4().hex,patch=merged)
                    else:self.data['drafts'].pop(key,None)
                if len(self.data['drafts'])>2000:raise ScreensaverError('Collection metadata is too large','storage_limit')
                if self.data!=before:self._save();self._selection_undo=None
            except BaseException:self.data=before;raise

    def undo_selection(self,token):
        with self.lock:
            self.ensure_idle()
            if not self.selection_undo() or not isinstance(token,str) or token!=self._selection_undo['token']:
                raise ScreensaverError('Selection has changed','selection_undo_expired')
            before=copy.deepcopy(self.data)
            try:self.data['drafts']=copy.deepcopy(self._selection_undo['drafts']);self._save()
            except BaseException:self.data=before;raise
            self._selection_undo=None

    def _clear_collection_metadata(self):
        """Called after export ownership validation; return rename-failure rollback."""
        with self.lock,self.store.lock:
            before=copy.deepcopy(self.data);catalog=copy.deepcopy(self.store.data)
            revision=self.store.revision;undo=self._selection_undo
            workspace_existed=self.path.exists()
            def rollback():
                with self.lock,self.store.lock:
                    atomic_json(self.store.path,{**catalog,'revision':revision})
                    if workspace_existed:atomic_json(self.path,before)
                    else:self.path.unlink(missing_ok=True)
                    self.store.data=copy.deepcopy(catalog);self.store.revision=revision
                    self.data=copy.deepcopy(before);self._selection_undo=undo
            try:
                for game in self.store.data['games'].values():game.update(collection_member=False,excluded=False)
                self.store.save()
                self.data.update(drafts={},task=dict(state='idle',error=''));self._save()
            except BaseException:rollback();raise
            self._selection_undo=None
            return rollback

    def delete_collection(self):
        self.ensure_idle()
        self.installer.uninstall(metadata=self._clear_collection_metadata)

    def order_snapshot(self):
        """All collection members, including drafts/hidden rows; no media reads."""
        with self.lock,self.store.lock:
            games=[self.overlay(g) for g in self.store.games() if self.member(self.overlay(g))]
            ids=[g['appid'] for g in games]
            revision=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
            return dict(revision=revision,items=[dict(appid=g['appid'],name=g.get('name',''),thumbnail_url=thumbnail(g)) for g in games])

    def reorder(self,appids,revision):
        """Persist only an exact, current permutation. Installed files stay intact."""
        with self.lock,self.store.lock:
            self.ensure_idle()
            if (not isinstance(appids,list) or len(appids)>2000 or
                any(type(n) is not int or not 0<abs(n)<=0xffffffff for n in appids) or len(set(appids))!=len(appids)):
                raise ScreensaverError('Invalid collection order','invalid_setting')
            snapshot=self.order_snapshot();current=[g['appid'] for g in snapshot['items']]
            if not isinstance(revision,str) or revision!=snapshot['revision'] or set(appids)!=set(current):
                raise ScreensaverError('Collection changed; reload its order','collection_order_changed')
            if appids==current:return
            before=copy.deepcopy(self.store.data)
            try:
                ordered=iter(appids);members=set(current)
                self.store.data['game_order']=[next(ordered) if n in members else n for n in self.store._ordered_ids()]
                self.store.save()
            except BaseException:self.store.data=before;raise
            self._selection_undo=None

    def preferences(self,patch):
        if not isinstance(patch,dict) or set(patch)-{'mode','layout'}:raise ScreensaverError('Invalid interface preference','invalid_setting')
        with self.lock:
            if 'mode' in patch and patch['mode'] not in ('collection','classic'):raise ScreensaverError('Invalid interface','invalid_setting')
            if 'layout' in patch and patch['layout'] not in ('comfort','compact','list'):raise ScreensaverError('Invalid layout','invalid_setting')
            before=copy.deepcopy(self.data)
            try:self.data.update(patch);self._save()
            except BaseException:self.data=before;raise

    @staticmethod
    def member(g):return member(g)

    def pending(self,g,ready,include_panel=True):
        if (g.get('status') in {'skipped','missing'} or g.get('skip_reason')=='no_animation' or g.get('error')=='animation_missing') and not self.store.options()['static_fallback'] and g.get('still_mode') not in {'motion','fixed'}:return False
        options=self.store.options();mode=g.get('branding',{}).get('mode','inherit')
        logo=mode in {'logo','both'} or mode=='inherit' and options['show_logo']
        panel=include_panel and getattr(self.delegation,'options',{}).get('enabled',False)
        # Recipe changes need the normal prepare/install action, not a forced
        # rebuild or a fake artwork error. Metadata only: no decoder or I/O.
        media=g.get('media',{})
        blocked_background=bool(skipped_media(g,'background') and not g.get('pending_change') and g.get('selection_policy')==64
            and (not options['static_fallback'] or g.get('still_fallback_tried')))
        if blocked_background and not ready:return False
        motion_pending=(g.get('animated') is False and media.get('tv')
                        and (bool(g.get('motion_error')) or
                             not options['reduced_motion'] and g.get('still_mode')!='fixed'
                             and g.get('still_motion_config')!=still_motion_spec(options)))
        return bool(g.get('pending_change') or options['show_cover'] and g.get('cover_pending')
                    or logo and g.get('logo_pending') or panel and g.get('panel_pending') or motion_pending or not ready and not blocked_background)

    def summary(self):
        with self.lock:
            entries=self.store.games();drafts=self.data['drafts'];pending=[];issues=[];members=[]
            for game in entries:
                g={**game,**copy.deepcopy(drafts.get(str(game['appid']),{}).get('patch',{}))}
                if not self.member(g):continue
                members.append(g)
                if g.get('excluded'):continue
                problem=game_problem(g,g['appid'] in self.service._ready)
                edited=str(g['appid']) in drafts
                if problem and not edited:issues.append(problem)
                if edited or not problem and self.pending(g,g['appid'] in self.service._ready):pending.append(g['appid'])
            installation=self.installer.status()
            count=installation.get('scene_count',0)
            return dict(mode=self.data['mode'],layout=self.data['layout'],draft_count=len(drafts),
                installed_count=count if installation.get('installed') and type(count) is int and count>=0 else 0,
                member_count=len(members),included_count=sum(not g.get('excluded') for g in members),
                preview_count=sum(included(g) and g['appid'] in self.service._ready and g.get('status')=='ready' and not g.get('pending_change') for g in entries),
                pending_count=len(pending),pending_ids=pending[:2000],issues_count=len(issues),
                skipped_visual_count=sum(bool(p.get('skipped')) for p in issues),
                skipped_count=sum(not g.get('excluded') and (g.get('status')=='skipped' or not g.get('media',{}).get('tv') and (g.get('status')=='missing' or g.get('skip_reason')=='no_animation' or g.get('error')=='animation_missing')) and not self.store.options()['static_fallback'] for g in members),
                selection_undo=self.selection_undo(),task={**copy.deepcopy(self.data['task']),'worker_active':self.busy()})

    def overlay(self,g):
        if not g:return {}
        with self.lock:
            value=self.data['drafts'].get(str(g['appid']))
            result={**g,**copy.deepcopy((value or {}).get('patch',{})),
                'workspace_draft':bool(value),'collection_member':self.member({**g,**((value or {}).get('patch',{}))})}
            result['problem']=None if value else game_problem(result,g['appid'] in self.service._ready)
            if result.get('status') in {'skipped','missing'} and self.store.options()['static_fallback']:
                result['status']='pending'
            return result

    def library(self,page=0,size=8,query='',filter='collection',limit=None):
        query=normalized(str(query)[:160]);size=max(1,min(12,int(size)))
        rows=[self.overlay(g) for g in self.store.games()]
        rows=[g for g in rows if query in normalized(g.get('name','')) and
              (filter=='all' or filter=='collection' and g['collection_member'] or filter=='installed' and g.get('installed')
               or filter=='attention' and self.member(g) and game_problem(g,g['appid'] in self.service._ready)
               or filter=='pending' and self.member(g) and (g.get('workspace_draft') or self.pending(g,g['appid'] in self.service._ready))
               or filter=='included' and self.member(g) and not g.get('excluded'))]
        if filter in {'all','installed'}:rows.sort(key=lambda g:(g.get('name','').casefold(),g['appid']))
        page=min(max(0,int(page)),max(0,(len(rows)-1)//size))
        if limit is not None:
            if type(limit) is not int or not 10<=limit<=2000 or limit%10:raise ScreensaverError('Invalid list limit','invalid_setting')
            return dict(items=rows[:limit],total=len(rows),page=max(0,min(limit,len(rows))-1)//10,page_size=10)
        return dict(items=rows[page*size:(page+1)*size],total=len(rows),page=page,page_size=size)

    def draft_patch(self,number,payload):
        if not self.store.get(number):raise ScreensaverError('Unknown game','not_installed')
        if not isinstance(payload,dict) or set(payload)-{'choices','crop','excluded','collection_member','still_mode','branding','cover_position','faceplate_crop'}:
            raise ScreensaverError('Invalid choices','invalid_setting')
        clean={};choices=payload.get('choices',{})
        if not isinstance(choices,dict) or set(choices)-{'animation','still_tv','cover','logo','panel'}:raise ScreensaverError('Invalid artwork','invalid_asset')
        if 'animation' in choices and 'still_tv' in choices:raise ScreensaverError('Choose one background','invalid_asset')
        for role,asset_id in choices.items():
            if type(asset_id) is not int:raise ScreensaverError('Invalid artwork','invalid_asset')
            candidates=self.service._candidates.get((number,role),[])
            matches=[a for a in candidates if a['id']==asset_id]
            if len(matches)!=1:raise ScreensaverError('Choose a listed image','invalid_asset')
            asset=_safe_asset(matches[0])
            if role in {'animation','still_tv'}:clean.update(asset=asset,manual=True,pending_change=True,still_mode='motion' if role=='still_tv' else 'inherit')
            else:clean.update({role+'_asset':asset,role+'_manual':True,role+'_pending':True})
        for key in ('excluded','collection_member'):
            if key in payload:
                if type(payload[key]) is not bool:raise ScreensaverError('Expected boolean','invalid_setting')
                clean[key]=payload[key]
        if 'crop' in payload:clean['crop']=crop(payload['crop'])
        if 'still_mode' in payload:
            if payload['still_mode'] not in ('inherit','motion','fixed'):raise ScreensaverError('Invalid still mode','invalid_setting')
            clean['still_mode']=payload['still_mode']
        if 'branding' in payload:
            v=payload['branding']
            if not isinstance(v,dict) or set(v)!={'mode','position'} or v['mode'] not in {'inherit','title','logo','both','hidden'} or v['position'] not in {'inherit','top-left','top-right','bottom-left','bottom-right'}:raise ScreensaverError('Invalid branding','invalid_setting')
            clean['branding']=dict(v)
        if 'cover_position' in payload:
            if payload['cover_position'] not in ('bottom-left','bottom-right','top-left','top-right'):raise ScreensaverError('Invalid cover position','invalid_setting')
            clean['cover_position']=payload['cover_position']
        if 'faceplate_crop' in payload:
            v=payload['faceplate_crop']
            if not isinstance(v,dict) or set(v)!={'x','y'} or any(type(v[k]) not in (int,float) or not 0<=v[k]<=100 for k in v):raise ScreensaverError('Invalid crop','invalid_setting')
            clean['faceplate_crop']=dict(v)
        return clean

    def save_draft(self,number,payload,reconcile_membership=False):
        clean=self.draft_patch(number,payload)
        with self.lock:
            previous=self.data['drafts'].get(str(number),{}).get('patch',{})
            before=copy.deepcopy(self.data)
            try:
                merged={**previous,**clean}
                if reconcile_membership:
                    if set(clean)-{'collection_member','excluded'}:raise ScreensaverError('Invalid membership change','invalid_setting')
                    original=self.store.get(number)
                    if clean.get('collection_member') is False and not self.member(original):merged['excluded']=bool(original.get('excluded'))
                    for key in ('collection_member','excluded'):
                        base=self.member(original) if key=='collection_member' else bool(original.get('excluded'))
                        if key in merged and merged[key]==base:merged.pop(key)
                if merged:self.data['drafts'][str(number)]=dict(revision=uuid4().hex,patch=merged)
                else:self.data['drafts'].pop(str(number),None)
                self._save()
            except BaseException:self.data=before;raise
            self._selection_undo=None

    def discard(self,number):
        with self.lock:self.data['drafts'].pop(str(number),None);self._save();self._selection_undo=None

    def commit(self):
        """One metadata transaction, only after both preparation workers stop."""
        if self.service._busy() or self.delegation.busy():raise ScreensaverError('Preparation still active','busy')
        with self.lock,self.store.lock:
            original=copy.deepcopy(self.store.data);old_ready=set(self.service._ready)
            values=copy.deepcopy(self.data['drafts'])
            try:
                for number,value in values.items():
                    game=self.store.data['games'].get(number)
                    if not game:continue
                    # A saved draft is input, never trusted executable state.
                    patch=self._validated_patch(value['patch'])
                    game.update(copy.deepcopy(patch))
                    # Old scene bytes remain available; only the working recipe
                    # changes. Installed Steam snapshot is not touched here.
                if values:self.store.save()
            except BaseException:
                self.store.data=original;self.service._ready=old_ready;raise
            for key,value in values.items():
                if self.data['drafts'].get(key,{}).get('revision')==value['revision']:self.data['drafts'].pop(key,None)
            self._save()
            self._selection_undo=None

    @staticmethod
    def _task_details(value):
        """Old task records remain readable, without trusting arbitrary fields."""
        choices=dict(outcome={'installed','unchanged','empty'},operation={'prepare','install'},
            tv_state={'prepared','installed','unchanged','empty'},
            faceplate_state={'disabled','unavailable','prepared','installed','repair_required'},
            stage={'tv','faceplate','installation'})
        result={key:value[key] for key,allowed in choices.items()
                if isinstance(value.get(key),str) and value[key] in allowed}
        if type(value.get('repair_faceplate')) is bool:result['repair_faceplate']=value['repair_faceplate']
        if type(value.get('skipped_count')) is int and 0<=value['skipped_count']<=2000:result['skipped_count']=value['skipped_count']
        return result

    def task(self,state,error='',**details):
        with self.lock:
            error=error if not error or isinstance(error,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',error) else 'unexpected_error'
            previous=self._task_details(self.data['task'])
            previous.pop('outcome',None)
            value=dict(state=state,error=error,**self._task_details({**previous,**details}))
            if self.data['task']==value:return
            self.data['task']=value;self._save()

    def _faceplate_state(self):
        if not getattr(self.delegation,'options',{}).get('enabled'):return 'disabled'
        if not getattr(self.delegation,'detected',False) or not getattr(self.delegation,'compatible',False):return 'unavailable'
        status=self.delegation.status()
        if (not status.get('prepared',{}).get('ready') or status.get('prepared',{}).get('power_upgrade_required')
            or status.get('reason') in {'CONTENT_INVALID','PREPARATION_POWER_REQUIRED','PREPARED_FILE_MISSING'}):return 'repair_required'
        return 'installed' if status.get('installed') else 'prepared'

    def _wait_faceplate(self):
        """Wait for local compile/registration only, never a USB transfer."""
        while self.delegation.busy():
            if self.stop.wait(.15):return False
            if self.service._playing():
                self.delegation.cancelled.set()
        return not self.stop.is_set()

    def start(self,language='en',install_only=False,resume=False,mode='missing',repair_faceplate=False,independent=False):
        if mode not in {'missing','all'}:raise ScreensaverError('Invalid preparation mode','invalid_setting')
        if type(repair_faceplate) is not bool or repair_faceplate and not install_only:
            raise ScreensaverError('Faceplate repair requires the installation workflow','invalid_setting')
        if type(independent) is not bool or independent and (resume or mode!='missing'):
            raise ScreensaverError('Invalid independent playback confirmation','invalid_setting')
        with self.lock:
            if self.busy() or self.service._busy() or self.delegation.busy():raise ScreensaverError('A task is already active','busy')
            if self.service._playing():raise ScreensaverError('Close the running game first','GAME_RUNNING')
            if not resume:
                if not self.service._scanned:self.service.refresh_games(include_new=False)
                self.commit()
            tv_pending=any(self.pending(g,g['appid'] in self.service._ready,include_panel=False)
                for g in self.store.games() if self.member(g) and not g.get('excluded'))
            unhandled=any(problem and not problem.get('skipped') for g in self.store.games() if included(g)
                          for problem in [game_problem(g,g['appid'] in self.service._ready)])
            if install_only and (tv_pending or unhandled):
                raise ScreensaverError('Prepare or repair the selected games first','not_ready')
            if independent:
                if not getattr(self.delegation,'options',{}).get('enabled'):
                    raise ScreensaverError('Enable Faceplate output first','invalid_setting')
                self.delegation.configure(dict(mode='async'))
            self.stop.clear();self.task('applying' if install_only else 'preparing',
                operation='install' if install_only else 'prepare',stage='installation' if install_only else 'tv',
                tv_state='prepared' if self.service.status()['ready_count'] else 'empty',faceplate_state=self._faceplate_state(),repair_faceplate=repair_faceplate)
            def work():
                try:
                    repair_known=getattr(self.delegation,'reason','') in {'CONTENT_INVALID','PREPARATION_POWER_REQUIRED','PREPARED_FILE_MISSING'}
                    panel_thread=getattr(self.delegation,'thread',None)
                    # Discover once for this explicit update, not from polling.
                    # Saved settings alone are not proof the panel is present.
                    refresh=getattr(self.delegation,'refresh',None)
                    if getattr(self.delegation,'options',{}).get('enabled') and callable(refresh):refresh()
                    if not install_only:
                        if resume:self.service.control('resume')
                        else:self.service.prepare(force=mode=='all')
                        while not self.stop.wait(.15):
                            # _busy() intentionally clears before after_prepare;
                            # wait for the real thread too, including that callback.
                            if self.service.thread and self.service.thread.is_alive():continue
                            if self.delegation.busy():
                                self.task('preparing',stage='faceplate',operation='install',tv_state='prepared')
                                continue
                            if self.service.job['state'] in {'paused','paused_game'}:
                                self.task('paused',self.service.job.get('error',''));continue
                            if self.service.job['state']!='complete':self.task('cancelled');return
                            break
                        if self.stop.is_set():return
                        self.task('preparing',skipped_count=self.service.job.get('skipped_count',0))
                        problems=[game_problem(g,g['appid'] in self.service._ready) for g in self.store.games() if included(g)]
                        if any(p and not p.get('skipped') for p in problems):
                            self.task('partial',tv_state='prepared' if self.service.status()['ready_count'] else 'empty',faceplate_state=self._faceplate_state());return
                    if self.stop.is_set():return
                    if not self.service.status()['ready_count']:
                        retained=bool(self.installer.status().get('installed'))
                        self.task('done',outcome='unchanged' if retained else 'empty',
                            tv_state='unchanged' if retained else 'empty',faceplate_state=self._faceplate_state());return
                    # TV-ready repairs use the same final installation path. No
                    # second TV encode and no display acquisition/USB write.
                    faceplate=self._faceplate_state()
                    panel_attempted=getattr(self.delegation,'thread',None) is not panel_thread
                    if (faceplate not in {'disabled','unavailable'} and (install_only or not panel_attempted)
                        and (faceplate=='repair_required' or repair_faceplate or repair_known)):
                        self.task('preparing',stage='faceplate',tv_state='prepared',faceplate_state=faceplate)
                        self.delegation.prepare()
                        if not self._wait_faceplate():return
                        panel_attempted=True
                        faceplate=self._faceplate_state()
                    if self.service._playing():self.task('paused','GAME_RUNNING',operation='install',tv_state='prepared',faceplate_state=faceplate);return
                    if faceplate=='repair_required':
                        self.task('partial',getattr(self.delegation,'reason','') or 'JSAUX_PREPARATION_REQUIRED',tv_state='prepared',faceplate_state=faceplate);return
                    installation=self.installer.status()
                    if (not repair_faceplate and not panel_attempted and installation.get('installed') and not installation.get('needs_update') and not installation.get('needs_repair')
                        and faceplate not in {'prepared','repair_required'}):
                        self.task('done',outcome='unchanged',tv_state='unchanged',faceplate_state=faceplate);return
                    self.task('applying',stage='installation',operation='install')
                    self.installer.install(language)
                    self.task('done',outcome='installed',stage='installation',tv_state='installed',faceplate_state=self._faceplate_state())
                except Exception as error:
                    code=getattr(error,'code','unexpected_error')
                    if self.data['task'].get('stage')=='faceplate':
                        self.task('partial',code,tv_state='prepared',faceplate_state='repair_required')
                    else:self.task('error',code)
            self.thread=threading.Thread(target=work,name='das-collection-workflow',daemon=True);self.thread.start()

    def resume(self,language='en'):
        """Rebuild orchestration after restart, without committing newer drafts."""
        with self.lock:
            if self.busy() or self.data['task']['state']!='paused':return False
            install_only=self.data['task'].get('operation')=='install'
            if not install_only and self.service.job['state'] not in {'paused','paused_game'}:return False
            self.start(language,install_only=install_only,resume=True,repair_faceplate=self.data['task'].get('repair_faceplate',False))
            return True

    def cancel(self):
        self.stop.set()
        if self.data['task']['state']!='applying':self.task('cancelled')

    def shutdown(self,timeout=3):
        self.stop.set()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(max(0,timeout))
