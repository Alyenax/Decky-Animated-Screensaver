"""Explicit, credential-free settings backups. Media and installed exports are untouched."""
import copy
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timezone
from das.core.catalog import atomic_json, ScreensaverError
from das.studio.storage import validate, read_object, DEFAULTS
from das.jsaux.manager import DEFAULTS as PANEL_DEFAULTS

SCHEMA='das-settings-v1'
LIMIT=65536

def checked_path(path):
    path=Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ScreensaverError('Unsafe backup path','backup_path')
    return path

def validate_backup(raw):
    if not isinstance(raw,dict) or set(raw)!={'schema','options','faceplate','interface'} or raw['schema']!=SCHEMA:
        raise ScreensaverError('Invalid settings backup','backup_invalid')
    options=validate(raw['options'])
    if set(options)!=set(DEFAULTS):raise ScreensaverError('Incomplete settings backup','backup_invalid')
    panel=raw['faceplate']
    if not isinstance(panel,dict) or set(panel)!=set(PANEL_DEFAULTS):raise ScreensaverError('Invalid faceplate settings','backup_invalid')
    for k,v in panel.items():
        if k in {'enabled','configured'} and type(v) is not bool:raise ScreensaverError('Invalid flag','backup_invalid')
        if k=='mode' and v not in ('sync','async'):raise ScreensaverError('Invalid mode','backup_invalid')
        if k=='transition' and v not in ('fade','wipe','slide','dissolve','none'):raise ScreensaverError('Invalid transition','backup_invalid')
        if k=='framing' and v not in ('square','fill'):raise ScreensaverError('Invalid framing','backup_invalid')
        if k=='page_seconds' and (type(v) is not int or not 2<=v<=180):raise ScreensaverError('Invalid duration','backup_invalid')
    ui=raw['interface']
    if not isinstance(ui,dict) or set(ui)!={'mode','layout'} or ui['mode'] not in ('collection','classic') or ui['layout'] not in ('comfort','compact','list'):
        raise ScreensaverError('Invalid interface settings','backup_invalid')
    return copy.deepcopy(raw)

def recover(root):
    """A crash between catalog and UI writes restores both before either is loaded."""
    root=checked_path(root);journal=root/'settings-import-journal.json'
    if not journal.exists():return
    saved=read_object(checked_path(journal))
    if not isinstance(saved,dict) or set(saved)!={'catalog','workspace'}:raise ScreensaverError('Invalid recovery journal','backup_invalid')
    for name,key in [('studio.json','catalog'),('workspace-v1.json','workspace')]:
        path=checked_path(root/name)
        if saved[key] is None:path.unlink(missing_ok=True)
        elif isinstance(saved[key],dict):atomic_json(path,saved[key])
        else:raise ScreensaverError('Invalid recovery journal','backup_invalid')
    journal.unlink()

class SettingsBackup:
    def __init__(self,service,workspace,panel,home):
        self.service=service;self.store=service.catalog;self.workspace=workspace;self.panel=panel
        self.home=Path(home).resolve()

    def snapshot(self):
        with self.workspace.lock,self.panel.lock,self.store.lock:
            return validate_backup(dict(schema=SCHEMA,options=self.store.options(),
                faceplate={k:self.panel.options.get(k,v) for k,v in PANEL_DEFAULTS.items()},
                interface={k:self.workspace.data[k] for k in ('mode','layout')}))

    def export(self):
        payload=self.snapshot();directory=checked_path(self.home/'Documents'/'AnimatedScreensaver')
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=directory/(datetime.now(timezone.utc).strftime('settings-%Y%m%d-%H%M%S-')+secrets.token_hex(4)+'.json')
        atomic_json(path,payload)
        return dict(path=str(path),backup=payload)

    def read(self,value):
        if not isinstance(value,str) or len(value)>4096:raise ScreensaverError('Choose a JSON file','backup_path')
        path=checked_path(Path(value))
        if not path.is_relative_to(self.home) or path.suffix.lower()!='.json':raise ScreensaverError('Choose a JSON file in your home folder','backup_path')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            import stat
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_size>LIMIT:raise ScreensaverError('Backup too large','backup_invalid')
            with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(LIMIT+1)
            if len(raw)>LIMIT:raise ScreensaverError('Backup too large','backup_invalid')
            return validate_backup(json.loads(raw))
        finally:os.close(fd)

    def restore(self,value):
        backup=self.read(value) # Validate everything before any mutation or hardware operation.
        self.workspace.ensure_idle()
        if self.panel.display_busy():raise ScreensaverError('Leave the screensaver before importing','busy')
        previous=self.export()['path']
        with self.workspace.lock,self.panel.lock,self.store.lock:
            catalog=copy.deepcopy(self.store.data);workspace=copy.deepcopy(self.workspace.data)
            original_panel=copy.deepcopy(self.panel.options);revision=self.store.revision
            journal=checked_path(self.store.root/'settings-import-journal.json')
            atomic_json(journal,dict(catalog=read_object(self.store.path),workspace=read_object(self.workspace.path)))
            try:
                # One catalog save contains TV and Faceplate settings. No preparation,
                # installation, calibration upload or automatic update is triggered.
                self.store.data['options']=backup['options'];self.store.data['jsaux']=backup['faceplate']
                self.workspace.data.update(backup['interface'])
                self.store.save();self.workspace._save()
                self.panel.options=copy.deepcopy(backup['faceplate'])
                journal.unlink() # Commit point; recovery rolls back until this succeeds.
            except BaseException:
                self.store.data=catalog;self.store.revision=revision;self.workspace.data=workspace;self.panel.options=original_panel
                recover(self.store.root)
                raise
        return dict(restored=True,previous_path=previous)
