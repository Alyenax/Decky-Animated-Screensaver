"""Versioned metadata, recoverable migration and exact managed-file boundaries."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path, PurePosixPath
import threading
from das.core.catalog import atomic_json, file_sha256, ScreensaverError

DEFAULTS = dict(scene_seconds=24, shuffle=True, transition='crossfade', show_title=True,
    show_logo=True, show_cover=True, cover_position='bottom-right', framing='original',
    reduced_motion=False, smoothing=False, smoothing_mode='fast', smoothing_fps=30,
    max_video_mib=256, storage_mib=10240,
    name_display='logo', logo_position='bottom-left', artwork_credit=False,
    cover_credit=False, logo_credit=False,
    static_fallback=False)

def validate(patch):
    if not isinstance(patch, dict) or set(patch)-set(DEFAULTS):
        raise ScreensaverError('Unknown Studio setting', 'invalid_setting')
    enums = dict(transition={'crossfade','fade-black','cut'},
        cover_position={'bottom-left','bottom-right','top-right','top-left'},
        framing={'original','16:9','16:10'}, smoothing_mode={'fast','quality','blend'},
        name_display={'title','logo','both','hidden'},
        logo_position={'bottom-left','bottom-right','top-left','top-right'})
    ranges = dict(scene_seconds=(8,180), storage_mib=(256,32768), max_video_mib=(0,1000000))
    for key, value in patch.items():
        if key in enums:
            if not isinstance(value,str) or value not in enums[key]: raise ScreensaverError('Invalid setting','invalid_setting')
        elif key=='storage_mib' and type(value) is int and value==0:continue
        elif key in ranges:
            if type(value) is not int or not ranges[key][0] <= value <= ranges[key][1]: raise ScreensaverError('Invalid setting','invalid_setting')
        elif key == 'smoothing_fps':
            if type(value) is not int or value not in {24,30}: raise ScreensaverError('Invalid cadence','invalid_setting')
        elif type(value) is not bool: raise ScreensaverError('Expected boolean','invalid_setting')
    return copy.deepcopy(patch)

def crop(value):
    if not isinstance(value,dict) or value.get('mode') not in {'inherit','original','16:9','16:10'}:
        raise ScreensaverError('Invalid framing','invalid_setting')
    result={'mode':value['mode']}
    for axis in ('x','y'):
        v=value.get(axis,50)
        if type(v) not in (int,float) or not 0<=v<=100: raise ScreensaverError('Invalid framing','invalid_setting')
        result[axis]=v
    return result

def component(game):
    import re
    return game.get('appid') in {228980,1070560,1391110,1628350,4183110} or bool(re.match(
        r'^(steam\s*linux\s*runtime\b|steamworks\s+(common\s+)?redistributables?\b|proton($|[\s_-]*(\d|experimental|hotfix|next))|ge[- ]?proton\b)',
        str(game.get('name','')),re.I))

def read_object(path, maximum=8*1024*1024):
    path=Path(path)
    if not path.exists(): return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum:
        raise ScreensaverError('Unsafe metadata','unsafe_path')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict): raise ValueError('Invalid metadata object')
    return value

class Store:
    def __init__(self, root, legacy=None):
        self.root=Path(root).absolute()
        if self.root.is_symlink(): raise ScreensaverError('Unsafe Studio root','unsafe_path')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=self.root.resolve(); self.path=self.root/'studio.json'; self.lock=threading.RLock()
        self.warning=''; self.legacy=Path(legacy).resolve() if legacy else None
        try: data=read_object(self.path)
        except (ValueError,UnicodeError):
            import time
            backup=self.path.with_name('studio.json.corrupt-'+str(time.time_ns()))
            self.path.rename(backup); data=None; self.warning='catalog_recovered'
        if data is not None and data.get('schema') != 1:
            raise ScreensaverError('Unsupported Studio schema; original preserved','unsupported_schema')
        self.data=data or dict(schema=1,games={},options=dict(DEFAULTS))
        self.data.setdefault('games',{})
        if not isinstance(self.data['games'],dict): raise ScreensaverError('Invalid Studio catalog','invalid_catalog')
        for key,entry in self.data['games'].items():
            if (not isinstance(entry,dict) or type(entry.get('appid')) is not int or str(entry['appid'])!=key
                    or not -0xffffffff<=entry['appid']<=0xffffffff or entry['appid']==0
                    or not isinstance(entry.get('name',''),str) or not isinstance(entry.get('media',{}),dict)
                    or not isinstance(entry.get('sha256',{}),dict)):
                raise ScreensaverError('Invalid Studio entries; original preserved','invalid_catalog')
        valid=dict(DEFAULTS)
        saved_options=self.data.get('options',{})
        for key,value in (saved_options if isinstance(saved_options,dict) else {}).items():
            if key in {'cover_position','logo_position'} and value=='beside-title':value=DEFAULTS[key]
            try: valid.update(validate({key:value}))
            except ScreensaverError: pass
        self.data['options']=valid
        for entry in self.data['games'].values():
            branding=entry.get('branding')
            if isinstance(branding,dict) and branding.get('position')=='beside-title':branding['position']='inherit'
        if (not isinstance(saved_options,dict) or 'name_display' not in saved_options) and not valid['show_logo']:
            self.data['options']['name_display']='title' if valid['show_title'] else 'hidden'
        saved_revision=self.data.get('revision',0)
        self.revision=saved_revision if type(saved_revision) is int and saved_revision>=0 else 0
        if data is None: self._import_legacy()

    def _ordered_ids(self):
        # JSON object keys are deliberately sorted on disk. They cannot carry
        # playback order across a restart; keep that order in an explicit array.
        games=self.data['games']; saved=self.data.get('game_order',[])
        ordered=[]; seen=set()
        for number in saved if isinstance(saved,list) else []:
            if type(number) is int and str(number) in games and number not in seen:
                ordered.append(number); seen.add(number)
        for entry in games.values():
            number=entry['appid']
            if number not in seen: ordered.append(number); seen.add(number)
        return ordered

    def managed(self, relative, exists=False):
        if not isinstance(relative,str) or not relative or '\\' in relative:
            raise ScreensaverError('Unsafe Studio path','unsafe_path')
        pure=PurePosixPath(relative)
        if pure.is_absolute() or not pure.parts or str(pure)!=relative or any(p in {'.','..'} for p in pure.parts): raise ScreensaverError('Unsafe Studio path','unsafe_path')
        path=self.root.joinpath(*pure.parts)
        for p in (path,*path.parents):
            if p==self.root: break
            if p.is_symlink(): raise ScreensaverError('Studio links are not followed','unsafe_path')
        if not path.resolve().is_relative_to(self.root): raise ScreensaverError('Unsafe Studio path','unsafe_path')
        if exists and not path.is_file(): raise ScreensaverError('Prepared media missing','missing_media')
        return path

    def _import_legacy(self):
        if not self.legacy: return
        try: old=read_object(self.legacy/'catalog.json')
        except (ValueError,OSError,ScreensaverError): self.warning='legacy_catalog_preserved'; return
        if not old or not isinstance(old.get('games'),dict): return
        for entry in list(old['games'].values())[:2000]:
            if not isinstance(entry,dict) or type(entry.get('appid')) is not int or component(entry): continue
            number=entry['appid']
            self.data['games'][str(number)]={k:copy.deepcopy(entry[k]) for k in ('appid','name','installed','excluded','asset','manual') if k in entry}
            self.data['games'][str(number)].update(status='pending',legacy=True)
        old_options=old.get('options',{})
        for key in ('scene_seconds','shuffle','show_logo','storage_mib'):
            try: self.data['options'].update(validate({key:(old_options if isinstance(old_options,dict) else {})[key]}))
            except (KeyError,ScreensaverError): pass
        self.warning='legacy_imported' if self.data['games'] else ''
        self.save()

    def save(self):
        with self.lock:
            next_revision=self.revision+1
            order=self._ordered_ids()
            atomic_json(self.path,{**self.data,'revision':next_revision,'game_order':order})
            self.data['game_order']=order
            self.revision=next_revision

    def games(self):
        with self.lock: return copy.deepcopy([self.data['games'][str(number)] for number in self._ordered_ids()])

    def get(self, appid):
        with self.lock: return copy.deepcopy(self.data['games'].get(str(appid),{}))

    def options(self):
        with self.lock: return copy.deepcopy(self.data['options'])

    def update(self, appid, patch):
        with self.lock:
            before=copy.deepcopy(self.data)
            self.data['games'].setdefault(str(appid),dict(appid=appid)).update(copy.deepcopy(patch))
            try: self.save()
            except BaseException: self.data=before; raise
        return self.get(appid)

    def configure(self, patch):
        valid=validate(patch)
        if 'name_display' in valid:
            valid.update(show_logo=valid['name_display'] in {'logo','both'},show_title=valid['name_display']!='hidden')
        with self.lock:
            before=self.data['options']; self.data['options']={**before,**valid}
            try: self.save()
            except BaseException: self.data['options']=before; raise
        return self.options()

    def ready(self, entry, verify=False):
        if entry.get('status')!='ready' or entry.get('pending_change') or not (entry.get('animated') or self.options()['static_fallback'] or entry.get('still_mode') in {'motion','fixed'}): return False
        try:
            for key in ('tv','thumbnail'):
                path=self.managed(entry['media'][key],True)
                if not path.stat().st_size or verify and file_sha256(path)!=entry['sha256'][key]: return False
            return True
        except (ScreensaverError,KeyError,OSError): return False

    def usage(self):
        total=0
        for directory,dirs,files in os.walk(self.root,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
            for name in files:
                path=Path(directory)/name
                if path.is_file() and not path.is_symlink(): total+=path.stat().st_size
        return total
