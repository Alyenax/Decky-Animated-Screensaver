"""Paired production DAS Unix client -> real GCA broker and HTTP player.

Requires an explicit GCA checkout; USB/Steam observations are simulated.
No skip or replacement fixture can turn a missing checkout into a pass.
"""
import hashlib,json,os,random,sys,tempfile,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
gca=Path(os.environ['DAS_TEST_GCA_ROOT']).resolve()
assert (gca/'py_modules/signalbar/jsaux_broker/player_batches.py').is_file()
sys.path[:0]=[str(root/'py_modules'),str(gca/'py_modules'),str(gca/'tests/backend')]
from das.jsaux.client import BrokerClient
from das.jsaux.protocol import BrokerError
from das.jsaux.collection import compile_pages
from signalbar.jsaux_broker.core import Broker
from signalbar.jsaux_broker.server import BrokerServer
from test_jsaux_broker_core import Adapter
class Clock:
    now=0
    def __call__(self):return time.monotonic()+self.now

with tempfile.TemporaryDirectory(prefix='bp-',dir='/private/tmp') as temp:
    work=Path(temp);hardware=Adapter();clock=Clock();broker=Broker(work/'data',hardware,clock=clock)
    broker.player_runtime.start(0);server=BrokerServer(broker,work/'run');server.start()
    client=BrokerClient(work/'run');collection='c'*64;secret='s'*48;ids=[]
    def replace(job,report):hardware.jobs.append(job);hardware.report=report;return True
    hardware.replace=replace
    try:
        client.discover(True)
        assert client.wire_version=='1.2' and client.hello['capabilities']['autonomous_batches']
        for index in range(7):
            rng=random.Random(index)
            pages=[bytes(rng.randrange(0,128) for _ in range(3456)) for _ in range(3)]
            data,details=compile_pages(pages,2,'none');path=work/f'lot{index}.gif';path.write_bytes(data)
            result=client.register(path,collection);validation=result.get('validation_id');until=time.monotonic()+12
            while not result.get('content_id'):
                assert time.monotonic()<until,result
                if result.get('state')=='rejected':raise AssertionError(result)
                time.sleep(.06);result=client.operation(validation_id=validation)
            ids.append(result['content_id'])
            result=client.request('publish_player_batch',dict(token=secret,content_id=ids[-1],collection_id=collection,alignment_ms=0,index=index,count=7))
            assert result['published']==(index==6)
        assert len(broker.contents)==4 and not hardware.jobs
        endpoint=result['relay']['url'];sequence=0
        def player(event,**extra):
            global sequence
            sequence+=1
            payload=dict(event=event,token=secret,collection_id=collection,session_id='pair',mode='async',sequence=sequence,**extra)
            request=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':'https://decky-animated-screensaver.steamloopback.host'})
            with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
        assert player('open')['accepted']
        assert player('ready',ready_mono_ms=None,deadline_mono_ms=None,clock_uncertainty_ms=None)['gate_accepted']
        lease=broker.lease;operation=lease['operation_id'];hardware.report(operation,transfer_state='confirmed',fresh_ack=True)
        assert player('started',started_mono_ms=None,outcome='independent',candidate_id=None)['gca_owned']
        client.close() # No DAS/browser renewal is used for playlist lifetime.
        for index in range(1,10):
            clock.now+=10;broker.tick();until=time.monotonic()+5
            while lease.get('batch_advancing'):
                assert time.monotonic()<until
                time.sleep(.01)
            assert lease['content_id']==ids[index%7],lease
            hardware.report(operation,transfer_state='confirmed',fresh_ack=True)
            assert len(broker.contents)<=4
        assert len(hardware.jobs)==10 and len(hardware.reservations)==1 and not hardware.restorations
        hardware.state['steam']['observed']='inactive';broker.tick()
        assert len(hardware.restorations)==1 and not broker.is_valid(operation)
        print(json.dumps(dict(paired=True,wire='1.2',lots=7,rotations=9,same_operation=True,home_between_lots=False,usb='simulated',physical_acceptance=False)))
    finally:
        client.close();server.stop();broker.stop();broker.worker.shutdown(wait=True)
