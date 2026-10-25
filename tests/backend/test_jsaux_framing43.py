"""Optional native-ratio crop, default/cache compatibility and preview parity."""
import base64
import copy
import io
import os
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_jsaux as fixtures
from das.core.catalog import file_sha256
from das.jsaux.collection import fingerprint, preparation_spec
from das.jsaux.framing import framing_filter
from das.jsaux.manager import Delegation
from das.jsaux.protocol import BrokerError
from das.studio.installer import player_catalog


class Framing43Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ManagerTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.manager = self.f.manager
        self.store = self.f.service.catalog

    def test_centred_default_is_exact_previous_filter_and_identity(self):
        self.assertEqual(self.manager.options['framing'], 'square')
        self.assertEqual(framing_filter(),
            'scale=54:54:force_original_aspect_ratio=increase,crop=54:54:(iw-54)*0.5:(ih-54)*0.5,pad=64:54:5:0:black')
        old = dict(self.manager.options)
        old.pop('framing')
        self.assertEqual(fingerprint(self.manager.games(),old,self.store.options()), self.manager.identity())
        self.assertNotIn('framing', preparation_spec(self.manager.games(),old,self.store.options()))

    def test_choice_persists_and_invalidates_only_panel_not_tv_or_installed_export(self):
        self.f.prepare_receipt()
        identity = self.manager.identity()
        tv = copy.deepcopy(player_catalog(self.store))
        exported = copy.deepcopy(self.f.installer.jsaux_export)
        calls = list(self.f.fake.calls)
        self.manager.configure({'framing':'fill'})
        self.assertNotEqual(identity, self.manager.identity())
        self.assertFalse(self.manager.readiness()['ready'])
        self.assertEqual(player_catalog(self.store), tv)
        self.assertEqual(self.f.installer.jsaux_export, exported)
        self.assertEqual(self.f.fake.calls, calls)
        again = Delegation(self.f.service,self.f.installer,self.f.fake)
        self.addCleanup(again.shutdown)
        self.assertEqual(again.options['framing'], 'fill')
        self.manager.configure({'framing':'square'})
        self.assertEqual(self.manager.identity(), identity)
        self.assertTrue(self.manager.readiness()['ready'])

    def test_readiness_names_framing_and_crop_changes(self):
        self.f.prepare_receipt()
        self.manager.receipt['input_spec'] = preparation_spec(self.manager.games(),self.manager.options,self.store.options())
        self.manager.configure({'framing':'fill'})
        self.assertIn('framing', self.manager.readiness()['changed'])
        identity = self.manager.identity()
        self.store.update(620,dict(faceplate_crop=dict(x=50,y=0)))
        self.assertNotEqual(self.manager.identity(), identity)
        self.assertIn('(ih-54)*0.0',framing_filter('fill',dict(x=50,y=0)))

    def test_invalid_values_are_rejected_without_saving_or_decoding(self):
        saved = dict(self.manager.options)
        for value in ('stretch','16:9','',None,True,[],{}):
            with self.subTest(value=value), self.assertRaises(BrokerError):
                self.manager.configure({'framing':value})
        self.assertEqual(self.manager.options,saved)
        for point in ({'x':-1},{'y':101},{'y':float('nan')},{'x':True},{'x':'50'},{'z':0},[]):
            with self.subTest(point=point), self.assertRaises(BrokerError):
                framing_filter('fill',point)

    def test_actual_native_pixels_and_prepared_preview_match_without_download_or_usb(self):
        binary = os.environ.get('DAS_TEST_FFMPEG')
        if not binary:
            self.skipTest('Explicit isolated FFmpeg required')
        from PIL import Image
        source = self.store.managed('square.png')
        image = Image.new('RGB',(64,64))
        image.putdata([(40+y*2,80+x,90) for y in range(64) for x in range(64)])
        image.save(source)
        original = file_sha256(source)
        def decode(mode,point=None):
            return subprocess.run([binary,'-v','error','-i',str(source),'-vf',framing_filter(mode,point),
                '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True,timeout=15).stdout
        for mode in ('square','fill'):
            raw=decode(mode)
            self.assertEqual(len(raw),64*54*3)
            for y in (0,27,53):
                if mode=='square':
                    self.assertEqual(raw[(y*64)*3:(y*64+5)*3],bytes(15))
                    self.assertEqual(raw[(y*64+59)*3:(y*64+64)*3],bytes(15))
                else:
                    # A 64x64 square becomes 64x54 by removing five rows at
                    # each end, not by stretching. No side borders remain.
                    for x in (0,32,63):
                        self.assertEqual(raw[(y*64+x)*3:(y*64+x+1)*3],bytes(image.getpixel((x,y+5))))
        self.assertEqual(decode('fill',{'y':0})[:3],bytes(image.getpixel((0,0))))
        self.assertEqual(decode('fill',{'y':100})[:3],bytes(image.getpixel((0,10))))
        game=self.store.get(620)
        self.store.update(620,dict(media={**game['media'],'panel_source':'square.png'},
            sha256={**game['sha256'],'panel_source':original}))
        self.f.service.compiler.runner=SimpleNamespace(ffmpeg=binary,library_path=None)
        self.manager.refresh()
        self.manager.configure(dict(enabled=True,framing='fill',transition='none'))
        with patch.object(self.f.service,'_download',side_effect=AssertionError('No download')):
            self.manager._prepare()
        self.assertEqual(self.manager.reason,'')
        self.assertTrue(self.manager.readiness()['ready'])
        self.f.fake.calls.clear()
        preview=self.manager.game_preview(620)
        with Image.open(self.store.managed(self.manager.receipt['path'],True)) as decoded:
            prepared=decoded.convert('RGB')
        projected=Image.open(io.BytesIO(base64.b64decode(preview['data_url'].split(',')[1]))).convert('RGB')
        self.assertEqual(prepared.size,(64,54))
        self.assertEqual(projected.tobytes(),prepared.tobytes())
        self.assertEqual(self.f.fake.calls,[])
        self.assertEqual(file_sha256(source),original)
