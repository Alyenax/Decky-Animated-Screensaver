import copy
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from das.studio.discovery import Discovery,normalized,steam_image,thumbnail,valid_top,image_diagnostic
from das.studio.storage import Store
from das.core.catalog import ScreensaverError,atomic_json

class DiscoveryTests(unittest.TestCase):
    def test_image_diagnostic_drops_paths_secrets_invalid_types_and_unbounded_events(self):
        value=dict(schema='das-artwork-load-v1',counts=dict(ready=2,error=-1,secret='KEY'),events=[dict(stage='blocked',source='other',format='png',url='https://private/?key=SECRET')]*30+[dict(stage=[],source='other',format='png')])
        safe=image_diagnostic(value)
        self.assertEqual(safe['counts'],dict(ready=2));self.assertEqual(len(safe['events']),23)
        self.assertNotIn('SECRET',json.dumps(safe));self.assertNotIn('https:',json.dumps(safe))
        self.assertEqual(image_diagnostic(None),{})

    def test_legacy_thumbnail_admission_does_not_broaden_source_download_hosts(self):
        from das.provider import _trusted_thumbnail,_trusted_url
        from das.core.jobs import _safe_asset
        url='https://s3.amazonaws.com/steamgriddb/thumb/a.png'
        self.assertTrue(_trusted_thumbnail(url));self.assertFalse(_trusted_url(url))
        asset=_safe_asset(dict(id=1,url='https://cdn2.steamgriddb.com/hero/a.webp',thumb=url))
        self.assertEqual(asset['thumb'],url)
        for unsafe in ('http://s3.amazonaws.com/steamgriddb/thumb/a.png','https://s3.amazonaws.com/other/thumb/a.png','https://s3.amazonaws.com/steamgriddb/grid/a.png'):
            self.assertFalse(_trusted_thumbnail(unsafe))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'library')
        self.service=SimpleNamespace(catalog=self.store,_candidates={},candidates=Mock(return_value=[dict(id=1,thumb='https://cdn.steamgriddb.com/a.jpg')]))
        self.discovery=Discovery(self.service)

    def search(self,items):
        opener=Mock();opener.open.return_value=io.BytesIO(json.dumps(dict(items=items)).encode())
        return patch('das.studio.steam_http.build_opener',return_value=opener),opener

    def test_search_minimum_and_cache_are_read_only(self):
        network,opener=self.search([dict(id=620,name='Portal 2',tiny_image='https://evil.test/p.jpg'),dict(id=True,name='No'),dict(id=3,name='Proton Experimental'),None])
        before=copy.deepcopy(self.store.data)
        with network:
            self.assertEqual(self.discovery.search('Po')['items'],[])
            self.assertFalse(opener.open.called)
            result=self.discovery.search('  Pórtal   2 ')
            self.assertEqual(len(result['items']),1)
            self.assertEqual(result['items'][0]['appid'],620)
            self.assertTrue(steam_image(result['items'][0]['thumbnail_url']))
            result['items'][0]['name']='Corruption'
            self.assertEqual(self.discovery.search('portal 2')['items'][0]['name'],'Portal 2')
            self.assertEqual(opener.open.call_count,1)
        self.assertEqual(self.store.data,before)
        self.assertEqual(normalized('ÉLDEN RING'),'elden ring')

    def test_open_only_known_metadata_and_does_not_select(self):
        with self.assertRaises(ScreensaverError):self.discovery.open(620)
        self.discovery._remember([dict(appid=620,name='Portal 2',excluded=True,collection_member=False)])
        value=self.discovery.open(620)
        self.assertTrue(value['excluded']);self.assertFalse(value['collection_member'])
        self.assertEqual(self.discovery.open(620),value)
        self.service.candidates.assert_not_called()

    def test_two_network_slots_and_no_waiting_mutation_lock(self):
        self.discovery.gate.acquire();self.discovery.gate.acquire()
        for call in (lambda:self.discovery.search('Portal'),lambda:self.discovery.ranking(),lambda:self.discovery.candidates(620,'animation')):
            with self.assertRaises(ScreensaverError) as caught:call()
            self.assertEqual(caught.exception.code,'read_busy')
        self.discovery.gate.release();self.discovery.gate.release()

    def test_candidate_cache_restores_selection_snapshot_and_is_bounded(self):
        first=self.discovery.candidates(620,'animation');first[0]['id']=999
        self.service._candidates.clear()
        self.assertEqual(self.discovery.candidates(620,'animation')[0]['id'],1)
        self.assertEqual(self.service._candidates[(620,'animation')][0]['id'],1)
        self.assertEqual(self.service.candidates.call_count,1)
        for number in range(30):self.discovery.candidates(1000+number,'cover')
        self.assertEqual(len(self.discovery.candidate_cache),24)

    def test_search_failure_does_not_change_catalogue_or_leak_slots(self):
        before=copy.deepcopy(self.store.data)
        with patch('das.studio.steam_http.build_opener',side_effect=OSError('offline')):
            for _ in range(3):
                with self.assertRaises(ScreensaverError) as caught:self.discovery.search('Portal')
                self.assertEqual(caught.exception.code,'steam_network_unavailable')
        self.assertEqual(before,self.store.data)
        self.assertTrue(self.discovery.gate.acquire(False));self.assertTrue(self.discovery.gate.acquire(False))

    def test_ranking_has_real_metadata_persistent_cache_and_offline_state(self):
        values=[dict(appid=620,name='Portal 2',rank=1,players=1234)]
        with patch('das.studio.selection.popular',return_value=values) as fetch:
            result=self.discovery.ranking();self.assertEqual(result['items'][0]['players'],1234)
            self.assertFalse(result['stale']);self.discovery.ranking();fetch.assert_called_once_with(self.service,with_metadata=True,observer=self.discovery.record)
        self.assertEqual(self.discovery.path.stat().st_mode&0o777,0o600)
        other=Discovery(self.service)
        with patch('das.studio.selection.popular',side_effect=OSError('offline')):
            value=other.ranking(force=True);self.assertTrue(value['stale']);self.assertEqual(value['items'][0]['rank'],1)
        self.assertEqual(self.store.games(),[])

    def test_malformed_or_expired_cache_is_not_success(self):
        for data in ({'items':[{}],'at':int(time.time())},{'items':'bad'}, {'at':int(time.time())+1}):
            atomic_json(self.discovery.path,data);other=Discovery(self.service)
            with patch('das.studio.selection.popular',side_effect=OSError('offline')):
                with self.assertRaises(ScreensaverError):other.ranking()
        self.assertFalse(valid_top({},int(time.time())))

    def test_optional_top_cache_write_failure_does_not_hide_live_results(self):
        values=[dict(appid=620,name='Portal 2',rank=1,players=1234)]
        with patch('das.studio.selection.popular',return_value=values),patch('das.studio.discovery.atomic_json',side_effect=OSError('disk full')):
            result=self.discovery.ranking()
        self.assertEqual(result['items'][0]['appid'],620)
        self.assertTrue(any(e['stage']=='ranking_cache' for e in self.discovery.diagnostic_snapshot()['events']))

    def test_safe_steam_stills_only_and_positive_real_appids(self):
        self.assertTrue(steam_image(thumbnail(dict(appid=620))))
        for value in ('https://shared.akamai.steamstatic.com@evil.test/steam/apps/620/header.jpg',
                      'https://shared.akamai.steamstatic.com:444/steam/apps/620/header.jpg',
                      'http://shared.akamai.steamstatic.com/steam/apps/620/header.jpg',
                      'https://shared.akamai.steamstatic.com/steam/apps/620/header.gif',
                      'https://shared.akamai.steamstatic.com.evil.test/steam/apps/620/header.jpg'):
            self.assertFalse(steam_image(value))
        for number in (True,-1,0,2**32,'620'):self.assertEqual(thumbnail(dict(appid=number)),'')
