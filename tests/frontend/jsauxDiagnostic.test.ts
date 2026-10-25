import test from 'node:test';
import assert from 'node:assert/strict';
import {JsauxFrameRelay,installJsauxPlayerRelay} from '../../src/jsauxRelay';
import {JsauxStorageRelay} from '../../src/jsauxStorage';
import {getJsauxRelayDiagnostic,relayEnabled,storageAvailable,relayRecovery,storageError} from '../../src/jsauxDiagnostic';
const message=(event='open',sequence=1)=>({event,sequence,token:'PRIVATE_TOKEN',session_id:'PRIVATE_SESSION',collection_id:'a'.repeat(64),mode:'sync'});
const wait=()=>new Promise(resolve=>setTimeout(resolve,0));

test('Actual listener lifetime is separate from configured relay and snapshots are detached',()=>{
  const saved=(globalThis as any).MutationObserver;
  (globalThis as any).MutationObserver=class{observe(){}disconnect(){}};
  const win={addEventListener(){},removeEventListener(){}};
  const doc={documentElement:{},querySelectorAll:()=>[]};
  try{
    relayEnabled(true);storageAvailable(false);relayRecovery();relayRecovery(true);
    const dispose=installJsauxPlayerRelay({client:async()=>({}),window:win as any,document:doc as any});
    const report=getJsauxRelayDiagnostic();assert.equal(report.enabled,true);assert.equal(report.iframe.installed,true);
    report.iframe.received=999999;assert.notEqual(getJsauxRelayDiagnostic().iframe.received,999999);
    dispose();assert.equal(getJsauxRelayDiagnostic().iframe.installed,false);
    assert.equal(getJsauxRelayDiagnostic().enabled,true);
  }finally{(globalThis as any).MutationObserver=saved;}
});

test('Frame diagnostics retain fixed codes and counts, never source messages or backend errors',async()=>{
  const source={postMessage(){}};let calls=0;
  const relay=new JsauxFrameRelay(async()=>{calls++;throw Error('PRIVATE_BACKEND_ERROR');});
  const event={origin:'https://steamloopback.host',source,data:{type:'das-jsaux-player-v1',payload:message()}} as any;
  const frame={src:'https://steamloopback.host/config/uioverrides/screensavers/decky-animated-screensaver/index.html',contentWindow:source};
  const before=getJsauxRelayDiagnostic();
  assert.equal(relay.receive({...event,origin:'https://PRIVATE_HOST'},[frame]),false);
  assert.equal(getJsauxRelayDiagnostic().iframe.last_rejection,'UNTRUSTED_ORIGIN');
  assert(relay.receive(event,[frame]));await wait();
  const report=getJsauxRelayDiagnostic();assert.equal(calls,1);
  assert.equal(report.iframe.routed,before.iframe.routed+1);assert.equal(report.iframe.errors,before.iframe.errors+1);
  assert.equal(report.iframe.last_error,'BACKEND_FAILED');
  assert(!JSON.stringify(report).includes('PRIVATE_'));assert(!JSON.stringify(report).includes('steamloopback'));
  const counted=report.iframe.received;
  assert.equal(relay.receive({...event,data:{type:'unrelated',payload:'PRIVATE_TOKEN'}},[frame]),false);
  assert.equal(getJsauxRelayDiagnostic().iframe.received,counted);
  relay.dispose();
});

test('Native diagnostics distinguish empty slots, malformed API return, backend and native write failures',async()=>{
  const before=getJsauxRelayDiagnostic();let calls=0;
  const relay=new JsauxStorageRelay(async()=>{calls++;throw Error('PRIVATE_BACKEND_ERROR');},
    {GetString:()=>'',SetString:()=>{throw Error('PRIVATE_NATIVE_ERROR');}});
  assert.equal(await relay.receive(''),false);assert.equal(getJsauxRelayDiagnostic().storage.received,before.storage.received);
  assert.equal(await relay.receive({PRIVATE_VALUE:1}),false);
  assert.equal(getJsauxRelayDiagnostic().storage.last_rejection,'INVALID_STORAGE');
  assert(await relay.receive(JSON.stringify({at:1000,payload:message()}),1000));
  const report=getJsauxRelayDiagnostic();assert.equal(calls,1);
  assert.equal(report.storage.backend_errors,before.storage.backend_errors+1);
  assert.equal(report.storage.write_errors,before.storage.write_errors+1);
  assert.equal(report.storage.last_error,'WRITE_FAILED');assert(!JSON.stringify(report).includes('PRIVATE_'));
  relay.dispose();
});

test('Native read errors are visible and disposal stops the existing timer without telemetry calls',async()=>{
  const before=getJsauxRelayDiagnostic();let calls=0;
  const relay=new JsauxStorageRelay(async()=>{calls++;return {};},
    {GetString:()=>{throw Error('PRIVATE_READ_ERROR');},SetString:()=>{}});
  relay.start();await wait();
  const report=getJsauxRelayDiagnostic();assert.equal(report.storage.running,true);
  assert.equal(report.storage.probes,before.storage.probes+1);
  assert.equal(report.storage.read_errors,before.storage.read_errors+1);assert.equal(report.storage.last_error,'READ_FAILED');
  relay.dispose();assert.equal(getJsauxRelayDiagnostic().storage.running,false);assert.equal(calls,0);
});
test('Native error evidence keeps only a fixed exception class and numeric operation result',()=>{
  storageError('read_errors','READ_FAILED',{eresult:2,message:'PRIVATE_TOKEN /home/private',name:'PRIVATE_NAME'});
  let report=getJsauxRelayDiagnostic();assert.equal(report.storage.last_error_name,'OperationResponse');assert.equal(report.storage.last_native_result,2);
  assert(!JSON.stringify(report).includes('PRIVATE_'));
  storageError('read_errors','READ_FAILED',new TypeError('PRIVATE_VALUE'));
  report=getJsauxRelayDiagnostic();assert.equal(report.storage.last_error_name,'TypeError');assert.equal(report.storage.last_native_result,null);
  assert(!JSON.stringify(report).includes('PRIVATE_'));
});
