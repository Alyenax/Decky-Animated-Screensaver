"""Candidate still/motion isolation and cancellation, no preparation or USB."""
import base64
import json
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch,Mock
from urllib.request import urlopen
from urllib.request import Request
from das.provider import Redirects,SteamGridDBError
from das.core.catalog import ScreensaverError,file_sha256,atomic_json
from das.studio.preview import Preview
from das.studio.service import StudioService
from test_plugin import Codec,GIF
from test_studio import Provider,ASSETS

class Candidate35Tests(unittest.TestCase):
 def test_legacy_thumbnail_redirects_remain_narrow_and_strip_credentials(self):
  request=Request('https://s3.amazonaws.com/steamgriddb/thumb/a.webp',headers={'Authorization':'Bearer fixture'})
  value=Redirects().redirect_request(request,None,302,'Found',{},'https://steamgriddb.s3.amazonaws.com/thumb/a.webp')
  self.assertIsNone(value.get_header('Authorization'))
  for unsafe in ('http://steamgriddb.s3.amazonaws.com/thumb/a.webp','https://s3.amazonaws.com/other/a.webp','https://evil.test/a.webp','https://s3.amazonaws.com/steamgriddb/grid/a.webp'):
   with self.assertRaises(SteamGridDBError):Redirects().redirect_request(request,None,302,'Found',{},unsafe)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.service=StudioService(Path(self.tmp.name)/'library',Provider(),media=Codec(),games_provider=lambda:[])
  self.addCleanup(self.service.shutdown);self.store=self.service.catalog
  self.store.update(620,dict(name='Portal'))
  self.preview=Preview(self.store,ASSETS,self.service);self.addCleanup(self.preview.close)
  self.asset=dict(id=1,url='https://cdn.steamgriddb.com/full.webp',thumb='https://s3.amazonaws.com/steamgriddb/thumb/test.webp',animated=True,width=1920,height=620)
  self.service._candidates[(620,'animation')]=[self.asset]
  self.source=self.store.managed('sources/source.gif');self.source.parent.mkdir();self.source.write_bytes(GIF)
 def render(self,codec,source,work,check,motion):
  check();path=work/('motion.webm' if motion else 'still.jpg');path.write_bytes(b'\x1aE\xdf\xa3fixture' if motion else b'\xff\xd8\xfffixture');return path
 def test_backend_stills_do_not_need_frontend_network_or_open_transport(self):
  before=self.store.path.read_bytes()
  with patch.object(self.service,'_download',return_value=self.source) as download,patch('das.studio.candidate_media.render',side_effect=self.render) as render:
   value=self.preview.candidate(620,'animation',1,request_id='s'*32)
   again=self.preview.candidate(620,'animation',1,request_id='t'*32)
  self.assertEqual(value,again);self.assertTrue(value['still'].startswith('data:image/jpeg;base64,'))
  self.assertEqual(download.call_args.kwargs['maximum'],8*1024*1024);self.assertTrue(download.call_args.kwargs['thumbnail'])
  self.assertEqual(render.call_count,1);self.assertFalse(self.preview.transport.files);self.assertEqual(before,self.store.path.read_bytes())
 def test_static_thumbnail_falls_back_to_original_without_32_mib_preview_limit(self):
  def render(codec,source,work,check,motion):
   if source.name=='thumb.gif':raise ScreensaverError('Static thumbnail','static_selection')
   return self.render(codec,source,work,check,motion)
  thumb=self.source.with_name('thumb.gif');thumb.write_bytes(GIF)
  def download(asset,**kw):
   if kw.get('thumbnail'):return thumb
   self.assertEqual(kw['maximum'],128*1024*1024);return self.source
  with patch.object(self.service,'_download',side_effect=download) as downloaded,patch('das.studio.candidate_media.render',side_effect=render):
   result=self.preview.candidate(620,'animation',1,True,'m'*32)
  self.assertEqual(downloaded.call_count,2);self.assertTrue(result['derivative'])
  with urlopen(result['source_url']) as response:self.assertEqual(response.read(),b'\x1aE\xdf\xa3fixture')
 def test_broken_remote_thumbnail_falls_back_to_the_same_candidate_not_another_game(self):
  def download(asset,**kw):
   if kw.get('thumbnail'):raise OSError('unavailable')
   self.assertEqual(asset,self.asset);return self.source
  with patch.object(self.service,'_download',side_effect=download),patch('das.studio.candidate_media.render',side_effect=self.render):
   self.assertIn('still',self.preview.candidate(620,'animation',1,request_id='s'*32))
 def test_unknown_candidate_cannot_request_an_arbitrary_url(self):
  with patch.object(self.service,'_download',side_effect=AssertionError('No network')):
   with self.assertRaises(ScreensaverError) as error:self.preview.candidate(620,'animation',999,request_id='s'*32)
   self.assertEqual(error.exception.code,'invalid_asset')
 def test_cached_large_original_does_not_trigger_a_second_download_for_thumbnail_cap(self):
  identity=hashlib.sha256(self.asset['url'].encode()).hexdigest()
  atomic_json(self.source.parent/(identity+'.json'),dict(path=str(self.source.relative_to(self.store.root)),sha256=file_sha256(self.source)))
  with patch.object(self.service.provider,'opener',Mock(open=Mock(side_effect=AssertionError('No redundant HTTP request'))),create=True):
   with self.assertRaises(ScreensaverError) as error:self.service._download(self.asset,checkpoint=lambda:None,maximum=1)
   self.assertEqual(error.exception.code,'source_limit')
 def test_cancel_queued_request_and_late_cleanup_cannot_close_new_motion(self):
  self.preview.close(request_id='a'*32)
  with self.assertRaises(ScreensaverError):self.preview.candidate(620,'animation',1,True,'a'*32)
  with patch.object(self.service,'_download',return_value=self.source),patch('das.studio.candidate_media.render',side_effect=self.render):
   result=self.preview.candidate(620,'animation',1,True,'b'*32)
  self.preview.close(request_id='a'*32)
  with urlopen(result['source_url']) as response:self.assertEqual(response.status,200)
 def test_cancellation_during_still_download_does_not_commit_a_derivative(self):
  started=threading.Event();release=threading.Event();errors=[]
  def download(asset,checkpoint,**kw):started.set();release.wait(2);checkpoint();return self.source
  def worker():
   try:self.preview.candidate(620,'animation',1,request_id='s'*32)
   except ScreensaverError as error:errors.append(error.code)
  with patch.object(self.service,'_download',side_effect=download):
   thread=threading.Thread(target=worker);thread.start();self.assertTrue(started.wait(2));self.preview.close(request_id='s'*32);release.set();thread.join(3)
  self.assertEqual(errors,['preview_cancelled']);self.assertFalse(list(self.store.managed('candidate-previews-v1').glob('*.jpg')))
 def test_old_motion_ends_immediately_when_scoped_close_arrives(self):
  with patch.object(self.service,'_download',return_value=self.source),patch('das.studio.candidate_media.render',side_effect=self.render):
   self.preview.candidate(620,'animation',1,True,'a'*32)
  self.preview.close(request_id='a'*32);self.assertFalse(self.preview.transport.files)
