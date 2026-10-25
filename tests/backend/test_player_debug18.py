import json
import os
from pathlib import Path
import tempfile
import unittest
from das.jsaux.player_debug import PlayerDebugJournal,clean_event,clean_report,collect_cef,SCHEMA

def report(events=None):
    return dict(schema=SCHEMA,run='a'*16,build='b'*12,events=events or [dict(event='boot',seq=1,ms=0)])

class PlayerDebug18Tests(unittest.TestCase):
    def test_late_terminal_survives_rolling_merge_out_of_order_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'debug.json';journal=PlayerDebugJournal(path)
            journal.receive(report())
            for block in range(1,81):
                journal.receive(report([dict(event='scene-visible',seq=block*32+i,ms=block*5000+i,scene=i%24) for i in range(32)]))
            terminal=dict(event='broker-refused',seq=3000,ms=410000,reason='STEAM_INACTIVE')
            journal.receive(report([terminal,dict(event='stop',seq=3001,ms=410001,reason='broker-refused')]))
            journal.receive(report([dict(event='request',seq=150,ms=15000)]))
            snapshot=PlayerDebugJournal(path).snapshot()
            self.assertIn(terminal,snapshot['runs'][0]['events'])
            self.assertEqual(snapshot['sessions'][0]['last_ms'],410001)
            self.assertEqual(snapshot['sessions'][0]['conclusion'],'terminal-observed')
            self.assertLess(len(json.dumps(snapshot)),14000)

    def test_failed_persistence_reports_safe_category_but_keeps_memory_evidence(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            journal=PlayerDebugJournal(Path(d)/'debug.json')
            with patch('das.jsaux.player_debug.atomic_json',side_effect=PermissionError('PRIVATE PATH')):journal.receive(report())
            snapshot=journal.snapshot()
            self.assertEqual(snapshot['storage_error_kind'],'permission-denied')
            self.assertEqual(snapshot['browser_evidence'],'received')
            self.assertNotIn('PRIVATE',json.dumps(snapshot))

    def test_cef_engine_hints_are_plugin_scoped_and_never_raw_log_text(self):
        with tempfile.TemporaryDirectory() as d:
            logs=Path(d)/'logs';logs.mkdir()
            (logs/'cef_log.txt').write_text('Other plugin out of memory PRIVATE\n'
                'decky-animated-screensaver PIPELINE_ERROR PRIVATE\n'
                'decky-animated-screensaver Render process exited PRIVATE\n')
            snapshot=collect_cef(d)
            self.assertEqual([e['code'] for e in snapshot['engine']],['media-pipeline-error','renderer-exited'])
            self.assertNotIn('PRIVATE',json.dumps(snapshot))

    def test_startup_milestones_survive_backend_report_compaction(self):
        from das.jsaux.player_debug import bounded_runs
        events=[dict(event='request',seq=n,ms=n) for n in range(64)]
        events[31]=dict(event='first-frame-held',seq=31,ms=31,reason='matrix-start')
        events[32]=dict(event='tv-start',seq=32,ms=32,reason='software-coordinated')
        clean=clean_report(report(events));self.assertIsNotNone(clean)
        compact=bounded_runs([clean])[0]['events']
        self.assertEqual(len(compact),32)
        self.assertIn(events[31],compact);self.assertIn(events[32],compact)

    def test_untrusted_fields_never_leave_allowlist(self):
        event=dict(event='js-error',seq=1,ms=2,reason='TypeError',resource='runtime',line=10,column=4,
            url='https://PRIVATE',token='PRIVATE',message='PRIVATE',flags={'fetch':True,'private':'PRIVATE'})
        clean=clean_report(report([event]));self.assertNotIn('PRIVATE',json.dumps(clean))
        for bad in ([],None,{'event':[],'seq':1,'ms':2},{'event':'boot','seq':True,'ms':0},
            {'event':'PRIVATE','seq':1,'ms':0}):self.assertIsNone(clean_event(bad))
        for value in ({},[],{**report(),'build':'PRIVATE'}, {**report(),'events':[event]*65}):self.assertIsNone(clean_report(value))

    def test_persistence_dedup_rotation_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'debug.json';journal=PlayerDebugJournal(path)
            for n in range(6):
                value=report([dict(event='request',action='open',seq=i,ms=i) for i in range(64)])
                value['run']=f'{n:016x}';self.assertTrue(journal.receive(value));self.assertTrue(journal.receive(value))
            self.assertLessEqual(path.stat().st_size,128*1024);self.assertEqual(path.stat().st_mode&0o777,0o600)
            saved=json.loads(path.read_text());self.assertEqual(len(saved['runs']),4)
            recovered=PlayerDebugJournal(path).snapshot();self.assertTrue(all(run['recovered'] for run in recovered['runs']))
            self.assertLessEqual(len(json.dumps(recovered)),13000)
            self.assertEqual(len({e['seq'] for e in saved['runs'][-1]['events']}),64)

    def test_corrupt_and_symlinked_journal_cannot_break_plugin_or_overwrite_foreign_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'debug.json';foreign=Path(d)/'foreign';foreign.write_text('keep');path.symlink_to(foreign)
            journal=PlayerDebugJournal(path);self.assertTrue(journal.receive(report()))
            self.assertTrue(journal.snapshot()['storage_error']);self.assertEqual(foreign.read_text(),'keep')

    def test_cef_fallback_only_exports_fixed_events_and_network_codes(self):
        with tempfile.TemporaryDirectory() as d:
            logs=Path(d)/'logs';logs.mkdir();event={**report()['events'][0],'run':'a'*16,'build':'b'*12,'message':'PRIVATE'}
            (logs/'cef_log.txt').write_text('unrelated browser PRIVATE\n[INFO:CONSOLE] "[DAS-JSAUX-DEBUG] '+json.dumps(event)+'", source: /home/PRIVATE\n'
                'Mixed Content: https://decky-animated-screensaver.steamloopback.host to http://127.0.0.1:37679 PRIVATE\n')
            previous={**event,'event':'js-error','reason':'SyntaxError','resource':'runtime','seq':2}
            (logs/'cef_log.previous.txt').write_text('[DAS-JSAUX-DEBUG] '+json.dumps(previous).replace('"','\\"')+'\n')
            out=collect_cef(d);self.assertNotIn('PRIVATE',json.dumps(out))
            self.assertEqual(out['reads'][0]['state'],'read');self.assertEqual(out['network'][0]['code'],'mixed-content')
            self.assertEqual([e['event'] for e in out['runs'][0]['events']],['boot','js-error'])

    def test_missing_huge_and_nonregular_cef_are_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            logs=Path(d)/'logs';logs.mkdir();os.mkfifo(logs/'cef_log.txt')
            out=collect_cef(d);self.assertEqual(out['reads'][0]['state'],'unreadable')
            self.assertEqual(out['reads'][1]['state'],'missing')
            (logs/'cef_log.txt').unlink();(logs/'cef_log.txt').write_text('PRIVATE'*100000)
            self.assertEqual(collect_cef(d)['runs'],[])

    def test_cef_warning_fallback_retains_flush_errors_and_fixed_script_location_only(self):
        with tempfile.TemporaryDirectory() as d:
            logs=Path(d)/'logs';logs.mkdir()
            event=dict(run='a'*16,build='b'*12,event='diagnostic-failed',seq=12,ms=42,status=403)
            (logs/'cef_log.txt').write_text('[WARNING:CONSOLE(5)] "[DAS-JSAUX-DEBUG] '+json.dumps(event)+'", source: PRIVATE\n'
                '[ERROR:CONSOLE(23)] "Uncaught SyntaxError: Unexpected token < PRIVATE", source: '
                'https://uioverride-decky-animated-screensaver.steamscreensavers.host/catalog.js?token=PRIVATE\n')
            out=collect_cef(d);self.assertNotIn('PRIVATE',json.dumps(out))
            self.assertEqual(out['runs'][0]['events'],[{k:v for k,v in event.items() if k not in ('run','build')}])
            self.assertEqual(out['network'],[dict(source='current',code='script-syntax',resource='catalog',line=23,syntax='unexpected-token')])
