"""Source previews, normal skips and preparation modes; no hardware claims."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from urllib.request import urlopen
from das.core.catalog import ScreensaverError
from das.studio.service import StudioService
from das.studio.preview import Preview
from das.studio.installer import Installer
from das.studio.workspace import CollectionWorkspace
from test_studio import Provider,scene,ASSETS
from test_plugin import Codec,GIF

class Preview33Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.service=StudioService(self.root/'library',Provider(),media=Codec(),games_provider=lambda:[])
  self.addCleanup(self.service.shutdown);self.store=self.service.catalog
  self.store.configure(dict(show_cover=False,name_display='title'))
  self.service._scanned=True;self.service._assets=lambda *args:[]
  self.service.compiler.inspect=lambda path,check:dict(animated=True,width=1,height=1,duration=1)
  self.preview=Preview(self.store,ASSETS,self.service);self.addCleanup(self.preview.close)
  (self.root/'Steam').mkdir()
  self.workspace=CollectionWorkspace(self.service,Installer(self.store,self.root/'Steam',ASSETS),SimpleNamespace(busy=lambda:False,options={}))
  self.addCleanup(self.workspace.shutdown)
 def catalog(self):return json.loads((self.preview.code/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').strip().removesuffix(';'))
 def test_existing_scene_preview_ignores_pending_replacement_and_keeps_files(self):
  scene(self.store);self.store.update(620,dict(pending_change=True,error='invalid_media'))
  before=self.store.path.read_bytes()
  value=self.preview.open(620)
  self.assertEqual(value['count'],1);self.assertEqual(self.store.path.read_bytes(),before)
  self.assertEqual(self.catalog()['games'][0]['name'],self.store.get(620)['name'])
 def test_old_cleanup_cannot_close_new_preview(self):
  scene(self.store)
  first=self.preview.open(620,request_id='a'*32)
  second=self.preview.open(620,request_id='b'*32)
  self.preview.close(request_id='a'*32);self.preview.close(nonce=first['nonce'])
  with urlopen(second['url']) as response:self.assertEqual(response.status,200)
  self.preview.close(request_id='b'*32);self.assertFalse(self.preview.transport.files)
 def test_cancel_before_rpc_starts_cannot_later_open_transport(self):
  scene(self.store);self.preview.close(request_id='c'*32)
  with self.assertRaises(ScreensaverError) as error:self.preview.open(620,request_id='c'*32)
  self.assertEqual(error.exception.code,'preview_cancelled');self.assertFalse(self.preview.transport.files)
 def test_optional_cover_failure_does_not_hide_valid_background(self):
  scene(self.store)
  with patch.object(self.service,'_download',side_effect=ScreensaverError('Download failed','download_failed')):
   value=self.preview.open(620,dict(cover_asset=dict(id=1,url='https://cdn.steamgriddb.com/test.png')))
  self.assertEqual(value['count'],1);self.assertEqual(value['warnings'],[dict(role='cover',code='download_failed')])
  with urlopen(value['url']) as response:self.assertEqual(response.status,200)
 def test_focused_candidate_gets_native_animation_without_optional_downloads(self):
  self.store.update(620,dict(name='Portal',status='pending'))
  source=self.store.managed('sources/source.gif');source.parent.mkdir();source.write_bytes(GIF)
  self.store.configure(dict(show_cover=True,name_display='both'))
  with patch.object(self.service,'_download',return_value=source),patch.object(self.service,'_assets',side_effect=AssertionError('No optional candidates')):
   value=self.preview.open(620,dict(asset=dict(id=1,url='https://cdn.steamgriddb.com/a.gif',animated=True)),artwork_only=True)
  with urlopen(value['source_url']) as response:
   self.assertEqual(response.headers['Content-Type'],'image/gif');self.assertEqual(response.read(),GIF)
  self.assertEqual(value['source_format'],'gif');self.assertFalse(self.store.get(620).get('media'))
 def test_draft_source_animated_preview_uses_shared_player_without_save_encode_or_usb(self):
  self.store.update(620,dict(name='Portal',excluded=True,status='pending'))
  asset=dict(id=1,url='https://cdn.steamgriddb.com/test.gif',animated=True,width=1,height=1,kind='hero',author='Test')
  self.service._candidates[(620,'animation')]=[asset]
  source=self.store.managed('sources/test.gif');source.parent.mkdir();source.write_bytes(GIF)
  before=self.store.path.read_bytes()
  clean=self.workspace.draft_patch(620,dict(choices={'animation':1},crop=dict(mode='16:10',x=30,y=60),branding=dict(mode='title',position='top-left')))
  with patch.object(self.service,'_download',return_value=source) as download,patch.object(self.service.compiler,'prepare',side_effect=AssertionError('No encoder')):
   value=self.preview.open(620,clean)
  self.assertEqual(download.call_args.kwargs['maximum'],32*1024*1024)
  self.assertEqual(before,self.store.path.read_bytes());self.assertEqual(self.workspace.summary()['draft_count'],0)
  game=self.catalog()['games'][0];self.assertTrue(game['media']['animated']);self.assertEqual(game['crop']['mode'],'16:10')
  self.assertEqual(game['branding']['position'],'top-left')
  with urlopen(value['url']) as response:self.assertIn(b'<script src=',response.read())
 def test_close_cancels_pending_download_and_does_not_reopen_transport(self):
  self.store.update(620,dict(name='Portal'))
  asset=dict(id=1,url='https://cdn.steamgriddb.com/test.gif',animated=True,width=1,height=1)
  started=threading.Event();release=threading.Event();errors=[]
  def download(asset,checkpoint,**kw):started.set();release.wait(2);checkpoint()
  def work():
   try:self.preview.open(620,dict(asset=asset))
   except ScreensaverError as e:errors.append(e.code)
  with patch.object(self.service,'_download',side_effect=download):
   worker=threading.Thread(target=work);worker.start();self.assertTrue(started.wait(2));self.preview.close();release.set();worker.join(3)
  self.assertEqual(errors,['preview_cancelled']);self.assertFalse(self.preview.transport.files)
 def test_job_admission_waits_for_preview_lease_or_fails_busy(self):
  self.preview.lock.acquire()
  try:
   with self.assertRaises(ScreensaverError) as error:self.preview.quiesce(timeout=.01)
   self.assertEqual(error.exception.code,'busy')
  finally:self.preview.lock.release()
  self.preview.quiesce(timeout=.01)
 def test_no_animation_is_normal_skip_not_pending_or_issue(self):
  self.store.update(620,dict(name='No animation',excluded=False))
  self.service.prepare();self.service.thread.join(3)
  self.assertEqual(self.store.get(620)['status'],'skipped')
  summary=self.workspace.summary();self.assertEqual(summary['skipped_count'],1)
  self.assertEqual(summary['issues_count'],0);self.assertEqual(summary['pending_count'],0)
 def test_still_fallback_uses_official_steam_cache_and_rejects_symlink(self):
  cache=self.root/'Steam/appcache/librarycache/620/hash';cache.mkdir(parents=True)
  image=cache/'library_hero.jpg';image.write_bytes(b'\xff\xd8\xff-local-fixture')
  self.store.configure(dict(static_fallback=True));self.store.update(620,dict(name='Portal',excluded=False))
  with patch.dict(os.environ,{'DAS_STEAM_ROOT':str(self.root/'Steam')}):
   found=self.service._local_artwork(620);self.assertEqual(found.read_bytes(),image.read_bytes())
   self.service.prepare();self.service.thread.join(3)
   self.assertEqual(self.store.get(620)['status'],'ready');self.assertEqual(self.store.get(620)['credits']['author'],'Steam')
   image.unlink();image.symlink_to(found);self.assertIsNone(self.service._local_artwork(620))
 def test_missing_vs_all_only_all_reencodes_valid_media(self):
  scene(self.store);self.service._ready.add(620)
  source=self.store.managed('sources/test.gif');source.parent.mkdir();source.write_bytes(GIF)
  asset=dict(id=1,url='https://cdn.steamgriddb.com/test.gif',animated=True,author='Fixture')
  self.service._assets=lambda *args:[asset] if args[1]=='animation' else []
  with patch.object(self.service,'_download',return_value=source),patch.object(self.service.compiler,'prepare',wraps=self.service.compiler.prepare) as prepare:
   self.service.prepare();self.service.thread.join(3);self.assertEqual(prepare.call_count,0)
   self.service.prepare(force=True);self.service.thread.join(3);self.assertEqual(prepare.call_count,1)
 def test_empty_still_fallback_is_real_actionable_error(self):
  self.store.configure(dict(static_fallback=True));self.store.update(-1,dict(name='Unknown',excluded=False))
  self.service.prepare();self.service.thread.join(3)
  self.assertEqual(self.store.get(-1)['status'],'skipped');self.assertEqual(self.store.get(-1)['error'],'');self.assertEqual(self.workspace.summary()['issues_count'],0)
 def test_skip_only_collection_finishes_without_empty_install(self):
  self.store.update(620,dict(name='Unknown',excluded=False,collection_member=True))
  with patch.object(self.workspace.installer,'install',side_effect=AssertionError('No empty installation')):
   self.workspace.start();self.workspace.thread.join(3)
  self.assertEqual(self.workspace.data['task']['state'],'done')
  self.assertEqual(self.workspace.data['task']['outcome'],'empty')
 def test_enabling_stills_turns_normal_skips_into_pending_work(self):
  self.store.update(620,dict(name='Unknown',excluded=False,status='skipped',skip_reason='no_animation'))
  self.assertEqual(self.workspace.summary()['pending_count'],0)
  self.store.configure(dict(static_fallback=True))
  self.assertEqual(self.workspace.summary()['pending_count'],1)
  self.assertEqual(self.workspace.overlay(self.store.get(620))['status'],'pending')
