import test from 'node:test';
import assert from 'node:assert/strict';
import {JsauxStorageRelay} from '../../src/jsauxStorage';
const message=(event='open',sequence=1)=>({event,sequence,token:'installed-token',session_id:'session1',collection_id:'a'.repeat(64),mode:'sync'});
test('Cross-window relay authenticates through backend and ignores stale, duplicate or malformed storage',async()=>{
  const calls:any[]=[],replies:any[]=[];
  const relay=new JsauxStorageRelay(async(a,p)=>{calls.push(p);return {accepted:true,capability:'secret'};},
    {GetString:()=>'',SetString:(k,v)=>replies.push(JSON.parse(v))});
  const raw=(p:any,at=1000)=>JSON.stringify({at,payload:p});
  assert.equal(await relay.receive(raw(message(),0),7000),false);
  assert.equal(await relay.receive(raw({...message(),extra:'bad'}),1000),false);
  assert(await relay.receive(raw(message()),1000));assert.equal(replies[0].result.capability,undefined);
  assert.equal(await relay.receive(raw(message()),1000),false);
  assert.equal(await relay.receive(raw({...message('clock',2),session_id:'other'}),1001),false);
  assert(await relay.receive(raw(message('clock',2)),1001));
  relay.dispose();await Promise.resolve();assert.equal(calls.at(-1).event,'stop');assert.equal(calls.at(-1).sequence,3);
});
