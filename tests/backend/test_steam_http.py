import io
import json
import ssl
import unittest
from unittest.mock import Mock,patch
from urllib.error import URLError,HTTPError
from das.studio.steam_http import public_json,SteamHTTPError

URL='https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/'

class SteamHTTPTests(unittest.TestCase):
    def opener(self,value):
        opener=Mock();opener.open.return_value=io.BytesIO(json.dumps(value).encode());return opener

    def test_normal_request_has_no_auth_and_no_untrusted_redirect(self):
        events=[];opener=self.opener({'response':{'ranks':[]}})
        with patch('das.studio.steam_http.build_opener',return_value=opener) as factory:
            self.assertEqual(public_json(URL,observer=events.append),{'response':{'ranks':[]}})
        self.assertEqual(opener.open.call_count,1)
        req=opener.open.call_args.args[0];self.assertIsNone(req.get_header('Authorization'))
        self.assertEqual(events[0]['stage'],'steam_chart');self.assertEqual(events[0]['result'],'ok')
        self.assertEqual(type(factory.call_args.args[0]).__name__,'NoRedirect')

    def test_embedded_python_ca_failure_retries_system_bundle_with_verified_tls(self):
        first=Mock();first.open.side_effect=URLError(ssl.SSLCertVerificationError('private-path-secret'))
        second=self.opener({'response':{}});events=[];context=ssl.create_default_context()
        with patch('das.studio.steam_http.build_opener',side_effect=[first,second]) as factory,patch('das.studio.steam_http.Path.is_file',return_value=True),patch('das.studio.steam_http.ssl.create_default_context',return_value=context) as create:
            public_json(URL,observer=events.append)
        create.assert_called_once();self.assertIn('cafile',create.call_args.kwargs)
        handler=factory.call_args.args[1]
        self.assertIs(handler._context,context);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(context.check_hostname)
        self.assertLessEqual(second.open.call_args.kwargs['timeout'],8)
        self.assertEqual(events[0]['tls_trust'],'system');self.assertNotIn('secret',json.dumps(events))

    def test_certificate_failure_without_a_bundle_fails_closed(self):
        first=Mock();first.open.side_effect=URLError(ssl.SSLCertVerificationError('SECRET'))
        with patch('das.studio.steam_http.build_opener',return_value=first),patch('das.studio.steam_http.Path.is_file',return_value=False):
            with self.assertRaises(SteamHTTPError) as caught:public_json(URL)
        self.assertEqual(caught.exception.code,'steam_tls_unavailable');self.assertEqual(first.open.call_count,1)

    def test_http_status_timeout_and_offline_errors_are_redacted_and_distinct(self):
        cases=[(HTTPError(URL,429,'SECRET',{},None),'steam_rate_limited',429),
               (HTTPError(URL,403,'SECRET',{},None),'steam_http_error',403),
               (URLError(TimeoutError('SECRET')),'steam_timeout',0),
               (URLError(OSError('SECRET')),'steam_network_unavailable',0)]
        for error,code,status in cases:
            events=[];opener=Mock();opener.open.side_effect=error
            with patch('das.studio.steam_http.build_opener',return_value=opener):
                with self.assertRaises(SteamHTTPError) as caught:public_json(URL+'?term=PRIVATE_GAME',observer=events.append)
            self.assertEqual(caught.exception.code,code);self.assertEqual(events[-1]['http_status'],status)
            self.assertNotIn('SECRET',str(caught.exception));self.assertNotIn('PRIVATE_GAME',json.dumps(events))
            self.assertEqual(opener.open.call_count,1)

    def test_body_and_json_validation_are_bounded(self):
        for body in (b'x'*21,b'not json',b'[]'):
            opener=Mock();opener.open.return_value=io.BytesIO(body)
            with patch('das.studio.steam_http.build_opener',return_value=opener):
                with self.assertRaises(SteamHTTPError) as caught:public_json(URL,maximum=20)
            self.assertEqual(caught.exception.code,'steam_response_invalid')

    def test_arbitrary_hosts_credentials_ports_and_paths_are_not_opened(self):
        with patch('das.studio.steam_http.build_opener') as factory:
            for url in ('https://evil.test/api/storesearch/','http://store.steampowered.com/api/storesearch/',
                        'https://user:pass@store.steampowered.com/api/storesearch/',
                        'https://store.steampowered.com:444/api/storesearch/','https://api.steampowered.com/other/'):
                with self.assertRaises(SteamHTTPError):public_json(url)
            factory.assert_not_called()
