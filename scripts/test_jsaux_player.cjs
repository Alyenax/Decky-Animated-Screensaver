const test=require('node:test');const assert=require('node:assert/strict');
const context={module:{exports:{}},URL};require('node:vm').runInNewContext(require('node:fs').readFileSync(require('node:path').join(__dirname,'../assets/player/player.js'),'utf8'),context);
const {clockMapping,alignmentEpoch,createJsauxLifecycle,playerRelayURL,presentationSlot,presentationMatches}=context.module.exports;
test('Explicit per-game still is admitted without enabling static fallback globally',()=>{
 const {catalogGames,settings}=context.module.exports;
 const game={included:true,status:'ready',media:{file:'media/test.jpg',thumbnail:'media/thumb.jpg',animated:false}};
 const selected=catalogGames({games:[game,{...game,explicitStill:true},{...game,explicitStill:'true'}]},settings({staticFallback:false}));
 assert.equal(selected.length,1);assert.equal(selected[0].explicitStill,true);
 assert.equal(catalogGames({games:[game]},settings({staticFallback:true})).length,1);
});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
test('Actual standalone player shares the backend/frontend Steam origin contract',()=>{
 const matrix=JSON.parse(require('node:fs').readFileSync('tests/fixtures/steam_origins.json','utf8'));
 for(const [expected,items] of [[true,matrix.accepted],[false,matrix.rejected]])for(const origin of items)assert.equal(context.module.exports.steamPlayerOrigin(origin),expected,origin);
});
function fixture(mode='sync',reply=true){
 const listeners=new Set(),events=new Map(),docEvents=new Map(),calls=[];let deadline;
 const parent={postMessage(p){const m=p.payload;calls.push(m);if(!reply)return;
   let result={accepted:true};
   if(m.event==='clock')result={broker_mono_ms:Math.floor(performance.now()+100000)};
   if(m.event==='ready'){deadline=m.deadline_mono_ms;result={accepted:true,gate_accepted:true};}
   if(m.event==='heartbeat')result={accepted:true,candidate:{candidate_id:'candidate1',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'}};
   queueMicrotask(()=>{for(const listener of listeners)listener({source:parent,origin:'https://steamloopback.host',data:{type:'das-jsaux-reply-v1',session_id:m.session_id,sequence:m.sequence,result}});});
 }};
 const win={parent,performance,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,
   addEventListener:(t,f)=>t==='message'?listeners.add(f):events.set(t,f),removeEventListener:(t,f)=>t==='message'?listeners.delete(f):events.delete(t)};
 const doc={referrer:'https://steamloopback.host/screensaver',hidden:false,addEventListener:(t,f)=>docEvents.set(t,f),removeEventListener:t=>docEvents.delete(t)};
 const catalog={bridge_token:'token1',jsaux:{enabled:true,mode,collection_id:'a'.repeat(64)}};
 return {win,doc,catalog,calls,events,docEvents};
}
test('Document unload and CEF freeze each release once and cancel future heartbeats',async()=>{
 for(const kind of ['beforeunload','freeze']){
  const f=fixture('async');const p=createJsauxLifecycle(f.win,f.doc,f.catalog);p.ready(()=>{});await sleep(30);
  const stop=(kind==='freeze'?f.docEvents:f.events).get(kind);assert(stop);stop();stop();
  assert.equal(f.calls.filter(x=>x.event==='stop').length,1);
  assert(!f.events.has('beforeunload'));assert(!f.docEvents.has('freeze'));
 }
});
test('Three conservative clock samples or TV only',()=>{
 assert(clockMapping([{sent:0,received:10,host:105},{sent:10,received:20,host:115},{sent:20,received:30,host:125}],30));
 assert.equal(clockMapping([{sent:0,received:100,host:100},{sent:0,received:100,host:100},{sent:0,received:100,host:100}],100),null);
 assert.equal(clockMapping([],0),null);
});
test('Signed calibration corrects an absolute confirmation epoch, never the duration or game count',()=>{
 const mapping={lower:100000,uncertainty:4,sampledAt:0};
 const timing={basis:'broker-confirmation-event',reference_mono_ms:105000,uncertainty_ms:3};
 assert.equal(alignmentEpoch(timing,mapping,5500,0,120000),4998);
 assert.equal(alignmentEpoch(timing,mapping,5500,5000,120000),9998);
 assert.equal(alignmentEpoch(timing,mapping,5500,-5000,120000),-2);
 assert.equal(alignmentEpoch(timing,mapping,5500,5000,109000),null,'Correction never extends the deadline');
 for(const change of [{reference_mono_ms:999999},{uncertainty_ms:100},{basis:'optically-perfect'}])
  assert.equal(alignmentEpoch({...timing,...change},mapping,5500,0,120000),null);
 assert.equal(alignmentEpoch(timing,mapping,5500,1,120000),null);
});
test('A delayed heartbeat starts on the reference epoch, not on its response time',async()=>{
 const f=fixture();let reference;
 f.win.location={href:'https://decky-animated-screensaver.steamloopback.host/index.html'};f.win.parent=f.win;
 f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};
 let deadline;
 f.win.fetch=async(url,options)=>{const p=JSON.parse(options.body);f.calls.push(p);let result={accepted:true};
  if(p.event==='clock')result={broker_mono_ms:Math.floor(performance.now()+100000)};
  if(p.event==='ready'){deadline=p.deadline_mono_ms;result={gate_accepted:true};}
  if(p.event==='heartbeat'){reference=performance.now()-400;result={accepted:true,candidate:{candidate_id:'candidate1',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'},timing:{basis:'broker-confirmation-event',reference_mono_ms:Math.floor(reference+100000),uncertainty_ms:1}};}
  return {ok:true,text:async()=>JSON.stringify(result)};
 };
 const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let timing;p.ready(value=>{timing=value;});await sleep(35);
 assert(timing&&Math.abs(timing.epoch-reference)<3,JSON.stringify({timing,reference}));
 assert.equal(f.calls.find(x=>x.event==='started').outcome,'software-coordinated');p.stop();
});
test('Exit cancels a calibrated future start without another acquisition',async()=>{
 const f=fixture();f.win.location={href:'https://decky-animated-screensaver.steamloopback.host/index.html'};f.win.parent=f.win;
 f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};
 let deadline,reference;
 f.win.fetch=async(url,options)=>{const m=JSON.parse(options.body);f.calls.push(m);let result={accepted:true};
  if(m.event==='open')result={accepted:true,alignment_ms:500};
  if(m.event==='clock')result={broker_mono_ms:Math.floor(performance.now()+100000)};
  if(m.event==='ready'){deadline=m.deadline_mono_ms;reference=Math.floor(performance.now()+100000);result={gate_accepted:true};}
  if(m.event==='heartbeat')result={accepted:true,candidate:{candidate_id:'candidate1',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'},timing:{basis:'broker-confirmation-event',reference_mono_ms:reference,uncertainty_ms:1}};
  return {ok:true,text:async()=>JSON.stringify(result)};
 };
 const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let shown=0;p.ready(()=>shown++);await sleep(60);
 assert.equal(shown,0);p.stop();await sleep(520);assert.equal(shown,0);
 assert.equal(f.calls.filter(x=>x.event==='open').length,1);assert.equal(f.calls.filter(x=>x.event==='started').length,0);
});
test('Extended installed start accepts a delayed candidate without waiting the full budget',async()=>{
 const f=fixture();f.catalog.jsaux.sync_wait_ms=15000;
 let offset=0;f.win.performance={now:()=>performance.now()+offset};
 // Hold the first heartbeat while the software clock advances past 2.5 s.
 const post=f.win.parent.postMessage;let first=true;
 f.win.parent.postMessage=p=>{if(p.payload.event==='heartbeat'&&first){first=false;offset=6000;}post(p);};
 const p=createJsauxLifecycle(f.win,f.doc,f.catalog);await sleep(5);let shown=0;p.ready(()=>shown++);
 await sleep(40);assert.equal(shown,1,JSON.stringify(f.calls));
 const ready=f.calls.find(x=>x.event==='ready'),started=f.calls.find(x=>x.event==='started');
 assert.equal(ready.deadline_mono_ms-ready.ready_mono_ms,15000);
 assert.equal(started.outcome,'software-coordinated');
 assert(started.started_mono_ms>=ready.ready_mono_ms+6000);p.stop();
});
test('Common manifest matches actual included order; absolute slots do not accumulate delay',()=>{
 const games=[{id:'steam:1'},{id:'sgdb:2'}],settings={sceneDuration:8};
 const catalog={presentation:{version:2,order:[1,-2],page_ms:8000,transition_included:true,orientation:0}};
 assert(presentationMatches(catalog,games,settings));
 assert.equal(presentationMatches(catalog,[games[1],games[0]],settings),false);
 for(let n=0;n<40;n++)assert.equal(presentationSlot(100,100+n*8000+500,8000),n);
});
test('Preview never opens a relay or delays first image',()=>{
 const f=fixture();f.catalog.previewNonce='preview1';const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let shown=0;p.ready(()=>shown++);p.stop();assert.equal(shown,1);assert.equal(f.calls.length,0);
});
test('Previously silent activation guards now report exact metadata-only reasons',()=>{
 const cases=[
  {patch:f=>{f.catalog.previewNonce='preview';},reason:'preview'},
  {patch:f=>{f.catalog.jsaux.enabled=false;},reason:'config-disabled'},
  {patch:f=>{f.catalog.jsaux.mode='bad';},reason:'mode-invalid'},
  {patch:f=>{f.catalog.jsaux.collection_id='bad';},reason:'collection-invalid'},
  {patch:f=>{f.catalog.bridge_token='';},reason:'token-invalid'},
  {patch:f=>{f.win.location={href:'https://unrecognized.test/index.html'};f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};},reason:'origin-refused'},
  {patch:f=>{f.win.location={href:'https://decky-animated-screensaver.steamloopback.host/index.html'};f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://evil.test/player'};},reason:'relay-invalid'},
  {patch:f=>{f.win.location={href:'https://decky-animated-screensaver.steamloopback.host/index.html'};f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};},reason:'fetch-missing'}
 ];
 for(const c of cases){const f=fixture(),events=[];f.win.DAS_PLAYER_DEBUG={record:(event,data)=>events.push({event,...data})};c.patch(f);
  let shown=0;createJsauxLifecycle(f.win,f.doc,f.catalog).ready(()=>shown++);assert.equal(shown,1);
  assert(events.some(e=>e.event==='lifecycle-disabled'&&e.reason===c.reason),JSON.stringify(events));assert.equal(f.calls.length,0);
 }
});
test('HTTP player uses one authenticated local transport, never native Storage or iframe',async()=>{
 const f=fixture();f.win.location={href:'https://decky-animated-screensaver.steamloopback.host/index.html'};f.win.parent=f.win;
 let native=0,deadline;const calls=[];
 f.win.SteamClient={Storage:{GetString(){native++;throw Error('missing key');},SetString(){native++;throw Error('native forbidden');}}};
 f.win.AbortController=AbortController;
 f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};
 f.win.fetch=async(url,options)=>{
  assert.equal(url,f.catalog.jsaux.relay.url);assert.equal(options.redirect,'error');assert.equal(options.credentials,'omit');
  const p=JSON.parse(options.body);calls.push(p);let result={accepted:true};
  if(p.event==='clock')result={broker_mono_ms:Math.floor(performance.now()+100000)};
  if(p.event==='ready'){deadline=p.deadline_mono_ms;result={gate_accepted:true};}
  if(p.event==='heartbeat')result={accepted:true,candidate:{candidate_id:'candidate1',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'}};
  return {ok:true,text:async()=>JSON.stringify(result)};
 };
 const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let shown=0;p.ready(()=>shown++);await sleep(35);
 assert.equal(shown,1);assert.equal(native,0);assert.equal(f.calls.length,0);
 assert.equal(calls.filter(x=>x.event==='open').length,1);assert.equal(calls.find(x=>x.event==='started').outcome,'software-coordinated');
 assert.equal(f.win.DAS_JSAUX_TRANSPORT.kind,'http-loopback-v1');p.stop();assert.equal(calls.at(-1).event,'stop');
});
test('Local endpoint validation rejects remote, redirect-like and preview transports',()=>{
 for(const url of ['http://evil.test:37679/jsaux/v1/player','https://127.0.0.1:37679/jsaux/v1/player','http://127.0.0.1:37679/other','http://127.0.0.1:37679/jsaux/v1/player?token=secret','http://user@127.0.0.1:37679/jsaux/v1/player'])
  assert.equal(playerRelayURL({kind:'http-loopback-v1',url}),null,url);
 const f=fixture();f.catalog.previewNonce='preview';f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};
 f.win.fetch=()=>{throw Error('preview must not send');};let shown=0;createJsauxLifecycle(f.win,f.doc,f.catalog).ready(()=>shown++);assert.equal(shown,1);
});
test('Ambiguous HTTP failure never resends through Storage or iframe',async()=>{
 const f=fixture();f.win.location={href:'https://decky-animated-screensaver.steamloopback.host/index.html'};let calls=0;
 f.catalog.jsaux.relay={kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'};
 f.win.fetch=async()=>{calls++;throw Error('network failure with private body');};
 const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let shown=0;p.ready(()=>shown++);await sleep(20);
 assert.equal(shown,1);assert.equal(calls,2);assert.equal(f.calls.length,0);assert.equal(f.win.DAS_JSAUX_TRANSPORT.last_error,'HTTP_REQUEST_FAILED');
 assert(!JSON.stringify(f.win.DAS_JSAUX_TRANSPORT).includes('private'));p.stop();
});
test('Sync admission precedes immutable ready gate and coordinated TV start',async()=>{
 const f=fixture();const p=createJsauxLifecycle(f.win,f.doc,f.catalog);await sleep(5);let shown=0;p.ready(()=>shown++);
 await sleep(30);assert.equal(shown,1,JSON.stringify(f.calls));assert.equal(f.calls.filter(x=>x.event==='clock').length,3);
 const ready=f.calls.find(x=>x.event==='ready'),started=f.calls.find(x=>x.event==='started');assert.equal(ready.deadline_mono_ms-ready.ready_mono_ms,2500);
 assert.equal(started.outcome,'software-coordinated');p.stop();assert.equal(f.calls.at(-1).event,'stop');
});
test('Async TV never waits, but hardware still requires ready before started',async()=>{
 const f=fixture('async');const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let shown=0;p.ready(()=>shown++);assert.equal(shown,1);
 await sleep(25);const events=f.calls.map(x=>x.event);assert(events.indexOf('ready')>events.indexOf('open'));assert(events.indexOf('started')>events.indexOf('ready'));
 assert.equal(f.calls.find(x=>x.event==='started').outcome,'independent');p.stop();
});
test('Unresponsive backend cannot block TV past readiness watchdog',async()=>{
 const f=fixture('sync',false);const p=createJsauxLifecycle(f.win,f.doc,f.catalog);let shown=0;p.ready(()=>shown++);
 await sleep(2600);assert.equal(shown,1);p.stop();assert.equal(f.calls.filter(x=>x.event==='ready').length,0);
});
