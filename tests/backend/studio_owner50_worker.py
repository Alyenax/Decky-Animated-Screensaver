"""Browser fixture: real installed export and GCA, DAS stopped before playback."""
import json
import os
from pathlib import Path
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py_modules')]
import test_studio_owner50 as fixture

def run():
    case=fixture.StudioOwnerTests();case.setUp()
    try:
        case.studio()
        mode=os.environ.get('DAS_TEST_MODE','sync')
        if mode=='async':
            case.manager.configure(dict(mode='async'))
            case.manager.receipt['collection_id']=case.manager.identity()
            case.manager.registered_boot=None
            case.installer.install()
        destination=case.installer.destination;token=case.installer.token
        catalog=json.loads((destination/'catalog.js').read_text().split('=',1)[1].rstrip(';\n'))
        # Keep the actual installer CSP, config and scripts; source animation is a UI fixture.
        for game in catalog['games']:
            game['media'].update(format='png',animated=True)
        case.manager.shutdown();case.service.shutdown()
        print(json.dumps(dict(setup=True,catalog=catalog,player_html=(destination/'index.html').read_text(),diagnostic_config=(destination/'diagnostic-config.js').read_text())),flush=True)
        for raw in sys.stdin:
            r=json.loads(raw)
            try:
                if r.get('hours'):
                    case.broker.clock=lambda:time.monotonic()+7200
                    case.broker.tick()
                if r.get('exit'):
                    case.hardware.state['steam']['observed']='inactive';case.broker.tick()
                result=dict(runtime=case.broker.player_runtime.snapshot(),state=case.broker.player_runtime.state(dict(token=token)),commands=case.hardware.commands)
                print(json.dumps(dict(id=r['id'],result=result)),flush=True)
            except Exception as error:print(json.dumps(dict(id=r['id'],error=type(error).__name__)),flush=True)
    finally:case.doCleanups()

if __name__=='__main__':run()
