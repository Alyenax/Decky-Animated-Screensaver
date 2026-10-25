const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('assets/player/diagnostic.js','utf8');
function fixture(){
 const listeners={},logs=[],calls=[],timers=new Map();let id=0,now=0;
 const win={location:{href:'https://decky-animated-screensaver.steamloopback.host/index.html'},document:{hidden:false,addEventListener(k,f){listeners[k]=f;}},
  parent:null,crypto:require('node:crypto').webcrypto,isSecureContext:true,navigator:{onLine:true},console:{info(x){logs.push(x);}},
  addEventListener(k,f){listeners[k]=f;},setTimeout(f){timers.set(++id,f);return id;},clearTimeout(n){timers.delete(n);},AbortController,
  async fetch(url,options){calls.push({url,options});return {ok:true};}};win.parent=win;
 vm.runInNewContext(source,{window:win,URL,Uint8Array,Date:{now:()=>now}});return {win,listeners,logs,calls,timers,advance(ms){now+=ms;}};
}
const config={enabled:true,token:'PRIVATE_TOKEN',relay:{kind:'http-loopback-v1',url:'http://127.0.0.1:37679/jsaux/v1/player'},build:'a'.repeat(12)};
test('Bootstrap runs before catalog, records sanitized errors/CSP, and simple diagnostic route never sends actions',async()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;assert.equal(d.snapshot().events[0].event,'boot');
 d.configure(config);f.listeners.error({target:f.win,error:{name:'TypeError',message:'PRIVATE'},filename:'https://PRIVATE/player.js?token=PRIVATE',lineno:12,colno:3});
 f.listeners.securitypolicyviolation({effectiveDirective:'connect-src',blockedURI:config.relay.url,lineNumber:1});
 f.listeners.unhandledrejection({reason:{name:'PRIVATE',message:'PRIVATE'}});
 await d.flush();assert.equal(f.calls.length,1);assert(f.calls[0].url.endsWith('/diagnostic'));
 assert.equal(f.calls[0].options.headers['Content-Type'],'text/plain;charset=UTF-8');
 assert.equal(JSON.parse(f.calls[0].options.body).token,config.token);assert(!('event' in JSON.parse(f.calls[0].options.body)));
 assert(!JSON.stringify(d.snapshot()).includes('PRIVATE'));assert(!f.logs.join('').includes('PRIVATE'));
 assert(d.snapshot().events.some(e=>e.event==='csp-violation'&&e.resource==='loopback-player'));
});
test('TV-only/preview never starts diagnostics networking; malformed routes are not widened',async()=>{
 for(const cfg of [null,{...config,enabled:false},{...config,relay:{kind:'http-loopback-v1',url:'http://evil.test:37679/jsaux/v1/player'}}]){
  const f=fixture();f.win.DAS_PLAYER_DEBUG.configure(cfg);await f.win.DAS_PLAYER_DEBUG.flush();assert.equal(f.calls.length,0);
 }
});
test('Both network routes can fail while console fallback remains safe and bounded',async()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;f.win.fetch=async()=>{throw Error('PRIVATE_NETWORK_URL');};d.configure(config);
 for(let n=0;n<300;n++)d.record('request-failed',{reason:'http-failed',action:'open',token:'PRIVATE'});
 for(let n=0;n<40;n++)await d.flush();
 assert(d.snapshot().events.length<=32);assert.equal(d.snapshot().events[0].event,'boot');assert(f.logs.length<=192);assert(!f.logs.join('').includes('PRIVATE'));
 assert(f.logs.some(x=>x.includes('diagnostic-failed')));
});
test('First frame and coordinated start survive a long wait full of heartbeat traces',()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;d.configure(config);
 for(let n=0;n<30;n++)d.record('request',{action:'heartbeat'});
 d.record('first-frame-held',{reason:'matrix-start'});d.record('tv-start',{reason:'software-coordinated'});
 for(let n=0;n<70;n++)d.record('response',{action:'heartbeat'});
 const events=d.snapshot().events;assert(events.length<=32);
 assert(events.some(e=>e.event==='first-frame-held'&&e.reason==='matrix-start'));
 assert(events.some(e=>e.event==='tv-start'&&e.reason==='software-coordinated'));
});
test('Late exit after 12 minutes survives 10000 control events and rolling flush windows',async()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;d.configure(config);
 d.record('first-frame-held');d.record('tv-start',{reason:'software-coordinated'});
 for(let n=0;n<10000;n++){
  f.advance(72);d.record('request',{action:'heartbeat',sequence:n});d.record('response',{action:'heartbeat',sequence:n,flags:{accepted:true}});
  if(n%100===0){d.record('scene-visible',{scene:n%24,slot:n});await d.flush();}
 }
 const before=f.calls.length;
 d.record('broker-refused',{reason:'STEAM_INACTIVE'});d.record('stop',{reason:'broker-refused'});await d.flush();
 const last=JSON.parse(f.calls.at(-1).options.body).report;
 assert(f.calls.length>32);assert(f.calls.length>before);
 assert(last.events.some(e=>e.event==='stop'&&e.ms===720000));
 assert(last.events.some(e=>e.event==='broker-refused'&&e.reason==='STEAM_INACTIVE'));
 assert(last.events.some(e=>e.event==='tv-start'));assert(last.events.length<=32);assert(JSON.stringify(last).length<14000);
});
test('Terminal event during an in-flight flush queues a fresh snapshot, without simultaneous POSTs',async()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;let finish;
 d.configure(config);f.win.fetch=(url,options)=>{f.calls.push({url,options});return new Promise(resolve=>finish=resolve);};
 const pending=d.flush();f.advance(130000);f.listeners.pagehide({persisted:false});
 assert.equal(f.calls.length,1);finish({ok:true});await pending;
 f.win.fetch=async(url,options)=>{f.calls.push({url,options});return {ok:true};};await d.flush();
 assert(JSON.parse(f.calls.at(-1).options.body).report.events.some(e=>e.event==='pagehide'&&e.ms===130000));
});
test('Terminal delivery has reserved capacity after the ordinary rolling quota',async()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;d.configure(config);
 for(let n=0;n<20;n++)await d.flush();assert.equal(f.calls.length,12);
 f.advance(130);d.record('stop',{reason:'destroyed'});await d.flush();assert.equal(f.calls.length,13);
 assert(JSON.parse(f.calls.at(-1).options.body).report.events.some(e=>e.event==='stop'));
 f.advance(60000);await d.flush();assert.equal(f.calls.length,14);
});
test('Late hide, freeze, unload, decoder error and input categories remain distinguishable and private',async()=>{
 for(const event of ['visibilitychange','freeze','beforeunload','error','keydown','pointerdown']){
  const f=fixture(),d=f.win.DAS_PLAYER_DEBUG;d.configure(config);f.advance(240000);f.win.document.hidden=true;
  f.listeners[event]({target:f.win,error:{name:'TypeError',message:'PRIVATE'},key:'PRIVATE',clientX:999,filename:'PRIVATE',lineno:2,colno:4});
  await d.flush();const report=d.snapshot();
  assert(report.events.some(e=>e.ms===240000));assert(!JSON.stringify(report).includes('PRIVATE'));
  if(event==='freeze')assert(report.events.some(e=>e.event==='freeze'&&e.reason==='frozen'));
  if(event==='visibilitychange')assert(report.events.some(e=>e.event==='visibility'&&e.reason==='visibility-hidden'));
  if(event==='beforeunload')assert(report.events.some(e=>e.event==='beforeunload'&&e.reason==='unloading'));
 }
});
test('Warning-level flush failures have valid sequence metadata and never self-schedule retries',async()=>{
 const f=fixture(),d=f.win.DAS_PLAYER_DEBUG,warnings=[];
 f.win.console.warn=x=>warnings.push(x);f.win.fetch=async()=>({ok:false,status:403});d.configure(config);
 const pending=f.timers.size;await d.flush();
 const failures=warnings.filter(x=>x.includes('diagnostic-failed')).map(x=>JSON.parse(x.slice('[DAS-JSAUX-DEBUG] '.length)));
 assert.equal(failures.length,1);assert(Number.isInteger(failures[0].seq));assert(Number.isInteger(failures[0].ms));
 assert.equal(failures[0].status,403);assert(f.timers.size<=pending);
 assert(d.snapshot().events.some(e=>e.event==='diagnostic-failed'));assert(!warnings.join('').includes(config.token));
});
