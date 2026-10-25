"""Real loopback HTTP with existing export-token and GCA admission checks."""
import http.client
import json
import socket
import threading
import unittest
from das.jsaux.player_relay import PlayerRelay,PATH,DEBUG_PATH,trusted_origin,safe_reply,origin_evidence
from pathlib import Path
from das.jsaux.protocol import BrokerError
from das.core.catalog import ScreensaverError
import test_jsaux as fixtures

ORIGIN='https://decky-animated-screensaver.steamloopback.host'

class PlayerRelay15Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.relay=PlayerRelay(self.f.manager,port=0)
        self.f.manager.player_relay=self.relay;self.addCleanup(self.relay.close)
        self.f.installer.install()

    def request(self,method='POST',payload=None,headers=None,path=PATH):
        client=http.client.HTTPConnection('127.0.0.1',self.relay.port,timeout=3)
        try:
            body=json.dumps(self.f.message() if payload is None else payload)
            client.request(method,path,body=body if method=='POST' else None,
                headers=headers or {'Origin':ORIGIN,'Content-Type':'application/json'})
            response=client.getresponse();return response.status,dict(response.getheaders()),json.loads(response.read())
        finally:client.close()

    def test_export_and_restart_use_loopback_only_no_user_storage(self):
        self.assertTrue(self.f.manager.status()['installed'])
        self.assertEqual(self.relay.server.server_address[0],'127.0.0.1')
        saved=self.relay.descriptor();self.relay.close();self.relay.start()
        self.assertEqual(self.relay.descriptor(),saved)
        status,headers,result=self.request()
        self.assertEqual(status,200);self.assertTrue(result['accepted'])
        self.assertEqual(headers['Access-Control-Allow-Origin'],ORIGIN)
        self.assertEqual([call[0] for call in self.f.fake.calls],['register','acquire'])
        report=self.f.manager.diagnostic_snapshot()
        self.assertTrue(report['player_relay']['running'])
        self.assertTrue(report['installation']['relay_current'])
        self.assertEqual(report['player_relay']['accepted'],1)
        self.assertNotIn('http://',json.dumps(report))
        self.assertNotIn(self.f.installer.token,json.dumps(report))

    def test_preflight_permits_only_exact_loopback_route_and_trusted_steam_origin(self):
        status,headers,_=self.request('OPTIONS',headers={'Origin':ORIGIN,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type','Access-Control-Request-Private-Network':'true'})
        self.assertEqual(status,200);self.assertEqual(headers['Access-Control-Allow-Private-Network'],'true')
        self.assertNotIn('*',headers['Access-Control-Allow-Origin'])
        for origin in ('https://evil.test','null','http://steamloopback.host','https://steamloopback.host.evil.test','https://steamloopback.host:443','https://user@steamloopback.host'):
            self.assertFalse(trusted_origin(origin),origin)
            status,headers,_=self.request(headers={'Origin':origin,'Content-Type':'application/json'})
            self.assertEqual(status,403);self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertEqual(self.f.fake.calls,[])

    def test_host_route_content_type_size_and_duplicate_json_are_rejected_before_admission(self):
        for headers,path in (({'Origin':ORIGIN,'Content-Type':'text/plain'},PATH),
            ({'Origin':ORIGIN,'Content-Type':'application/json','Host':'evil.test'},PATH),
            ({'Origin':ORIGIN,'Content-Type':'application/json'},PATH+'?token=private')):
            self.assertIn(self.request(headers=headers,path=path)[0],(400,403))
        self.assertEqual(self.request(payload={'extra':'x'*4096})[0],400)
        client=http.client.HTTPConnection('127.0.0.1',self.relay.port,timeout=3)
        try:
            client.request('POST',PATH,body='{"event":"open","event":"stop"}',headers={'Origin':ORIGIN,'Content-Type':'application/json'})
            response=client.getresponse();self.assertEqual(response.status,400);response.read()
        finally:client.close()
        self.assertEqual(self.f.fake.calls,[])

    def test_token_and_independent_steam_observation_still_gate_acquisition(self):
        message=self.f.message();message['token']='wrong'
        self.assertEqual(self.request(payload=message)[0],403);self.assertEqual(self.relay.snapshot()['last_error'],'AUTH_REFUSED')
        self.assertEqual(self.f.fake.calls,[])
        self.f.fake.current['steam']['observed']='inactive'
        self.assertFalse(self.request()[2]['accepted']);self.assertEqual(self.f.manager.reason,'STEAM_INACTIVE')
        self.assertEqual(self.f.fake.calls,[])

    def test_invalid_http_token_cannot_invalidate_an_existing_conversation(self):
        self.assertTrue(self.request()[2]['accepted'])
        message=self.f.message('heartbeat',2);message['token']='wrong'
        self.assertEqual(self.request(payload=message)[0],403)
        self.assertFalse(self.f.manager.session['terminal'])

    def test_waits_for_gca_two_second_observer_without_assuming_steam_active(self):
        self.f.fake.current['steam']['observed']='inactive'
        timer=threading.Timer(1.85,lambda:self.f.fake.current['steam'].update(observed='active'))
        timer.start();self.addCleanup(timer.cancel)
        self.assertTrue(self.request()[2]['accepted'])
        self.assertEqual([call[0] for call in self.f.fake.calls],['register','acquire'])

    def test_http_csp_is_exact_and_old_prepared_gif_is_reused(self):
        html=(self.f.installer.destination/'index.html').read_text()
        self.assertIn('connect-src '+self.relay.descriptor()['url']+' ',html)
        self.assertIn('/jsaux/v1/diagnostic;',html)
        self.assertNotIn('127.0.0.1:*',html)
        self.assertTrue(self.f.installer.status(True,True)['player_current'])
        self.assertTrue(self.f.manager.status()['prepared']['ready'])
        for descriptor in ({'relay':{'kind':'http-loopback-v1','url':'http://evil.test:1/jsaux/v1/player'}},
                           {'relay':'invalid'},True):
            with self.assertRaises(ScreensaverError):self.f.installer.player_html(descriptor)

    def test_disable_closes_listener_and_preserves_faceplate_preferences(self):
        self.f.manager.configure({'enabled':False})
        self.assertFalse(self.relay.snapshot()['running']);self.assertIsNone(self.relay.server)
        self.assertEqual(self.f.manager.options['mode'],'sync')

    def test_occupied_port_does_not_replace_another_service_or_old_export(self):
        self.relay.close();sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(1);self.addCleanup(sock.close)
        other=PlayerRelay(self.f.manager,port=sock.getsockname()[1]);self.f.manager.player_relay=other
        marker=self.f.installer.destination/'.decky-animated-screensaver.json';before=marker.read_bytes()
        with self.assertRaises(BrokerError):self.f.installer.install()
        self.assertEqual(other.snapshot()['last_error'],'ADDRESS_IN_USE')
        self.assertEqual(before,marker.read_bytes())

    def test_bounded_response_never_reflects_extra_backend_fields(self):
        result=safe_reply({'accepted':True,'token':'private','url':'private','broker_mono_ms':True,
            'candidate':{'candidate_id':'candidate1','deadline_mono_ms':4,'phase_basis':'gif-end-ack-assumption','optical_alignment':'unknown','secret':'private'}})
        self.assertTrue(result['accepted']);self.assertNotIn('broker_mono_ms',result)
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(safe_reply(dict(accepted=False,reason='STEAM_INACTIVE')),dict(accepted=False,reason='STEAM_INACTIVE'))
        for reason in ('PRIVATE PATH',[],{}):self.assertNotIn('reason',safe_reply(dict(reason=reason)))

    def test_diagnostic_plain_post_is_authenticated_read_only_and_included_in_report(self):
        from test_player_debug18 import report
        payload=dict(token=self.f.installer.token,report=report())
        status,headers,value=self.request(payload=payload,path=DEBUG_PATH,headers={'Origin':ORIGIN,'Content-Type':'text/plain;charset=UTF-8'})
        self.assertEqual(status,200);self.assertTrue(value['accepted']);self.assertEqual(self.f.fake.calls,[])
        self.assertEqual(self.relay.snapshot()['requests'],0);self.assertEqual(self.relay.snapshot()['diagnostic_accepted'],1)
        debug=self.f.manager.diagnostic_snapshot()['player_debug'];self.assertEqual(debug['browser']['runs'][0]['events'][0]['event'],'boot')
        payload['token']='wrong';self.assertEqual(self.request(payload=payload,path=DEBUG_PATH)[0],403)
        self.assertNotIn(self.f.installer.token,json.dumps(debug))

    def test_local_preflight_checks_are_not_counted_as_browser_or_hardware_evidence(self):
        value=self.relay.diagnostic_check();self.assertEqual(value,dict(browser_evidence=False,control_preflight=200,diagnostic_preflight=200))
        self.assertEqual(self.relay.snapshot()['preflights'],0);self.assertEqual(self.f.fake.calls,[])
        self.assertTrue(any(e.get('source')=='backend-check' for e in self.relay.debug_snapshot()['http']))

    def test_bad_diagnostic_does_not_mutate_control_session_and_new_export_has_early_bootstrap(self):
        self.assertEqual(self.request(payload=dict(token=self.f.installer.token,report={'schema':'wrong'}),path=DEBUG_PATH)[0],400)
        self.assertIsNone(self.f.manager.session);self.assertEqual(self.f.fake.calls,[])
        html=(self.f.installer.destination/'index.html').read_text()
        self.assertLess(html.index('diagnostic.js'),html.index('catalog.js'));self.assertIn('player.js?v=',html)
        config=(self.f.installer.destination/'diagnostic-config.js').read_text();self.assertIn(self.f.installer.token,config)

    def test_corrupt_bootstrap_receipt_is_reported_not_a_plugin_startup_exception(self):
        from das.studio.installer import MARKER
        path=self.f.installer.destination/MARKER;saved=json.loads(path.read_text());saved['jsaux'].pop('collection_id')
        path.write_text(json.dumps(saved));self.assertTrue(self.f.installer.status(True)['needs_repair'])
        saved['jsaux']=self.f.manager.export_descriptor(True);saved['bridge_token']=123
        path.write_text(json.dumps(saved));self.assertTrue(self.f.installer.status(True)['needs_repair'])
        self.assertTrue(self.f.installer.install()['player_current']);self.assertIsInstance(self.f.installer.token,str)

    def test_origin_contract_shared_with_actual_player_and_frontend(self):
        matrix=json.loads((Path(__file__).parents[1]/'fixtures/steam_origins.json').read_text())
        for expected,items in ((True,matrix['accepted']),(False,matrix['rejected'])):
            for origin in items:self.assertIs(trusted_origin(origin),expected,origin)

    def test_steam_native_screensaver_host_is_admitted_but_token_and_ownership_checks_remain(self):
        origin='https://uioverride-decky-animated-screensaver.steamscreensavers.host'
        headers={'Origin':origin,'Content-Type':'application/json'}
        self.assertTrue(self.request(headers=headers)[2]['accepted'])
        self.assertEqual([call[0] for call in self.f.fake.calls],['register','acquire'])
        message=self.f.message('heartbeat',2);message['token']='wrong'
        self.assertEqual(self.request(payload=message,headers=headers)[0],403)
        self.assertFalse(self.f.manager.session['terminal'])
        self.assertTrue(any(e.get('origin',{}).get('category')=='screensaver-plugin' for e in self.relay.debug_snapshot()['http']))

    def test_unknown_and_opaque_origins_still_fail_and_metadata_contains_no_private_host(self):
        for origin in ('null','https://PRIVATE-USER.example:449','https://uioverride-other-plugin.steamscreensavers.host'):
            self.assertEqual(self.request(headers={'Origin':origin,'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.f.fake.calls,[])
        self.assertNotIn('PRIVATE',json.dumps(self.relay.debug_snapshot()))
        self.assertEqual(origin_evidence(['null'])['category'],'opaque')
        self.assertEqual(origin_evidence([])['reason'],'missing')
        self.assertEqual(origin_evidence([ORIGIN,ORIGIN])['reason'],'multiple')
        value=origin_evidence(['https://uioverride-decky-animated-screensaver.steamscreensavers.host:449'])
        self.assertEqual(value['reason'],'port');self.assertEqual(value['port'],449)
