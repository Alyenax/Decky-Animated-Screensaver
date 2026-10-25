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

class StorageCacheAuditTests(unittest.TestCase):
    def service(self,directory):
        media=Media();service=StudioService(Path(directory)/'library',steamgriddb=Provider(),media=media,games_provider=lambda:[])
        media.service=service;self.addCleanup(service.shutdown)
        service.catalog.configure(dict(storage_mib=256,smoothing=True,show_cover=False,show_logo=False))
        return service,media

    def test_nearly_full_native_cache_refuses_smoothing_even_with_unlimited_video(self):
        for maximum in (128,0):
            with self.subTest(maximum=maximum),tempfile.TemporaryDirectory() as directory:
                service,media=self.service(directory);scene(service.catalog,620);scene(service.catalog,730)
                service.catalog.configure({'max_video_mib':maximum})
                with (service.root/'filler').open('wb') as handle:handle.truncate(255*MIB-service.catalog.usage())
                for number in (620,730):
                    original=service.catalog.get(number)
                    with self.assertRaises(ScreensaverError) as error:service._one(number)
                    self.assertEqual('storage_limit',error.exception.code)
                    self.assertTrue(service.catalog.ready(service.catalog.get(number),True))
                    self.assertEqual(original['media'],service.catalog.get(number)['media'])
                self.assertEqual(0,media.calls);self.assertLessEqual(service.catalog.usage(),256*MIB)
                self.assertEqual([],list((service.root/'staging').glob('*')) if (service.root/'staging').exists() else [])

    def test_actual_temp_and_commit_are_counted_without_duplicate_copy_or_orphan(self):
        for failure in ('none','cancel','save'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                service,media=self.service(directory);original=scene(service.catalog)
                with (service.root/'filler').open('wb') as handle:handle.truncate(252*MIB-service.catalog.usage())
                update=service.catalog.update
                def publish(number,patch):
                    self.assertLessEqual(service.catalog.usage(),256*MIB)
                    if 'smoothed' in patch.get('media',{}) and failure!='none':
                        if failure=='cancel':raise Interrupted()
                        raise OSError('Simulated pre-commit failure')
                    return update(number,patch)
                with patch.object(service.catalog,'update',side_effect=publish):
                    if failure=='none':service._one(620)
                    else:
                        with self.assertRaises(Interrupted if failure=='cancel' else OSError):service._one(620)
                self.assertLessEqual(max(media.peak),256*MIB);self.assertLessEqual(service.catalog.usage(),256*MIB)
                derivatives=list((service.root/'prepared').glob('*.webm'))
                self.assertEqual(1 if failure=='none' else 0,len(derivatives))
                if failure!='none':self.assertEqual(original['media'],service.catalog.get(620)['media'])
                self.assertTrue(service.catalog.ready(service.catalog.get(620),True))
