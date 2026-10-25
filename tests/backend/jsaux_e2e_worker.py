"""Test-only RPC host: actual DAS plugin + actual GCA broker, simulated USB."""
import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py_modules'),str(Path(os.environ['DAS_TEST_GCA_ROOT']).resolve()/'py_modules')]
from das.jsaux.client import BrokerClient
from das.jsaux.collection import compile_pages
from das.studio.media import Media
from signalbar.jsaux_broker.core import Broker
from signalbar.jsaux_broker.server import BrokerServer
from test_jsaux_interop import Hardware

async def run():
    with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
        root=Path(temporary).resolve();steam=root/'Steam';steam.mkdir()
        os.environ['DAS_STEAM_ROOT']=str(steam)
        sys.modules['decky']=types.SimpleNamespace(DECKY_PLUGIN_SETTINGS_DIR=str(root/'settings'),DECKY_PLUGIN_DIR=str(ROOT))
        spec=importlib.util.spec_from_file_location('das_e2e_plugin',ROOT/'main.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        hardware=Hardware();broker=Broker(root/'broker-cache',hardware);server=BrokerServer(broker,root/'runtime');server.start()
        # This fixture exercises the retained classic 1.0 DAS relay. The paired
        # 1.1 direct-player route is exercised by studio_owner50_worker.py.
        broker.player_runtime.close()
        plugin=module.Plugin()
        try:
            await plugin._main();plugin._status()
            plugin.jsaux.broker.close();plugin.jsaux.broker=BrokerClient(root/'runtime')
            plugin.service.compiler=Media(str(Path(os.environ['DAS_TEST_FFMPEG']).resolve()))
            if os.environ.get('DAS_TEST_FFPROBE'):plugin.service.compiler._probe=str(Path(os.environ['DAS_TEST_FFPROBE']).resolve())
            game_count=int(os.environ.get('DAS_TEST_GAME_COUNT','1'))
            assert 1<=game_count<=24
            plugin.service.games_provider=lambda:[dict(appid=620+n,name='Fixture '+str(n)) for n in range(game_count)]
            plugin.service.configure(dict(show_cover=False,show_logo=False,scene_seconds=24))
            plugin.service._assets=lambda number,role:[dict(id=620,animated=True,kind='hero',author='Fixture',url='https://cdn.steamgriddb.com/fixture.gif')] if role=='animation' else []
            source=plugin.service.catalog.managed('fixture.gif')
            source.write_bytes(compile_pages([bytes([0x93])*3456,bytes([0xd2])*3456],4,'none')[0])
            plugin.service._download=lambda asset:source
            plugin.jsaux.refresh();plugin.jsaux.configure(dict(enabled=True,mode=os.environ.get('DAS_TEST_MODE','sync')))
            await plugin.studio('prepare')
            for _ in range(400):
                # The TV job clears busy before its after_prepare callback.
                # Wait for that real thread too, as the production workspace does.
                if not (plugin.service.thread and plugin.service.thread.is_alive()) and not plugin.jsaux.busy():break
                await asyncio.sleep(.05)
            state=await plugin.studio('state')
            assert state['ready_count']==game_count,state
            assert state['jsaux']['prepared']['ready'],state
            assert not hardware.commands,hardware.commands
            await plugin.studio('install',dict(confirm=True))
            catalog=json.loads((plugin.installer.destination/'catalog.js').read_text().split('=',1)[1].rstrip(';\n'))
            print(json.dumps(dict(setup=True,catalog=catalog,player_html=(plugin.installer.destination/'index.html').read_text(),
                fixture_media=base64.b64encode(source.read_bytes()).decode('ascii'),
                diagnostic_config=(plugin.installer.destination/'diagnostic-config.js').read_text())),flush=True)
            for raw in sys.stdin:
                request=json.loads(raw)
                try:
                    if request.get('new_activation'):
                        hardware.state['steam'].update(activation_id=request['new_activation'],activation_closed=False)
                        result=dict(changed=True)
                    elif request.get('steam_inactive'):
                        hardware.state['steam']['observed']='inactive'
                        broker.tick()
                        result=dict(changed=True)
                    elif request.get('report'):result=dict(commands=hardware.commands,jsaux=plugin.jsaux.status(),delivery=plugin.jsaux.diagnostic_snapshot())
                    else:result=await plugin.studio('jsaux_player',request['payload'])
                    print(json.dumps(dict(id=request['id'],result=result)),flush=True)
                except Exception as error:print(json.dumps(dict(id=request['id'],error=type(error).__name__)),flush=True)
        finally:
            await plugin._unload();server.stop();broker.stop()

if __name__=='__main__':asyncio.run(run())
