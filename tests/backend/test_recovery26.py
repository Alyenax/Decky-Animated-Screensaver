import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from das.studio.service import StudioService
from das.studio.problems import game_problem
from test_studio import Provider,FakeMedia,scene


class Recovery26Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=StudioService(Path(self.temp.name)/'library',steamgriddb=Provider(),media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(self.service.shutdown)

    def test_retained_animation_failure_is_counted_and_filtered_without_invalidating_ready(self):
        scene(self.service.catalog);self.service._ready.add(620)
        self.service.catalog.update(620,{'error':'invalid_media','pending_change':True})
        with patch('das.studio.service.file_sha256',side_effect=AssertionError('Metadata reads must not hash or decode')):
            state=self.service.status();page=self.service.library(filter='attention')
            detail=self.service.game_details(620)
        self.assertEqual(state['issues_count'],1);self.assertEqual(state['failed_count'],0)
        self.assertEqual(state['ready_count'],1);self.assertEqual(page['total'],1)
        self.assertEqual(detail['problem']['appid'],620)
        self.assertEqual(detail['problem']['code'],'invalid_media')
        self.assertTrue(detail['problem']['retained_media'])
        self.assertEqual(detail['problem'],page['items'][0]['problem'])

    def test_optional_assets_missing_and_exclusions_share_one_attention_rule(self):
        for number,patch in ((1,{'cover_error':'download_failed','status':'ready'}),
                             (2,{'logo_error':'invalid_media','status':'ready'}),
                             (3,{'status':'missing'}),(4,{'error':'decode_failed','status':'error','excluded':True})):
            self.service.catalog.update(number,dict(name='Game '+str(number),**patch))
        state=self.service.status();self.assertEqual(state['issues_count'],2)
        page=self.service.library(filter='attention');self.assertEqual(page['total'],2)
        self.assertEqual([g['problem']['role'] for g in page['items']],['cover','logo'])
        self.service.catalog.update(1,{'cover_error':''})
        self.assertEqual(self.service.status()['issues_count'],1)
        self.service.catalog.update(2,{'excluded':True});self.assertEqual(self.service.status()['issues_count'],0)

    def test_summary_is_bounded_but_filter_contains_every_affected_game(self):
        for n in range(30):self.service.catalog.update(n+1,dict(name=f'Game {n:02}',status='error',error='invalid_media'))
        self.assertEqual(self.service.status()['issues_count'],30)
        self.assertEqual(len(self.service.status()['issues']),5)
        page=self.service.library(filter='attention',page=4)
        self.assertEqual(page['total'],30);self.assertEqual(page['page'],4);self.assertEqual(len(page['items']),6)

    def test_recovery_summary_does_not_reflect_arbitrary_error_details(self):
        problem=game_problem(dict(appid=1,name='Example',status='error',error='secret path /private/file'))
        self.assertEqual(problem['code'],'unexpected_error')
        self.assertNotIn('/private',str(problem))
