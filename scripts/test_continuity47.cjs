const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(mode,scenario,controller){
 let now=0,id=0,heartbeats=0,shown=0,deadline=0;
 const timers=new Map(),calls=[],trace=[],events=new Map(),docEvents=new Map();
 const timer=(fn,ms=0)=>{timers.set(++id,{at:now+ms,fn});return id;};
 const win={performance:{now:()=>now},setTimeout:timer,clearTimeout:n=>timers.delete(n),
  location:{href:'https://decky-animated-screensaver.steamloopback.host/index.html'},
  addEventListener:(k,f)=>events.set(k,f),removeEventListener:k=>events.delete(k),
  crypto:{randomUUID:()=> 'session47'},DAS_PLAYER_DEBUG:{record:(event,data)=>trace.push({event,...data})}};
 win.parent=win;const doc={hidden:false,referrer:'',addEventListener:(k,f)=>docEvents.set(k,f),removeEventListener:k=>docEvents.delete(k)};
 win.fetch=async(_url,options)=>{
  const p=JSON.parse(options.body);calls.push({...p,at:now});let result={accepted:true,lease_remaining_ms:8000};
  if(p.event==='clock')result={broker_mono_ms:Math.floor(now+100000)};
  if(p.event==='ready'){deadline=p.deadline_mono_ms;result={accepted:true,gate_accepted:true};}
  if(p.event==='started'&&controller){if(scenario==='lost-ack')return new Promise(()=>{});result.gca_owned=true;}
  if(p.event==='heartbeat'){
   heartbeats++;
   const beforeStart=mode==='sync'&&heartbeats===1;
   if(!beforeStart&&scenario==='persistent')throw Error('offline');
   if(!beforeStart&&['http','timeout','late'].includes(scenario)){
    scenario='recovered';
    if(f.initial==='http')return {ok:false};
    if(f.initial==='timeout')return new Promise(()=>{});
    if(f.initial==='late')return new Promise(resolve=>timer(()=>resolve({ok:true,text:async()=>JSON.stringify(result)}),2500));
   }
   if(!beforeStart&&scenario==='denied')result={accepted:false,reason:'DISPLAY_OFF'};
   else result={...result,candidate:{candidate_id:'candidate47',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'}};
  }
  if(controller&&scenario==='lost-ack'&&calls.some(p=>p.event==='started')&&p.event==='heartbeat')result.gca_owned=true;
  return {ok:true,text:async()=>JSON.stringify(result)};
 };
 const context={module:{exports:{}},URL};vm.runInNewContext(fs.readFileSync(process.env.DAS_PLAYER_SOURCE||'assets/player/player.js','utf8'),context);
 const f={initial:scenario,win,doc,calls,trace,events,docEvents,get shown(){return shown;},
  async advance(ms){const until=now+ms;for(let n=0;n<2000;n++){
    for(let i=0;i<200;i++)await Promise.resolve();
    let next=[...timers].filter(([,v])=>v.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];
    if(!next){now=until;for(let i=0;i<200;i++)await Promise.resolve();next=[...timers].filter(([,v])=>v.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)return;}
    timers.delete(next[0]);now=Math.max(now,next[1].at);next[1].fn();
   }throw Error('unbounded timer loop');}};
 f.lifecycle=context.module.exports.createJsauxLifecycle(win,doc,{bridge_token:'token47',jsaux:{enabled:true,mode,controller,collection_id:'a'.repeat(64),relay:{kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'}}});
 f.lifecycle.ready(()=>shown++);return f;
}
for(const mode of ['sync','async']){
 for(const scenario of ['accepted','lost-ack'])test(`${mode}: GCA handoff ${scenario} ends browser heartbeats for hours`,async()=>{
  const f=fixture(mode,scenario,'GabeCubeAura');await f.advance(12000);
  assert.equal(f.shown,1);assert(f.trace.some(p=>p.event==='gca-handoff'));
  const count=f.calls.length;await f.advance(7200000);assert.equal(f.calls.length,count);
  assert.equal(f.calls.filter(p=>p.event==='open').length,1);assert.equal(f.calls.filter(p=>p.event==='ready').length,1);
  assert.equal(f.calls.filter(p=>p.event==='started').length,1);
  f.events.get('pagehide')?.();await f.advance(3000);
  assert.equal(f.calls.filter(p=>p.event==='open').length,1);
 });
 for(const failure of ['http','timeout','late'])test(`${mode}: isolated ${failure} heartbeat recovers same presentation`,async()=>{
  const f=fixture(mode,failure);await f.advance(12000);
  assert.equal(f.shown,1);assert.equal(f.calls.filter(p=>p.event==='stop').length,0,JSON.stringify({calls:f.calls,trace:f.trace}));
  assert.equal(f.calls.filter(p=>p.event==='open').length,1);assert.equal(f.calls.filter(p=>p.event==='ready').length,1);
  assert(f.calls.filter(p=>p.event==='heartbeat').length>=4);
  assert(f.trace.some(p=>p.event==='heartbeat-degraded'));assert(f.trace.some(p=>p.event==='heartbeat-recovered'));
  const seq=f.calls.map(p=>p.sequence);assert(seq.every((n,i)=>!i||n>seq[i-1]));f.lifecycle.stop();
 });
 test(`${mode}: persistent loss stops at known deadline without replay`,async()=>{
  const f=fixture(mode,'persistent');await f.advance(15000);
  const stops=f.calls.filter(p=>p.event==='stop');assert.equal(stops.length,1);assert(stops[0].at<=8000);
  assert.equal(f.calls.filter(p=>p.event==='open').length,1);
  const count=f.calls.length;await f.advance(20000);assert.equal(f.calls.length,count);
 });
 test(`${mode}: explicit denial is terminal`,async()=>{
  const f=fixture(mode,'denied');await f.advance(6000);
  assert.equal(f.calls.filter(p=>p.event==='stop').length,1);
  assert.equal(f.calls.find(p=>p.event==='stop').reason,'broker-refused');
 });
 test(`${mode}: hidden/unload during timeout cannot revive a stopped lifecycle`,async()=>{
  const f=fixture(mode,'timeout');await f.advance(2500);f.doc.hidden=true;f.docEvents.get('visibilitychange')();
  await f.advance(10000);assert.equal(f.calls.filter(p=>p.event==='stop').length,1);
  assert.equal(f.calls.find(p=>p.event==='stop').reason,'visibility-hidden');
  const count=f.calls.length;await f.advance(10000);assert.equal(f.calls.length,count);
 });
}
