import test from 'node:test';
import assert from 'node:assert/strict';
import {JsauxFrameRelay,playerMessage,safeReply,steamRelayOrigin} from '../../src/jsauxRelay';
import {readFileSync} from 'node:fs';
import {jsauxVisible,jsauxPreviewURL,jsauxBusy,type JsauxState} from '../../src/types';
const origin='https://steamloopback.host';
const message=(event='open',sequence=1)=>({event,sequence,token:'installed-token',session_id:'session1',collection_id:'a'.repeat(64),mode:'sync'});
test('Steam origin contract admits only our mapped screensaver hosts and legacy origins',()=>{
  const matrix=JSON.parse(readFileSync(new URL('../fixtures/steam_origins.json',import.meta.url),'utf8'));
  for(const [expected,items] of [[true,matrix.accepted],[false,matrix.rejected]] as const)
    for(const origin of items)assert.equal(steamRelayOrigin(origin),expected,origin);
});
test('Progressive card, bounded native preview and active-only observation',()=>{
  assert.equal(jsauxVisible(undefined),false);assert.equal(jsauxVisible({detected:false,configured:false} as JsauxState),false);
  assert.equal(jsauxVisible({detected:false,compatible:true,configured:true} as JsauxState),false);
  assert.equal(jsauxVisible({detected:true,compatible:false,configured:true} as JsauxState),false);
  assert(jsauxVisible({detected:true,compatible:true,configured:true} as JsauxState));assert(jsauxBusy({phase:'preparing'} as JsauxState));
  assert.equal(jsauxBusy({phase:'idle'} as JsauxState),false);
  assert(jsauxPreviewURL('data:image/gif;base64,R0lGODlh'));
  for(const x of ['https://cdn.steamgriddb.com/a.gif','data:image/svg+xml;base64,AAAA','data:image/gif;base64,'+'A'.repeat(300000)])assert.equal(jsauxPreviewURL(x),undefined);
});
test('Exact payloads and immutable native gate reject malformed requests',()=>{
  assert(playerMessage(message()));
  assert.equal(playerMessage({...message(),extra:'bad'}),null);
  assert.equal(playerMessage({...message(),token:'secret with space'}),null);
  assert.equal(playerMessage({...message('ready'),ready_mono_ms:10,deadline_mono_ms:2600,clock_uncertainty_ms:0}),null);
  assert(playerMessage({...message('ready'),ready_mono_ms:10,deadline_mono_ms:2510,clock_uncertainty_ms:50}));
  assert.equal(playerMessage({...message('ready'),ready_mono_ms:10,deadline_mono_ms:2510,clock_uncertainty_ms:51}),null);
});
test('Installed exact iframe only; stale sequences and previews never reach backend',async()=>{
  const calls:any[]=[],replies:any[]=[];const source={postMessage:(p:unknown)=>replies.push(p)};
  const frame={src:origin+'/config/uioverrides/screensavers/decky-animated-screensaver/index.html',contentWindow:source,isConnected:true};
  const relay=new JsauxFrameRelay(async(a,p)=>{calls.push([a,p]);return {accepted:true,capability:'private',broker_mono_ms:1};});
  const event={origin,source,data:{type:'das-jsaux-player-v1',payload:message()}} as any;
  assert.equal(relay.receive({...event,origin:'https://evil.test'},[frame]),false);
  assert.equal(relay.receive(event,[{...frame,src:'http://127.0.0.1:1234/preview'}]),false);
  assert.equal(relay.receive(event,[frame]),true);assert.equal(relay.receive(event,[frame]),false);
  await new Promise(r=>setTimeout(r,0));assert.equal(calls.length,1);assert.equal(replies[0].result.capability,undefined);
  frame.isConnected=false;relay.check();await new Promise(r=>setTimeout(r,0));assert.equal(calls[1][1].event,'stop');relay.dispose();
});
test('Backend replies only expose bounded coordination evidence, not secrets',()=>{
  assert.deepEqual(safeReply({accepted:true,capability:'never',socket_path:'/secret',physical_alignment:'proven'}),{accepted:true});
  assert.deepEqual(safeReply({candidate:{candidate_id:'a',deadline_mono_ms:100,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'}}),
    {candidate:{candidate_id:'a',deadline_mono_ms:100,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'}});
  assert.deepEqual(safeReply({alignment_ms:-5000,timing:{reference_mono_ms:400,uncertainty_ms:3,basis:'broker-confirmation-event',secret:'never'}}),
    {alignment_ms:-5000,timing:{reference_mono_ms:400,uncertainty_ms:3,basis:'broker-confirmation-event'}});
  assert.deepEqual(safeReply({alignment_ms:1,timing:{reference_mono_ms:-1,uncertainty_ms:3,basis:'broker-confirmation-event'}}),{});
});
