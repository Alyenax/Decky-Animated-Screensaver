"""GH-02/DB-03 through both real plugins and the real local broker wire.

USB, browser, Steam metadata and wait clocks are explicit fakes. No hardware.
"""
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import test_jsaux_interop as interop
GCA=interop.GCA
import test_jsaux as fixtures

@unittest.skipUnless(GCA,'explicit DAS_TEST_GCA_ROOT required')
class ReceiptInteropTests(unittest.TestCase):
    setUp = interop.InteropTests.setUp
    # Inherit the fixture, not the older test methods, into this focused class.
    def test_actual_artwork_receipt_after_delayed_return_without_browser(self):
        from signalbar.faceplate.broker_adapter import FaceplateBrokerAdapter
        from signalbar.faceplate.coordinator import FaceplateCoordinator
        from signalbar.faceplate.transport import install_ownership_manager,GifCommitUnconfirmed
        sys.path.insert(0,str(Path(GCA)/'tests/backend'))
        try:
            from test_faceplate import FakeLink,StaticFirstSteamGridDB,ASSET_ROOT
        finally:sys.path.pop(0)
        for index,outcome in enumerate(('confirmed','already-stored','deferred','missing','sent-unconfirmed','error','cancelled')):
            with self.subTest(outcome=outcome):
                if index:
                    self.doCleanups()
                    self.setUp()
                f=fixtures.ManagerTests();f.setUp()
                record=[];reports=[]
                class ReceiptLink(FakeLink):
                    def send_gif(self,data,cancelled=None):
                        if outcome=='sent-unconfirmed':
                            self.record.append(('gif',data))
                            raise GifCommitUnconfirmed('Fake missing final ACK')
                        return super().send_gif(data,cancelled=cancelled)
                coordinator=FaceplateCoordinator(ASSET_ROOT,self.root/(outcome+'-panel.json'),steamgriddb=StaticFirstSteamGridDB(),
                    link_factory=lambda **kw:ReceiptLink(record,outcome!='already-stored',**kw),
                    port_finder=lambda:'/dev/fake',identity_reader=lambda _:'fake')
                coordinator.configure(True,50)
                engine=SimpleNamespace(faceplate=coordinator,faceplate_worker=Mock(),_faceplate_suspended=False)
                adapter=FaceplateBrokerAdapter(engine,ownership_root=self.root/(outcome+'-ownership'))
                adapter._policy=lambda:{'reason':''}
                original_restore=self.hardware.restore;original_submit=self.hardware.submit
                def submit(job,report):
                    adapter._display_operation=job['operation_id']
                    return original_submit(job,report)
                def restore(operation,report):
                    reports.append(operation);adapter._job=None;adapter._executing=False
                    self.hardware.commands.append(('restore',operation))
                    result=adapter.restore(operation,report)
                    if outcome=='deferred':adapter.normal_completed({'deferred':True})
                    return result
                self.hardware.submit=submit;self.hardware.restore=restore
                try:
                    f.prepare_receipt();manager=f.manager
                    manager.receipt['sync_wait_ms']=15000;f.installer.install()
                    manager.broker=self.client
                    # Each subtest has a distinct Steam activation; no replay of
                    # an ended activation is allowed by the actual broker.
                    self.hardware.state['steam']['activation_id']='activation-'+outcome
                    manager.refresh();message=f.message();message['session_id']='session-'+outcome
                    reply=manager.player(message)
                    self.assertTrue(reply['accepted'],reply)
                    session=manager.session
                    # Exercise actual DAS ready -> GCA broker submit/report.
                    started=time.monotonic_ns()//1000000
                    ready={**f.message('ready',2,ready_mono_ms=started,deadline_mono_ms=started+15000,clock_uncertainty_ms=1),
                        'session_id':message['session_id']}
                    ready_reply=manager.player(ready)
                    self.assertTrue(ready_reply['accepted'],ready_reply)
                    self.assertEqual(session['operation_id'],adapter._display_operation)
                    before_return=list(self.hardware.commands)
                    now=[0];delivered=[False]
                    def wait(stop,delay):
                        now[0]+=delay
                        if now[0]>=27 and not delivered[0]:
                            delivered[0]=True
                            if outcome in ('confirmed','already-stored','deferred','sent-unconfirmed','missing'):
                                with patch('signalbar.faceplate.coordinator.artwork_render.artwork',return_value=(None,'','hero') if outcome=='missing' else (bytes((20,40,60))*(64*54),'/fake/42.png','hero')):
                                    result=coordinator.synchronize_artwork(42)
                            else:result={'superseded':True} if outcome=='cancelled' else {'error':'fake render failure'}
                            adapter.normal_completed(result)
                        return stop.is_set()
                    manager._wait_return=wait
                    manager.stop();manager.return_thread.join(3)
                    self.assertFalse(manager.return_thread.is_alive())
                    self.assertGreaterEqual(now[0],27);self.assertEqual(1,len(reports))
                    self.assertFalse(manager.display_busy());self.assertIsNone(manager.last_operation)
                    if outcome in ('confirmed','already-stored','deferred'):
                        self.assertEqual('confirmed',manager.restore_state)
                        self.assertIsNone(adapter._restore_pending);self.assertIsNone(adapter._display_operation)
                        self.assertFalse(adapter.requires_exit_blank())
                    else:self.assertEqual('unconfirmed',manager.restore_state)
                    self.assertEqual(0 if outcome in ('missing','error','cancelled') else 1,sum(command[0]=='gif' for command in record))
                    self.assertEqual(['cancel','restore'],[kind for kind,_ in self.hardware.commands[len(before_return):]])
                    # No prepare/re-register/upload is performed by return tracking.
                    self.assertEqual(1,sum(event['event']=='content-registration-start' for event in manager.events))
                finally:
                    f.doCleanups();adapter.stop();self.hardware.restore=original_restore;self.hardware.submit=original_submit
                    install_ownership_manager(None)
