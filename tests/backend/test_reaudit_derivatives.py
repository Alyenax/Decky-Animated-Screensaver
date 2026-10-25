import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from das.studio.service import StudioService,Interrupted
from test_studio import FakeMedia,Provider,scene

class DerivativeReauditTests(unittest.TestCase):
    def test_shared_cover_is_immutable_on_cancel_or_catalog_failure_and_replacement(self):
        for previous in (False,True):
            for same in (False,True):
                for failure in ('none','cancel','save'):
                    with self.subTest(previous=previous,same=same,failure=failure),tempfile.TemporaryDirectory() as folder:
                        service=StudioService(Path(folder)/'library',media=FakeMedia(),steamgriddb=Provider(),games_provider=lambda:[])
                        try:
                            scene(service.catalog,620);scene(service.catalog,621)
                            target=service.root/'prepared/shared-cover.png';source=service.root/'staged-cover';source.write_bytes(b'old' if same else b'new')
                            if previous:
                                target.write_bytes(b'old');entry=service.catalog.get(620);entry['media']['cover']='prepared/shared-cover.png';service.catalog.update(620,{'media':entry['media']})
                            original=target.read_bytes() if previous else None
                            entry=service.catalog.get(621);entry['media']['cover']='prepared/shared-cover.png'
                            checkpoint=service.checkpoint;calls=[0]
                            def check():
                                calls[0]+=1
                                if calls[0]==2 and failure=='cancel':raise Interrupted()
                                checkpoint()
                            service.checkpoint=check
                            saved=service.catalog.update
                            def update(*a,**kw):
                                if failure=='save':raise OSError('Synthetic ENOSPC')
                                return saved(*a,**kw)
                            with patch.object(service.catalog,'update',side_effect=update):
                                if failure=='none':service._publish_derivative(source,target,621,{'media':entry['media']})
                                else:
                                    with self.assertRaises(Interrupted if failure=='cancel' else OSError):service._publish_derivative(source,target,621,{'media':entry['media']})
                            if previous:self.assertEqual(original,target.read_bytes());self.assertEqual('prepared/shared-cover.png',service.catalog.get(620)['media']['cover'])
                            leaves=list((service.root/'prepared').glob('shared-cover*'))
                            if failure!='none':self.assertEqual(1 if previous else 0,len(leaves));self.assertNotIn('cover',service.catalog.get(621)['media'])
                            else:
                                selected=service.root/service.catalog.get(621)['media']['cover'];self.assertEqual(b'old' if same else b'new',selected.read_bytes())
                        finally:service.shutdown()

    def test_actual_one_shared_cover_survives_second_game_enospc(self):
        from das.core.catalog import file_sha256
        with tempfile.TemporaryDirectory() as folder:
            service=StudioService(Path(folder)/'library',media=FakeMedia(),steamgriddb=Provider(),games_provider=lambda:[])
            try:
                scene(service.catalog,620);scene(service.catalog,621)
                service.catalog.configure(dict(show_cover=True,show_logo=False,smoothing=False))
                source=service.root/'source-cover';source.write_bytes(b'cover-source')
                target=service.root/('prepared/cover-'+file_sha256(source)[:24]+'.png');target.write_bytes(b'prepared-cover')
                entry=service.catalog.get(620);entry['media']['cover']=str(target.relative_to(service.root));service.catalog.update(620,{'media':entry['media']})
                service._assets=lambda *a:[dict(author='synthetic fixture',url='https://example.invalid/cover')]
                service._download=lambda *a:source
                def prepare(source,directory,*a,**kw):
                    leaf=directory/'cover.png';leaf.write_bytes(b'prepared-cover');return dict(tv=leaf,format='png')
                service.compiler.prepare=prepare;update=service.catalog.update
                def fail_second(number,values):
                    if number==621 and values.get('media',{}).get('cover'):raise OSError('Synthetic ENOSPC')
                    return update(number,values)
                with patch.object(service.catalog,'update',side_effect=fail_second):
                    with self.assertRaises(OSError):service._one(621)
                self.assertEqual(b'prepared-cover',target.read_bytes())
                self.assertEqual(str(target.relative_to(service.root)),service.catalog.get(620)['media']['cover'])
                self.assertNotIn('cover',service.catalog.get(621)['media'])
            finally:service.shutdown()
