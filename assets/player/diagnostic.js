/* Runs before catalog/player. Fixed metadata only, no media/URL/token logging. */
(function (win) {
  'use strict';
  var doc=win.document;if(!doc)return;
  var events=[],seq=0,dirty=0,attempts=0,timer=null,busy=false,configured=false,endpoint=null,token=null,build='unknown';
  var began=Date.now(),run='',windowAt=began,windowAttempts=0,lastFlush=-10000,terminalPending=false,stateReader=null,samples=new Map();
  try{var bytes=new Uint8Array(8);win.crypto.getRandomValues(bytes);run=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');}catch{run=Math.floor(Math.random()*2**52).toString(16).padStart(16,'0');}
  var names=new Set(('boot configured dom-ready window-load script-loaded script-error runtime-start catalog-loaded catalog-missing catalog-filtered presentation-check lifecycle-check lifecycle-disabled transport-selected request response request-failed request-timeout open-result clock-result media-ready gate-result tv-start stop visibility pagehide paused media-error js-error js-rejection csp-violation diagnostic-send diagnostic-result diagnostic-failed').split(' '));
  var reasons=new Set(('none preview config-disabled config-missing mode-invalid collection-invalid token-invalid origin-refused relay-invalid fetch-missing transport-unavailable presentation-invalid http-failed timeout rejected accepted tv-only independent software-coordinated clock-unavailable deadline-expired hidden player-ended unknown bootstrap config catalog runtime stylesheet media loopback-player loopback-diagnostic other inline eval script-src script-src-elem connect-src img-src media-src default-src style-src Error TypeError ReferenceError RangeError SyntaxError DOMException AbortError SecurityError NotAllowedError steam-host steam-subdomain screensaver-host http-host file other-origin').split(' '));
  var flagNames=new Set(('secure top hidden installed fetch native config_enabled token_valid collection_valid relay_valid preview presentation_valid version_match duration_match orientation_match transition_match order_match count_match catalog_match build_match accepted gate_accepted candidate mapping_valid online origin_valid path_expected port_default has_parent').split(' '));
  function resource(value){
    try{
      if(value==='inline'||value==='eval')return value;
      var u=new URL(value,win.location.href),leaf=u.pathname.split('/').pop();
      if(u.hostname==='127.0.0.1')return u.pathname==='/jsaux/v1/player'?'loopback-player':u.pathname==='/jsaux/v1/diagnostic'?'loopback-diagnostic':'other';
      return ({'diagnostic.js':'bootstrap','diagnostic-config.js':'config','catalog.js':'catalog','player.js':'runtime','player.css':'stylesheet'})[leaf]||'other';
    }catch{return 'other';}
  }
  names.add('first-frame-held');reasons.add('matrix-start');
  names.add('gca-handoff');
  names.add('alignment-reference');flagNames.add('reference_valid');flagNames.add('calibrated');
  'scene-attempt scene-visible scene-timeout media-waiting media-stalled media-ended player-state lifecycle-exit input-observed freeze beforeunload broker-refused'.split(' ').forEach(x=>names.add(x));
  'visibility-hidden page-hidden frozen unloading destroyed catalog-replaced manual-pause coordinated-ended broker-refused keydown pointerdown gamepad-connected gamepad-disconnected STEAM_INACTIVE STEAM_STATE_STALE LEASE_EXPIRED SESSION_UNKNOWN OPERATION_UNKNOWN PRIORITY_ACTIVE DISPLAY_DISABLED SYSTEM_SUSPENDED FLASH_PROTECTED INTERNAL_ERROR'.split(' ').forEach(x=>reasons.add(x));
  'playing loading coordinated video paused connected persisted focused'.split(' ').forEach(x=>flagNames.add(x));
  var numeric=['status','count','expected','actual','line','column','sequence','scene','slot','age_ms','media_ms','ready_state','network_state','media_error','gap_ms'];
  var critical=new Set('stop pagehide visibility freeze beforeunload lifecycle-exit broker-refused js-error js-rejection media-error scene-timeout'.split(' '));
  function milestone(e){return critical.has(e.event)||['first-frame-held','gate-result','alignment-reference','tv-start'].includes(e.event);}
  function compact(values){
    if(values.length<=32)return values.slice();
    const milestones=values.filter(milestone).slice(-12);
    const selected=new Set(values.slice(0,8).concat(milestones,values.slice(-12)));
    for(const event of values){if(selected.size>=32)break;selected.add(event);}
    return [...selected].sort((a,b)=>a.seq-b.seq);
  }
  function snapshot(){return {schema:'das-player-debug-v1',run:run,build:build,began_at_ms:began,sent_at_ms:Date.now(),events:compact(events)};}
  function retain(e){
    events.push(e);
    if(events.length>64){
      const drop=events.findIndex((value,index)=>index>=8&&index<events.length-24&&!milestone(value));
      events.splice(drop<0?8:drop,1);
    }
  }
  function write(e){try{(win.console.warn||win.console.info).call(win.console,'[DAS-JSAUX-DEBUG] '+JSON.stringify({run:run,build:build,...e}));}catch{}}
  function record(event,data){
    if(!names.has(event)||seq>=2147483646)return;
    // Keep observing for hours, not just the first 160 messages. Healthy control
    // traffic is sampled; failures, scene changes and terminal events are not.
    var sample=event+':'+(['open','clock','ready','started','heartbeat','stop'].includes(data?.action)?data.action:'');
    if(data?.action==='heartbeat'&&['request','response'].includes(event)){
      if(Date.now()-(samples.get(sample)??-Infinity)<15000)return;samples.set(sample,Date.now());
    }
    if(['request-failed','media-waiting','media-stalled','js-error','js-rejection','visibility','stop'].includes(event)){
      if(Date.now()-(samples.get(sample)??-Infinity)<250)return;samples.set(sample,Date.now());
    }
    var e={event:event,seq:++seq,ms:Math.max(0,Math.min(2147483647,Date.now()-began))};data=data||{};
    for(var key of ['reason','resource'])if(reasons.has(data[key]))e[key]=data[key];
    if(['open','clock','ready','started','heartbeat','stop'].includes(data.action))e.action=data.action;
    for(var key of numeric)if(Number.isInteger(data[key])&&data[key]>=0&&data[key]<=2147483647)e[key]=data[key];
    if(data.flags){e.flags={};for(var key of Object.keys(data.flags))if(flagNames.has(key)&&typeof data.flags[key]==='boolean')e.flags[key]=data.flags[key];}
    retain(e);dirty++;
    // This remains useful when ALL browser->backend routes are blocked. Never
    // stringify an exception, request, config, location or catalog here.
    write(e);
    if(critical.has(event)){terminalPending=true;if(timer){win.clearTimeout(timer);timer=null;}}
    if(configured&&endpoint&&!timer&&!busy)timer=win.setTimeout(flush,terminalPending?0:Math.max(350,5000-(Date.now()-lastFlush)));
  }
  async function flush(){
    if(timer)win.clearTimeout(timer);timer=null;if(!endpoint||busy||!win.fetch)return;
    if(Date.now()-windowAt>=60000){windowAt=Date.now();windowAttempts=0;}
    // Reserve terminal delivery even if ordinary traffic hit its rolling quota.
    if(windowAttempts>=12&&(!terminalPending||windowAttempts>=16))return;
    terminalPending=false;
    busy=true;attempts++;windowAttempts++;lastFlush=Date.now();var last=dirty,controller=typeof win.AbortController==='function'?new win.AbortController():null;
    var timeout=win.setTimeout(()=>controller?.abort(),1800);
    try{
      // A simple text/plain POST diagnoses CORS preflight failures separately
      // from the authenticated JSON control channel. It cannot request USB.
      var body=JSON.stringify({token:token,report:snapshot()});
      var response=await win.fetch(endpoint,{method:'POST',mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',
        headers:{'Content-Type':'text/plain;charset=UTF-8'},body:body,signal:controller?.signal,keepalive:true});
      // Do not record/flush success recursively. The server owns receipt proof.
      if(!response.ok)consoleFailure(response.status);
    }catch{consoleFailure(0);}finally{
      win.clearTimeout(timeout);busy=false;
      if(dirty>last&&!timer)timer=win.setTimeout(flush,terminalPending?0:5000);
    }
  }
  function consoleFailure(status){
    if(seq>=2147483646)return;
    var e={event:'diagnostic-failed',seq:++seq,ms:Math.max(0,Math.min(2147483647,Date.now()-began)),status:status,reason:'http-failed'};
    retain(e);write(e); // Do not dirty/flush recursively after a failed flush.
  }
  win.DAS_PLAYER_DEBUG={record:record,snapshot:snapshot,resource:resource,flush:flush,setStateReader:function(read){stateReader=typeof read==='function'?read:null;},configure:function(config){
    if(configured)return;configured=true;
    if(config&&/^[a-f0-9]{12}$/.test(config.build))build=config.build;
    try{
      var u=new URL(config?.relay?.url);
      if(config?.enabled===true&&config.relay.kind==='http-loopback-v1'&&u.protocol==='http:'&&u.hostname==='127.0.0.1'&&u.port&&Number(u.port)<=65535&&u.pathname==='/jsaux/v1/player'&&!u.username&&!u.password&&!u.search&&!u.hash&&/^[A-Za-z0-9_-]{1,80}$/.test(config.token)){
        endpoint=u.origin+'/jsaux/v1/diagnostic';token=config.token;
      }
    }catch{}
    record('configured',{flags:{config_enabled:!!endpoint,fetch:typeof win.fetch==='function',secure:win.isSecureContext===true}});
  }};
  win.addEventListener('error',function(e){
    if(e.target&&e.target!==win){record('script-error',{resource:resource(e.target.src||e.target.href)});return;}
    record('js-error',{reason:reasons.has(e.error?.name)?e.error.name:'unknown',resource:resource(e.filename),line:e.lineno,column:e.colno});
  },true);
  win.addEventListener('unhandledrejection',e=>record('js-rejection',{reason:reasons.has(e.reason?.name)?e.reason.name:'unknown'}));
  var cspSeen=new Set();
  doc.addEventListener('securitypolicyviolation',e=>{
    var reason=reasons.has(e.effectiveDirective)?e.effectiveDirective:'unknown',kind=resource(e.blockedURI),key=reason+':'+kind;
    if(cspSeen.has(key))return;cspSeen.add(key);
    record('csp-violation',{reason:reason,resource:kind,line:e.lineNumber,column:e.columnNumber});
  });
  doc.addEventListener('DOMContentLoaded',()=>record('dom-ready'));
  win.addEventListener('load',()=>record('window-load'));
  doc.addEventListener('load',e=>{if(e.target?.tagName==='SCRIPT')record('script-loaded',{resource:resource(e.target.src)});},true);
  function state(){try{if(stateReader)record('player-state',stateReader());}catch{}}
  function exit(event,reason,e){state();record(event,{reason:reason,flags:{hidden:doc.hidden===true,persisted:e?.persisted===true}});void flush();}
  doc.addEventListener('visibilitychange',()=>{state();record('visibility',{reason:doc.hidden?'visibility-hidden':'none',flags:{hidden:doc.hidden===true}});if(doc.hidden)void flush();});
  win.addEventListener('pagehide',e=>exit('pagehide','page-hidden',e));
  win.addEventListener('beforeunload',e=>exit('beforeunload','unloading',e));
  doc.addEventListener('freeze',e=>exit('freeze','frozen',e));
  // Observe categories only: no key, text, coordinates or gamepad identity.
  for(const event of ['keydown','pointerdown','gamepadconnected','gamepaddisconnected'])win.addEventListener(event,()=>{
    const at=Date.now();if(at-(samples.get(event)??-Infinity)<2000)return;samples.set(event,at);
    record('input-observed',{reason:({'gamepadconnected':'gamepad-connected','gamepaddisconnected':'gamepad-disconnected'})[event]||event});
  },{capture:true,passive:true});
  var tickAt=Date.now();
  function tick(){const now=Date.now();record('player-state',{gap_ms:Math.max(0,Math.min(2147483647,now-tickAt)),flags:{hidden:doc.hidden===true,online:win.navigator?.onLine===true,focused:doc.hasFocus?.()===true}});tickAt=now;state();win.setTimeout(tick,15000);}
  win.setTimeout(tick,15000);
  var origin='other-origin';try{var u=new URL(win.location.href);origin=u.protocol==='file:'?'file':u.protocol==='http:'?'http-host':u.hostname==='steamloopback.host'?'steam-host':u.hostname.endsWith('.steamloopback.host')?'steam-subdomain':
    ['uioverride-decky-animated-screensaver.steamscreensavers.host','decky-animated-screensaver.steamscreensavers.host'].includes(u.hostname)?'screensaver-host':'other-origin';}catch{}
  record('boot',{reason:origin,flags:{top:win.parent===win,hidden:doc.hidden===true,secure:win.isSecureContext===true,online:win.navigator?.onLine===true}});
})(window);
