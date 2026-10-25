from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from das.studio.service import StudioService,Interrupted
from das.studio.discovery import Discovery
from das.core.catalog import ScreensaverError
from test_studio import FakeMedia,Provider,scene

MIB=1024*1024
class Media(FakeMedia):
    def __init__(self):self.calls=0;self.peak=[];self.service=None
    def smooth(self,source,directory,options,checkpoint,progress):
        self.calls+=1
        if options.get('_storage_output_bytes',options['max_video_mib']*MIB or float('inf'))<2*MIB:raise ScreensaverError('Budget','storage_limit')
        path=directory/'smooth.webm';path.write_bytes(b'x'*(2*MIB));self.peak.append(self.service.catalog.usage());return path

class CandidateAuditTests(unittest.TestCase):
    def service(self,directory):
        media=Media();service=StudioService(Path(directory)/'library',steamgriddb=Provider(),media=media,games_provider=lambda:[])
        media.service=service;self.addCleanup(service.shutdown)
        service.catalog.configure(dict(storage_mib=256,smoothing=True,show_cover=False,show_logo=False))
        return service,media

    def test_both_candidate_caches_bound_300_games_and_expire_without_losing_saved_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            service,_=self.service(directory);discovery=Discovery(service)
            service.candidates=lambda number,role:[dict(id=number*100+i,animated=True) for i in range(36)]
            for number in range(1,301):discovery.candidates(number,'animation')
            self.assertLessEqual(len(service._candidates),24);self.assertLessEqual(len(discovery.candidate_cache),24)
            service.choose(300,30000)
            saved=service.catalog.get(300)['asset']
            with self.assertRaises(ScreensaverError):service.choose(1,100)
            with patch('das.studio.service.time.time',return_value=time.time()+301):
                self.assertEqual(0,service.diagnostic_snapshot()['candidate_lists'])
                self.assertEqual(0,discovery.diagnostic_snapshot()['cached_candidate_lists'])
                with self.assertRaises(ScreensaverError):service.choose(300,30000)
            self.assertEqual(saved,service.catalog.get(300)['asset'])
