/* Offline player. Optional installed iframe relay; no sockets or broker secrets. */
(function (global) {
  'use strict';
  function debug(win,event,data){try{win.DAS_PLAYER_DEBUG?.record(event,data);}catch{}}
  debug(global,'runtime-start',{flags:{build_match:global.DAS_PLAYER_BOOT?.revision===19}});
  const defaults = {
    sceneDuration: 24,
    shuffle: true,
    transition: 'crossfade',
    showLogos: true,
    showCover: true,
    coverPosition: 'bottom-right',
    framing: 'original',
    staticFallback: false,
    reducedMotion: false,
    language: 'en'
  };
  function localMedia(value) {
    if (typeof value !== 'string' || value.length > 240 || /[\\\u0000-\u001f?#]/.test(value))
      return false;
    return (/^\/[A-Za-z0-9_-]{32,100}\/[a-f0-9]{24}$/.test(value) ||
      /^(?:(?:\/?media\/)|(?:app:\/\/screensaver\/media\/))[a-zA-Z0-9][a-zA-Z0-9._-]{0,180}$/.test(
        value
      ) && !value.includes('..')
    );
  }
  function settings(input = {}) {
    return {
      sceneDuration: Math.max(8, Math.min(180, Number(input.sceneDuration) || 24)),
      shuffle: input.shuffle !== false,
      transition: ['crossfade', 'fade-black'].includes(input.transition)
        ? input.transition
        : 'crossfade',
      showLogos: input.showLogos !== false,
      nameDisplay: ['title', 'logo', 'both', 'hidden'].includes(input.nameDisplay)
        ? input.nameDisplay
        : input.showLogos === false
          ? 'hidden'
          : 'logo',
      logoPosition: [
        'bottom-left',
        'bottom-right',
        'top-left',
        'top-right'
      ].includes(input.logoPosition)
        ? input.logoPosition
        : 'bottom-left',
      showArtworkCredit: input.showArtworkCredit === true,
      showCoverCredit: input.showCoverCredit === true,
      showLogoCredit: input.showLogoCredit === true,
      showCover: input.showCover !== false,
      coverPosition: ['bottom-left', 'bottom-right', 'top-right', 'top-left'].includes(
        input.coverPosition
      )
        ? input.coverPosition
        : 'bottom-right',
      framing: ['original', '16:9', '16:10'].includes(input.framing) ? input.framing : 'original',
      staticFallback: input.staticFallback === true,
      reducedMotion: input.reducedMotion === true,
      language: input.language === 'fr' ? 'fr' : 'en'
    };
  }
  function catalogGames(catalog, options) {
    return (Array.isArray(catalog?.games) ? catalog.games : [])
      .filter(
        (g) =>
          g &&
          g.included !== false &&
          g.status === 'ready' &&
          g.media &&
          localMedia(g.media.file) &&
          localMedia(g.media.thumbnail) &&
          (g.media.animated || options.staticFallback || g.explicitStill === true)
      )
      .slice(0, 10000);
  }
  function shuffle(items, random = Math.random) {
    const result = items.slice();
    for (let i = result.length - 1; i > 0; i--) {
      const j = Math.floor(random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    return result;
  }
  function framing(game, options) {
    const mode = ['original', '16:9', '16:10'].includes(game.crop?.mode)
      ? game.crop.mode
      : options.framing;
    const coordinate = (v) => (Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : 50);
    return { mode, x: coordinate(game.crop?.x), y: coordinate(game.crop?.y) };
  }
  function frameBox(width, height, mode) {
    if (mode === 'original') return { width, height };
    const ratio = mode === '16:10' ? 16 / 10 : 16 / 9;
    const fittedWidth = Math.min(width, height * ratio);
    return { width: fittedWidth, height: fittedWidth / ratio };
  }
  // Absolute slots do not accumulate decoder/transition delays. Pure helper is
  // exercised with slow media and 30+ transitions in the software timing tests.
  function presentationSlot(epoch,now,duration){
    return Math.max(0,Math.floor((now-epoch)/duration));
  }
  function presentationMatches(value,games,options){
    const m=value?.presentation;
    const key=g=>g.steamAppId||(/^steam:\d+$/.test(g.id)?Number(g.id.slice(6)):/^sgdb:\d+$/.test(g.id)?-Number(g.id.slice(5)):null);
    return m?.version===2&&m.page_ms===options.sceneDuration*1000&&m.orientation===0&&m.transition_included===true&&
      Array.isArray(m.order)&&m.order.length===games.length&&m.order.every((id,n)=>id===key(games[n]));
  }
  // The host CLOCK_MONOTONIC and browser performance.now origins differ. Three
  // bounded round trips establish a conservative interval, never a wall clock.
  function clockMapping(samples, now) {
    if (!Array.isArray(samples) || samples.length !== 3) return null;
    let lower = -Infinity, upper = Infinity;
    for (const s of samples) {
      if (![s.sent, s.received, s.host].every(Number.isFinite) || s.received < s.sent || now < s.received || now - s.sent > 30000) return null;
      lower = Math.max(lower, s.host - s.received);
      upper = Math.min(upper, s.host - s.sent);
    }
    return upper >= lower && upper - lower <= 50 ? { lower, uncertainty: Math.ceil(upper - lower), sampledAt: now } : null;
  }
  function alignmentEpoch(timing,mapping,browserNow,offset,deadline){
    if(!timing||timing.basis!=='broker-confirmation-event'||!mapping||
      !Number.isSafeInteger(timing.reference_mono_ms)||!Number.isSafeInteger(timing.uncertainty_ms)||
      timing.uncertainty_ms<0||timing.uncertainty_ms>26||!Number.isInteger(offset)||
      Math.abs(offset)>10000||offset%100!==0)return null;
    const middle=mapping.lower+mapping.uncertainty/2,age=browserNow+middle-timing.reference_mono_ms;
    if(age < -mapping.uncertainty-timing.uncertainty_ms-1||age>15000)return null;
    const epoch=timing.reference_mono_ms-middle+offset;
    return epoch+mapping.lower<deadline-1?epoch:null;
  }
  function playerRelayURL(value) {
    try {
      if(value?.kind!=='http-loopback-v1'||typeof value.url!=='string')return null;
      const u=new URL(value.url);
      return u.protocol==='http:'&&u.hostname==='127.0.0.1'&&/^[0-9]+$/.test(u.port)&&Number(u.port)>0&&Number(u.port)<=65535
        &&!u.username&&!u.password&&!u.search&&!u.hash&&u.pathname==='/jsaux/v1/player'?u.href:null;
    }catch{return null;}
  }
  const screenHosts=['uioverride-decky-animated-screensaver.steamscreensavers.host','decky-animated-screensaver.steamscreensavers.host'];
  function steamPlayerOrigin(origin){
    try{const u=new URL(origin);return origin==='https://'+u.hostname&&!u.port&&
      (screenHosts.includes(u.hostname)||/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*steamloopback\.host$/.test(u.hostname));}catch{return false;}
  }
  function createJsauxLifecycle(win, document, value) {
    const config=value?.jsaux, token=value?.bridge_token;
    // Fixed in the installed export, never extended by a delayed reply.
    const syncWait=config?.sync_wait_ms===15000?15000:2500;
    const validOrigin=steamPlayerOrigin;
    let origin=null;
    try{const candidate=new URL(document.referrer).origin;if(validOrigin(candidate))origin=candidate;}catch{}
    if(!origin&&win.parent!==win)try{if(validOrigin(win.parent.location.origin))origin=win.parent.location.origin;}catch{}
    const storage=win.SteamClient?.Storage;
    let installed=false,originValid=false,pathExpected=false,portDefault=false;
    try{const u=new URL(win.location.href);originValid=validOrigin(u.origin);portDefault=!u.port;
      pathExpected=screenHosts.includes(u.hostname)||u.hostname==='decky-animated-screensaver.steamloopback.host'||/(?:^|\/)decky-animated-screensaver\/(?:index\.html)?$/.test(u.pathname);
      installed=originValid&&pathExpected;}catch{}
    const native=installed&&typeof storage?.SetString==='function'&&typeof storage?.GetString==='function';
    const relayURL=playerRelayURL(config?.relay),http=installed&&relayURL&&typeof win.fetch==='function';
    // One transport per export. Never replay a timed-out mutation through another
    // channel; HTTP exports do not touch Steam's VDF-backed Storage at all.
    const legacy=!config?.relay;
    const enabled=!value?.previewNonce&&config?.enabled===true&&['sync','async'].includes(config.mode)&&/^[a-f0-9]{64}$/.test(config.collection_id||'')&&/^[A-Za-z0-9_-]{1,80}$/.test(token||'')&&(http||legacy&&(native||win.parent!==win&&origin));
    const flags={preview:!!value?.previewNonce,config_enabled:config?.enabled===true,installed,
      fetch:typeof win.fetch==='function',native:!!native,relay_valid:!!relayURL,
      collection_valid:/^[a-f0-9]{64}$/.test(config?.collection_id||''),token_valid:/^[A-Za-z0-9_-]{1,80}$/.test(token||''),hidden:document.hidden===true,
      origin_valid:originValid,path_expected:pathExpected,port_default:portDefault,has_parent:win.parent!==win};
    debug(win,'lifecycle-check',{flags});
    if(!enabled){
      const reason=flags.preview?'preview':!config?'config-missing':!flags.config_enabled?'config-disabled':!['sync','async'].includes(config.mode)?'mode-invalid':
        !flags.collection_valid?'collection-invalid':!flags.token_valid?'token-invalid':!installed&&config.relay?'origin-refused':config.relay&&!relayURL?'relay-invalid':
        config.relay&&!flags.fetch?'fetch-missing':'transport-unavailable';
      debug(win,'lifecycle-disabled',{reason,flags});return {ready:show=>show(),stop:()=>{}};
    }
    debug(win,'transport-selected',{flags:{fetch:!!http,native:!!native}});
    const now=()=>win.performance.now(), session=win.crypto?.randomUUID?.()||`das_${Math.random().toString(36).slice(2)}_${Math.floor(now())}`;
    let sequence=0,ended=false,started=false,accepted=false,mapping=null,readyAt=null,deadline=null,showScene=null,watchdog=null,pollTimer=null,busy=false;
    let calibrationMs=0,alignmentTimer=null,pendingAlignment=false,leaseDeadline=0,heartbeatFailures=0,handedOff=false;
    function rememberLease(result,sent){
      const ttl=result?.lease_remaining_ms;
      if(Number.isInteger(ttl)&&ttl>=0&&ttl<=8000)leaseDeadline=sent+ttl;
      else if(result?.accepted===true)leaseDeadline=sent+4000; // Conservative older relay compatibility.
    }
    const requests=new Map();
    let storageTimer=null,storageReading=false;
    const transport={kind:http?'http-loopback-v1':native?'native-storage':'iframe',requests:0,replies:0,errors:0,last_error:''};
    win.DAS_JSAUX_TRANSPORT=transport;
    function transportError(code){transport.errors=Math.min(999999,transport.errors+1);transport.last_error=code;}
    function accept(data){
      if(data?.session_id!==session)return;
      const pending=requests.get(data.sequence);if(!pending)return;
      requests.delete(data.sequence);win.clearTimeout(pending.timeout);pending.resolve(data.result);
    }
    async function readStorage(){
      if(ended||storageReading||!requests.size)return;
      storageReading=true;
      try{const raw=await storage.GetString('decky-animated-screensaver.jsaux.reply.v1');if(typeof raw==='string'&&raw.length<=2048)accept(JSON.parse(raw));}catch{}
      finally{storageReading=false;if(!ended&&requests.size)storageTimer=win.setTimeout(readStorage,10);}
    }
    function request(event,extra={}){
      const n=++sequence;
      const traced=event!=='heartbeat'||!started;
      if(traced)debug(win,'request',{action:event,sequence:n});
      return new Promise(resolve=>{
        const controller=http&&typeof win.AbortController==='function'?new win.AbortController():null;
        const timeout=win.setTimeout(()=>{requests.delete(n);controller?.abort();transportError('REQUEST_TIMEOUT');debug(win,'request-timeout',{action:event,sequence:n,reason:'timeout'});resolve(null);},http&&event==='open'?3000:2000);
        requests.set(n,{resolve,timeout,controller,event});
        const payload={event,token,collection_id:config.collection_id,session_id:session,mode:config.mode,sequence:n,...extra};
        transport.requests=Math.min(999999,transport.requests+1);
        try{
          if(http){
            void win.fetch(relayURL,{method:'POST',mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',
              headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller?.signal,keepalive:event==='stop'}).then(async response=>{
                if(traced||!response.ok)debug(win,'response',{action:event,sequence:n,status:response.status});
                if(!response.ok)throw Error('HTTP_STATUS');
                let text='';
                if(response.body?.getReader&&typeof win.TextDecoder==='function'){
                  const reader=response.body.getReader(),decoder=new win.TextDecoder();let bytes=0;
                  try{for(;;){const part=await reader.read();if(part.done)break;bytes+=part.value.length;if(bytes>2048)throw Error('REPLY_TOO_LARGE');text+=decoder.decode(part.value,{stream:true});}text+=decoder.decode();}
                  finally{try{await reader.cancel();}catch{}}
                }else{text=await response.text();if(text.length>2048)throw Error('REPLY_TOO_LARGE');}
                const result=JSON.parse(text);transport.replies=Math.min(999999,transport.replies+1);
                if(traced)debug(win,'response',{action:event,sequence:n,reason:result.reason,flags:{accepted:result.accepted===true,gate_accepted:result.gate_accepted===true,candidate:!!result.candidate}});
                accept({session_id:session,sequence:n,result});
              }).catch(()=>{transportError('HTTP_REQUEST_FAILED');debug(win,'request-failed',{action:event,sequence:n,reason:'http-failed'});const pending=requests.get(n);if(pending){requests.delete(n);win.clearTimeout(pending.timeout);pending.resolve(null);}});
          }
          else if(native){Promise.resolve(storage.SetString('decky-animated-screensaver.jsaux.request.v1',JSON.stringify({at:Date.now(),payload}))).catch(()=>{});win.clearTimeout(storageTimer);storageTimer=win.setTimeout(readStorage,0);}
          else win.parent.postMessage({type:'das-jsaux-player-v1',payload},origin);
        }catch{debug(win,'request-failed',{action:event,sequence:n,reason:'unknown'});win.clearTimeout(timeout);requests.delete(n);resolve(null);}
      });
    }
    function reply(event){
      if(event.source!==win.parent||event.origin!==origin||event.data?.type!=='das-jsaux-reply-v1'||event.data.session_id!==session)return;
      if(!http&&!native)accept(event.data);
    }
    win.addEventListener('message',reply);
    const visibility=()=>{if(document.hidden){debug(win,'lifecycle-exit',{reason:'visibility-hidden'});mapping=null;start('tv-only');stop('visibility-hidden');}};
    const unloading=()=>stop('unloading'),freezing=()=>stop('frozen');
    document.addEventListener?.('visibilitychange',visibility);
    win.addEventListener('beforeunload',unloading);
    document.addEventListener?.('freeze',freezing);
    function poll(delay){
      win.clearTimeout(pollTimer);
      if(ended||handedOff||!accepted)return;
      pollTimer=win.setTimeout(async()=>{
        if(ended||busy)return;busy=true;
        if(leaseDeadline&&now()>=leaseDeadline){busy=false;if(!started)start('tv-only',null,null,'lease-expired');stop('lease-expired');return;}
        const sent=now(),result=await request('heartbeat');busy=false;
        if(ended)return;
        if(result===null||result?.retryable===true){
          heartbeatFailures++;
          debug(win,'heartbeat-degraded',{reason:result?.reason||'transport-unavailable',count:Math.min(999,heartbeatFailures)});
          // Unknown delivery never refreshes the last confirmed lease. Retry
          // only heartbeat; acquire/ready and GIF writes are never replayed.
          if(leaseDeadline&&now()<leaseDeadline){poll(Math.min(250,leaseDeadline-now()));return;}
          if(!started)start('tv-only',null,null,'transport-lost');stop('transport-lost');return;
        }
        if(result?.accepted!==true){debug(win,'broker-refused',{reason:result?.reason||'rejected'});if(!started)start('tv-only',null,null,'broker-refused');stop('broker-refused');return;}
        if(config.controller==='GabeCubeAura'&&result?.gca_owned===true){handedOff=true;debug(win,'gca-handoff',{reason:'accepted'});return;}
        rememberLease(result,sent);
        if(heartbeatFailures)debug(win,'heartbeat-recovered',{count:Math.min(999,heartbeatFailures)});
        heartbeatFailures=0;
        const c=result?.candidate;
        if(!started&&!pendingAlignment&&c&&c.phase_basis==='gif-end-ack-assumption'&&c.optical_alignment==='unknown'&&c.deadline_mono_ms===deadline&&typeof c.candidate_id==='string'&&now()<readyAt+syncWait&&mapping&&Math.floor(now()+mapping.lower)<deadline){
          const epoch=alignmentEpoch(result.timing,mapping,now(),calibrationMs,deadline);
          debug(win,'alignment-reference',{actual:Math.abs(calibrationMs),flags:{reference_valid:epoch!==null,calibrated:calibrationMs!==0}});
          if(epoch!==null){
            pendingAlignment=true;
            const begin=()=>{if(ended||started)return;
              if(now()>=readyAt+syncWait||Math.floor(now()+mapping.lower)>=deadline){start('tv-only');return;}
              start('software-coordinated',c.candidate_id,epoch);};
            // started_mono_ms uses the conservative lower clock bound. Wait
            // through the reference uncertainty before reporting an actual start,
            // but keep the calendar on its original (possibly past) epoch.
            const startAt=Math.max(epoch,result.timing.reference_mono_ms+result.timing.uncertainty_ms-mapping.lower+1);
            if(startAt>now())alignmentTimer=win.setTimeout(begin,startAt-now());else begin();
          }else if(!result.timing&&calibrationMs===0)start('software-coordinated',c.candidate_id);
          // Invalid or uncertain references never manufacture an aligned start.
          // Keep observing until the existing deadline; never extend it.
        }
        poll(started?2000:500);
      },delay);
    }
    function start(outcome,candidate=null,epoch=null,endReason='player-ended'){
      if(started||ended)return;started=true;win.clearTimeout(watchdog);win.clearTimeout(alignmentTimer);
      debug(win,'tv-start',{reason:outcome,flags:{candidate:!!candidate}});
      const show=showScene;showScene=null;if(show)show(epoch===null?null:{epoch});
      if(accepted){
        void request('started',{started_mono_ms:config.mode==='sync'&&mapping?Math.floor(now()+mapping.lower):null,outcome,candidate_id:candidate}).then(result=>{
          if(ended)return;
          if(config.controller==='GabeCubeAura'&&result?.accepted===true&&result.gca_owned===true){handedOff=true;win.clearTimeout(pollTimer);debug(win,'gca-handoff',{reason:'accepted'});return;}
          if(outcome!=='tv-only')poll(2000);
        });
        if(outcome==='tv-only')stop(endReason);
      }
    }
    async function open(){
      const sent=now(),result=await request('open');
      if(ended)return;
      accepted=result?.accepted===true&&!result?.tv_only;
      if(accepted)rememberLease(result,sent);
      if(Number.isInteger(result?.alignment_ms)&&Math.abs(result.alignment_ms)<=10000&&result.alignment_ms%100===0)calibrationMs=result.alignment_ms;
      debug(win,'open-result',{flags:{accepted}});
      if(started){stop();return;}
      if(!accepted){if(showScene)start('tv-only');stop();return;}
      if(config.mode==='sync'){
        const samples=[];
        for(let i=0;i<3&&!ended;i++){
          // Outward rounding matches the backend's integer millisecond sample.
          // Sub-ms round trips must not produce an empty interval just because
          // CLOCK_MONOTONIC was floored while performance.now retains fractions.
          const sent=Math.floor(now()),sample=await request('clock'),received=Math.ceil(now());
          if(!Number.isSafeInteger(sample?.broker_mono_ms)){mapping=null;break;}
          samples.push({sent,received,host:sample.broker_mono_ms});
        }
        mapping=clockMapping(samples,Math.ceil(now()));
        debug(win,'clock-result',{flags:{mapping_valid:!!mapping},count:samples.length,actual:mapping?.uncertainty});
      }
      if(ended)return;
      if(showScene)void gate();
    }
    async function gate(){
      if(ended||started||readyAt===null||!accepted)return;
      if(config.mode==='sync'&&(!mapping||now()-mapping.sampledAt>30000||document.hidden)){debug(win,'gate-result',{reason:document.hidden?'hidden':'clock-unavailable'});start('tv-only');stop();return;}
      deadline=config.mode==='sync'?Math.floor(readyAt+mapping.lower)+syncWait:null;
      if(config.mode==='sync'&&(now()>=readyAt+syncWait||Math.floor(now()+mapping.lower)>=deadline)){debug(win,'gate-result',{reason:'deadline-expired'});start('tv-only');return;}
      const result=await request('ready',{ready_mono_ms:config.mode==='sync'?deadline-syncWait:null,deadline_mono_ms:deadline,clock_uncertainty_ms:config.mode==='sync'?mapping.uncertainty:null});
      if(ended||started)return;
      debug(win,'gate-result',{flags:{gate_accepted:result?.gate_accepted===true}});
      if(!result?.gate_accepted){start('tv-only');stop();return;}
      if(config.mode==='async')start('independent');else poll(0);
    }
    function stop(reason='player-ended'){
      if(ended)return;ended=true;win.clearTimeout(watchdog);win.clearTimeout(pollTimer);win.clearTimeout(storageTimer);win.clearTimeout(alignmentTimer);
      debug(win,'stop',{reason});
      const known=['player-ended','visibility-hidden','unloading','frozen','destroyed','manual-pause','catalog-replaced','coordinated-ended','broker-refused','transport-lost','lease-expired'];
      void request('stop',{reason:known.includes(reason)?reason:'player-ended'});
      // Stop is best-effort. GCA independently revokes on Steam inactive/expiry.
      win.removeEventListener('message',reply);
      document.removeEventListener?.('visibilitychange',visibility);
      win.removeEventListener('beforeunload',unloading);
      document.removeEventListener?.('freeze',freezing);
      for(const {resolve,timeout,controller,event}of requests.values()){win.clearTimeout(timeout);if(event!=='stop')controller?.abort();resolve(null);}requests.clear();
      showScene=null;
    }
    void open();
    return {
      // Reveal an already decoded first frame, not a blank stage, while the
      // bounded USB gate holds the presentation clock. Preview remains instant.
      get waitingForMatrix(){return !ended&&!started&&config.mode==='sync';},
      ready(show){
        debug(win,'media-ready',{flags:{hidden:document.hidden===true}});
        if(started||ended){show();return;}
        if(readyAt!==null){show();return;}
        readyAt=now();showScene=show;
        if(config.mode==='async'){showScene=()=>{};show();if(accepted)void gate();return;}
        watchdog=win.setTimeout(()=>start('tv-only'),syncWait);
        if(accepted&&mapping)void gate();
      },
      stop
    };
  }
  const helpers = { localMedia, settings, catalogGames, shuffle, framing, frameBox, clockMapping, alignmentEpoch,createJsauxLifecycle,playerRelayURL,presentationSlot,presentationMatches,steamPlayerOrigin };
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (!global.document) return;
  const doc = global.document,
    stage = doc.getElementById('stage'),
    empty = doc.getElementById('empty');
  let options = settings(),
    catalog = { games: [] },
    games = [],
    order = [],
    position = -1,
    history = [],
    historyPosition = -1,
    current = null,
    retiring = null,
    pending = null,
    timer = null,
    transitionTimer = null,
    loadTimer = null,
    destroyed = false,
    playing = true,
    loading = false,
    generation = 0,
    failures = new Set(),
    hiddenPause = false,
    jsaux = null,
    epoch = null,
    slot = 0,
    preload = null,
    coordinated = false;
  const french = () => options.language === 'fr';
  try{global.DAS_PLAYER_DEBUG?.setStateReader(()=>({scene:Math.max(0,games.indexOf(current?.game)),slot:Math.max(0,slot),count:games.length,
    age_ms:Math.max(0,Math.floor(performance.now()-(current?._shownAt||performance.now()))),
    media_ms:Math.max(0,Math.floor((current?.querySelector('.artwork')?.currentTime||0)*1000)),
    flags:{playing,loading,coordinated,hidden:doc.hidden===true}}));}catch{}
  function notify(status, game) {
    if (global.parent !== global)
      global.parent.postMessage(
        { type: 'screensaver-player', status, gameId: game?.id || null, nonce:catalog.previewNonce },
        '*'
      );
  }
  function emptyState(failed = false) {
    empty.hidden = false;
    empty.querySelector('h1').textContent = failed
      ? french()
        ? 'Ces médias sont indisponibles.'
        : 'These artworks are unavailable.'
      : french()
        ? 'Aucune animation préparée.'
        : 'No prepared animations.';
    empty.querySelector('p').textContent = failed
      ? french()
        ? 'Réparez la bibliothèque depuis le gestionnaire.'
        : 'Repair your library in the Manager, then preview again.'
      : french()
        ? 'Préparez les animations dans le gestionnaire.'
        : 'Prepare animations in the Manager.';
  }
  function release(scene) {
    if (!scene) return;
    for (const media of scene.querySelectorAll('video')) {
      media.pause();
      media.removeAttribute('src');
      media.load();
    }
    for (const image of scene.querySelectorAll('img')) {
      image._sasReleased = true;
      image._sasSuspended = true;
      if (image._sasRestore) image.removeEventListener('load', image._sasRestore);
      image.removeAttribute('src');
    }
    for (const canvas of scene.querySelectorAll('canvas')) canvas.width = canvas.height = 0;
    scene.remove();
  }
  function freezeScene(scene) {
    if (!scene) return;
    scene.classList.add('paused');
    if (!scene.game.media.animated) return;
    for(const art of scene.querySelectorAll('img.artwork,img.ambience,img.caption-cover[data-fallback="true"]')){
    if (art._sasReleased || art.hidden&&!art._sasSuspended) continue;
    // Canvas image sources expose the browser's default animation frame. Freeze that
    // local frame and unload the native animation rather than pretending a timer pauses it.
    if (!art._sasSnapshot) {
      if (!art.complete || !art.naturalWidth) continue;
      const canvas = doc.createElement('canvas');
      canvas.className = art.className+(art.classList.contains('ambience')?' frozen-ambience':art.classList.contains('caption-cover')?' frozen-cover':' frozen-artwork');
      const cap=art.classList.contains('artwork')?Infinity:art.classList.contains('ambience')?960:256;
      const scale=Math.min(1,cap/Math.max(art.naturalWidth,art.naturalHeight));
      canvas.width = Math.max(1,Math.round(art.naturalWidth*scale));
      canvas.height = Math.max(1,Math.round(art.naturalHeight*scale));
      canvas.setAttribute('aria-hidden', 'true');
      try {
        canvas.getContext('2d').drawImage(art, 0, 0,canvas.width,canvas.height);
      } catch {
        canvas.width = canvas.height = 0;
        continue;
      }
      art.insertAdjacentElement('afterend', canvas);
      art._sasSnapshot = canvas;
    }
    if (art._sasRestore) {
      art.removeEventListener('load', art._sasRestore);
      art._sasRestore = null;
    }
    art._sasSuspended = true;
    art._sasResumeSource=art.getAttribute('src')||art._sasResumeSource;
    art.hidden = true;
    art.removeAttribute('src');
    }
  }
  function resumeScene(scene) {
    if (!scene) return;
    scene.classList.remove('paused');
    for(const art of scene.querySelectorAll('img.artwork,img.ambience,img.caption-cover')){
    if (!art._sasSnapshot || !art._sasSuspended || art._sasReleased) continue;
    art._sasSuspended = false;
    const restored = () => {
      art._sasRestore = null;
      if (art._sasReleased) return;
      if (!playing) {
        freezeScene(scene);
        return;
      }
      const canvas = art._sasSnapshot;
      art._sasSnapshot = null;
      art.hidden = art.classList.contains('caption-cover')&&(!options.showCover||art.dataset.failed==='true');
      if (canvas) {
        canvas.width = canvas.height = 0;
        canvas.remove();
      }
    };
    art._sasRestore = restored;
    art.addEventListener('load', restored, { once: true });
    art.src = art._sasResumeSource;
    }
  }
  function clearTimer() {
    clearTimeout(timer);
    timer = null;
  }
  function preloadNext(){
    if(destroyed||!coordinated||games.length<2)return;
    const game=order[(slot+1)%order.length];
    if(preload?.game===game)return;
    if(preload)release(preload.scene);
    const item=sceneFor(game);preload={...item,game,ready:false,failed:false};
    const prepared=preload;
    item.art.addEventListener(item.isVideo?'canplay':'load',()=>{prepared.ready=true;},{once:true});
    item.art.addEventListener('error',()=>{prepared.failed=true;},{once:true});
    item.art.src=game.media.file;if(item.isVideo)item.art.load();
  }
  function degrade(){
    if(!coordinated)return;
    coordinated=false;epoch=null;if(jsaux)jsaux.stop();
    stage.classList.remove('coordinated');
    if(preload){release(preload.scene);preload=null;}
    notify('coordination-ended',current?.game);
  }
  function schedule() {
    clearTimer();
    if (playing && !destroyed && games.length > 1 && !loading){
      if(coordinated&&epoch!==null){
        preloadNext();
        const boundary=epoch+(slot+1)*options.sceneDuration*1000;
        const lead=options.reducedMotion?0:400;
        timer=setTimeout(()=>{
          // A delayed browser timer skips obsolete slots without moving the epoch.
          slot=Math.max(slot+1,presentationSlot(epoch,performance.now()+lead,options.sceneDuration*1000));
          position=slot%order.length;display(order[position]);
        },Math.max(0,boundary-lead-performance.now()));
      }else timer = setTimeout(next, options.sceneDuration * 1000);
    }
  }
  function setPaused(paused, automatic=false) {
    if(!automatic)hiddenPause=false;
    debug(global,'paused',{flags:{hidden:doc.hidden===true},actual:paused?1:0});
    if(paused){degrade();if(jsaux)jsaux.stop();}
    playing = !paused;
    clearTimer();
    if (paused) {
      clearTimeout(transitionTimer);
      transitionTimer = null;
      if (current) current.classList.add('visible');
      if (retiring) {
        release(retiring);
        retiring = null;
      }
    }
    for (const scene of stage.children) {
      if (paused) freezeScene(scene);
      else resumeScene(scene);
    }
    for (const video of stage.querySelectorAll('video')) {
      if (paused) video.pause();
      else video.play().catch(() => {});
    }
    if (!paused) schedule();
    notify(paused ? 'paused' : 'playing', current?.game);
  }
  function newOrder(lastId) {
    order = options.shuffle ? shuffle(games) : games.slice();
    if (order.length > 1 && order[0]?.id === lastId) [order[0], order[1]] = [order[1], order[0]];
    position = -1;
  }
  function placeBranding(scene) {
    const copy = scene.querySelector('.caption-copy'),
      caption = scene.querySelector('.caption'),
      logo = scene.querySelector('.game-logo'),
      title = scene.querySelector('h1'),
      custom = scene.game.branding || {},
      mode = ['title', 'logo', 'both', 'hidden'].includes(custom.mode)
        ? custom.mode
        : options.nameDisplay,
      position = ['bottom-left', 'bottom-right', 'top-left', 'top-right'].includes(
        custom.position
      )
        ? custom.position
        : options.logoPosition;
    scene.dataset.logoPosition = position;
    const available =
      !!logo && logo.dataset.failed !== 'true' && logo.complete && logo.naturalWidth > 0;
    title.hidden = mode === 'hidden' || (mode === 'logo' && available);
    if (logo) {
      logo.hidden = !available || mode === 'hidden' || mode === 'title';
      scene.append(logo);
    }
    const logoCredit = scene.querySelector('.logo-credit');
    if (logoCredit) logoCredit.hidden = !options.showLogoCredit || !logo || logo.hidden;
    const artworkCredit = scene.querySelector('.artwork-credit');
    if (artworkCredit) artworkCredit.hidden = !options.showArtworkCredit;
    scene.classList.toggle('has-logo', !!logo && !logo.hidden);
    if(logo&&!logo.hidden){
      const ratio=logo.naturalWidth/Math.max(1,logo.naturalHeight);
      scene.style.setProperty('--pair-logo-width',Math.min(logo.naturalWidth,global.innerWidth*.36,460,Math.min(global.innerHeight*.12,150)*ratio)+'px');
    }
    // Preserve both independently selected corners. Only a shared corner needs
    // collision handling: cover on the left, logo on the right, with a gap.
    scene.classList.toggle('branding-pair', scene.classList.contains('has-cover') && !!logo && !logo.hidden
      && scene.dataset.coverPosition === position);
    const captionHeight = caption.getBoundingClientRect().height;
    scene.style.setProperty('--caption-height', `${captionHeight}px`);
    scene.style.setProperty(
      '--caption-clearance',
      captionHeight > 0 ? `calc(${captionHeight}px + var(--cover-gap))` : '0px'
    );
  }
  function placeCover(scene) {
    const cover = scene.querySelector('img.caption-cover');
    scene.dataset.coverPosition = ['bottom-left','bottom-right','top-left','top-right'].includes(scene.game.coverPosition)?scene.game.coverPosition:options.coverPosition;
    if (!cover) return;
    const visible=options.showCover && cover.dataset.failed !== 'true';
    cover.hidden = !visible || cover._sasSuspended===true;
    if(cover._sasSnapshot)cover._sasSnapshot.hidden=!visible;
    scene.append(cover);
    scene.classList.toggle('has-cover', visible);
    const credit = scene.querySelector('.cover-credit');
    if (credit)
      credit.hidden = !options.showCoverCredit || !visible || cover.dataset.fallback === 'true';
    placeBranding(scene);
  }
  function placeFrame(scene) {
    const crop = framing(scene.game, options),
      frame = scene.querySelector('.art-frame');
    scene.dataset.framing = crop.mode;
    scene.style.setProperty('--crop-x', `${crop.mode === 'original' ? 50 : crop.x}%`);
    scene.style.setProperty('--crop-y', `${crop.mode === 'original' ? 50 : crop.y}%`);
    const box = frameBox(
      stage.clientWidth || global.innerWidth,
      stage.clientHeight || global.innerHeight,
      crop.mode
    );
    frame.style.width = `${box.width}px`;
    frame.style.height = `${box.height}px`;
  }
  function resizeFrames() {
    for (const scene of stage.children) {
      placeFrame(scene);
      placeBranding(scene);
    }
  }
  function sceneFor(game) {
    const scene = doc.createElement('section');
    scene.className = `scene ${!game.media.animated ? 'static ' : ''}${!game.media.animated && game.stillMotion === 'gentle' ? 'gentle ' : ''}${options.reducedMotion ? 'reduced instant' : ''}`;
    scene.game = game;
    const ambience = doc.createElement('img');
    ambience.className = 'ambience';
    ambience.alt = '';
    ambience.src = game.media.thumbnail;
    scene.append(ambience);
    const isVideo = game.media.format === 'webm',
      art = doc.createElement(isVideo ? 'video' : 'img');
    art.className = 'artwork';
    if (isVideo) {
      art.muted = true;
      art.defaultMuted = true;
      art.loop = true;
      art.playsInline = true;
      art.preload = 'auto';
      art.poster = game.media.thumbnail;
      art.setAttribute('disablepictureinpicture', '');
    } else art.alt = '';
    const frame = doc.createElement('div');
    frame.className = 'art-frame';
    frame.append(art);
    scene.append(frame);
    const shade = doc.createElement('div');
    shade.className = 'shade';
    scene.append(shade);
    const caption = doc.createElement('div');
    caption.className = 'caption';
    const title = doc.createElement('h1');
    title.textContent = String(game.name || '');
    title.hidden = !options.showLogos;
    const credit = doc.createElement('p');
    credit.className = 'credit artwork-credit';
    credit.hidden = !options.showArtworkCredit;
    credit.textContent = `${french() ? 'Artwork de' : 'Artwork by'} ${String(game.media.author?.name || 'Unknown')} · SteamGridDB`;
    const copy = doc.createElement('div');
    copy.className = 'caption-copy';
    copy.append(title, credit);
    if (game.logo?.animated === false && localMedia(game.logo.file)) {
      const logo = doc.createElement('img');
      logo.className = 'game-logo';
      logo.alt = String(game.name || '');
      logo.hidden = true;
      logo.addEventListener('load', () => {
        if (!logo._sasReleased) placeBranding(scene);
      });
      logo.addEventListener('error', () => {
        if (logo._sasReleased) return;
        logo.dataset.failed = 'true';
        placeBranding(scene);
      });
      copy.prepend(logo);
      const logoCredit = doc.createElement('p');
      logoCredit.className = 'credit logo-credit';
      logoCredit.hidden = true;
      logoCredit.textContent = `${french() ? 'Logo de' : 'Logo by'} ${String(game.logo.author?.name || 'Unknown')} · SteamGridDB`;
      copy.append(logoCredit);
      logo.src = game.logo.file;
    }
    const cover = doc.createElement('img');
    cover.className = 'caption-cover';
    cover.alt = french() ? `Jaquette de ${game.name}` : `${game.name} cover`;
    const hasCover = game.cover?.animated === false && localMedia(game.cover.file);
    cover.dataset.fallback = String(!hasCover);
    cover.src = hasCover ? game.cover.file : game.media.thumbnail;
    cover.addEventListener('error', () => {
      if (cover._sasReleased || cover._sasSuspended) return;
      if (cover.dataset.fallback !== 'true') {
        cover.dataset.fallback = 'true';
        cover.src = game.media.thumbnail;
      } else cover.dataset.failed = 'true';
      placeCover(scene);
    });
    if (hasCover) {
      const coverCredit = doc.createElement('p');
      coverCredit.className = 'credit cover-credit';
      coverCredit.textContent = `${french() ? 'Jaquette de' : 'Cover by'} ${String(game.cover.author?.name || 'Unknown')} · SteamGridDB`;
      copy.append(coverCredit);
    }
    caption.append(cover, copy);
    scene.append(caption);
    placeCover(scene);
    placeFrame(scene);
    return { scene, art, isVideo };
  }
  function display(game, remember = true) {
    if (destroyed || !game) return;
    debug(global,'scene-attempt',{scene:Math.max(0,games.indexOf(game)),count:games.length,slot:Math.max(0,slot)});
    clearTimer();
    clearTimeout(loadTimer);
    clearTimeout(transitionTimer);
    loading = true;
    if (retiring) {
      release(retiring);
      retiring = null;
    }
    if (pending) {
      release(pending);
      pending = null;
    }
    const prepared=preload?.game===game?preload:null;
    if(prepared)preload=null;
    const token = ++generation,
      { scene, art, isVideo } = prepared || sceneFor(game);
    stage.append(scene);
    placeBranding(scene);
    pending = scene;
    let complete = false;
    function fail(event) {
      debug(global,event?.type==='error'?'media-error':'scene-timeout',{scene:Math.max(0,games.indexOf(game)),ready_state:art.readyState,network_state:art.networkState,media_error:art.error?.code});
      if(coordinated&&current===scene){scene.classList.add('matrix-placeholder');notify('media-placeholder',game);return;}
      if (complete || token !== generation || destroyed || art._sasSuspended || art._sasReleased)
        return;
      complete = true;
      clearTimeout(loadTimer);
      release(scene);
      pending = null;
      loading = false;
      failures.add(game.id);
      notify('media-error', game);
      if (failures.size >= games.length) {
        release(current);
        current = null;
        emptyState(true);
        clearTimer();
        return;
      }
      next();
    }
    function ready() {
      if (complete || token !== generation || destroyed) return;
      complete = true;
      clearTimeout(loadTimer);
      failures.delete(game.id);
      empty.hidden = true;
      loading = false;
      const old = current;
      current = scene;
      pending = null;
      retiring = old;
      scene.classList.toggle('paused', !playing);
      if (remember) {
        history = history.slice(0, historyPosition + 1);
        history.push(game);
        if (history.length > 1000) history.shift();
        historyPosition = history.length - 1;
      }
      const show = () => {
        if (token !== generation || destroyed) return;
        if(scene.classList.contains('matrix-wait')){
          resumeScene(scene);
          scene.classList.remove('matrix-wait');
        }
        if (!old && !options.reducedMotion) {
          // The first decoded frame appears directly; later scene changes keep their transitions.
          scene.classList.add('instant');
          global.requestAnimationFrame(() => {
            if (!destroyed && scene.isConnected)
              scene.classList.toggle('instant', options.reducedMotion);
          });
        }
        scene.classList.add('visible');
        scene._shownAt=performance.now();
        debug(global,'scene-visible',{scene:Math.max(0,games.indexOf(game)),slot:Math.max(0,slot),flags:{video:isVideo,playing,coordinated}});
        if(coordinated&&epoch===null)epoch=performance.now();
        if (isVideo && playing) art.play().catch(runtimeFailure);
        if (old) {
          old.classList.remove('visible');
          transitionTimer = setTimeout(
            () => {
              release(old);
              if (retiring === old) retiring = null;
            },
            options.reducedMotion ? 0 : coordinated?450:1250
          );
        }
        schedule();
        notify(playing ? 'playing' : 'paused', game);
      };
      // Fade to black waits for the old scene to disappear before revealing the next.
      if (old && options.transition === 'fade-black' && !options.reducedMotion && playing) {
        old.classList.remove('visible');
        transitionTimer = setTimeout(show, coordinated?200:1200);
      } else if (!old && jsaux) {
        if(jsaux.waitingForMatrix){
          scene.classList.add('instant','visible','matrix-wait');
          freezeScene(scene);
          if(isVideo)art.pause();
          debug(global,'first-frame-held',{reason:'matrix-start'});
        }
        jsaux.ready(timing=>{
          if(coordinated&&timing){
            epoch=timing.epoch;slot=presentationSlot(epoch,performance.now(),options.sceneDuration*1000);
            position=slot%order.length;
            if(position!==0){display(order[position]);return;}
          }
          global.requestAnimationFrame(show);
        });
      }
      else global.requestAnimationFrame(show);
      if (!playing) {
        if (isVideo) art.pause();
        else freezeScene(scene);
      }
    }
    art.addEventListener(isVideo ? 'canplay' : 'load', ()=>{
      if(complete){scene.classList.remove('matrix-placeholder');return;}
      ready();
    }, { once: true });
    art.addEventListener('error', fail, { once: true });
    loadTimer = setTimeout(fail, 15000);
    if(!prepared){art.src = game.media.file;if (isVideo) art.load();}
    if(coordinated&&oldSceneExists()){
      // A slow/broken next media keeps its identity and fixed time slot. It does
      // not silently skip a matrix page or restart the presentation clock.
      if(!prepared?.ready)scene.classList.add('matrix-placeholder');
      ready();
    }else if(prepared?.ready)queueMicrotask(ready);
    function oldSceneExists(){return current!==null;}
    // Decoder failures after startup also skip the failed scene.
    function runtimeFailure() {
      debug(global,'media-error',{reason:'unknown',scene:Math.max(0,games.indexOf(game)),ready_state:art.readyState,network_state:art.networkState,media_error:art.error?.code});
      if (art._sasSuspended || art._sasReleased) return;
      if(coordinated&&current===scene){scene.classList.add('matrix-placeholder');notify('media-placeholder',game);return;}
      if (current === scene) {
        failures.add(game.id);
        notify('media-error', game);
        release(scene);
        current = null;
        if (failures.size >= games.length) {
          clearTimer();
          emptyState(true);
        } else next();
      }
    }
    art.addEventListener('error', runtimeFailure);
    if(isVideo)for(const event of ['waiting','stalled','ended'])art.addEventListener(event,()=>{
      if(art._sasReleased)return;
      debug(global,'media-'+event,{scene:Math.max(0,games.indexOf(game)),ready_state:art.readyState,network_state:art.networkState,
        media_ms:Math.max(0,Math.floor((art.currentTime||0)*1000))});
    });
  }
  function next() {
    if (destroyed || !games.length) return;
    if (historyPosition < history.length - 1) {
      display(history[++historyPosition], false);
      return;
    }
    if (position + 1 >= order.length) newOrder(current?.game?.id);
    let tried = 0,
      game;
    do {
      game = order[++position];
      if (position >= order.length) {
        newOrder(current?.game?.id);
        game = order[++position];
      }
    } while (game && failures.has(game.id) && ++tried < games.length);
    if (game && !failures.has(game.id)) display(game);
  }
  function previous() {
    if (historyPosition > 0) display(history[--historyPosition], false);
  }
  function loadCatalog(value, waitingForParent = false) {
    debug(global,value?'catalog-loaded':'catalog-missing',{count:Array.isArray(value?.games)?value.games.length:0,
      flags:{catalog_match:!!value?.jsaux&&value.jsaux.collection_id===global.DAS_PLAYER_BOOT?.collection_id}});
    if(jsaux)jsaux.stop();
    empty.hidden = true;
    ++generation;
    clearTimer();
    clearTimeout(loadTimer);
    clearTimeout(transitionTimer);
    for (const scene of [...stage.children]) release(scene);
    current = retiring = pending = null;
    if(preload){release(preload.scene);preload=null;}
    epoch=null;slot=0;
    loading = false;
    failures.clear();
    catalog = value || { games: [] };
    options = settings({ ...defaults, ...catalog.settings });
    if(catalog.jsaux?.enabled&&catalog.jsaux?.mode==='sync'&&!catalog.previewNonce)options.shuffle=false;
    games = catalogGames(catalog, options);
    const validPresentation=presentationMatches(catalog,games,options);
    const manifest=catalog.presentation;
    debug(global,'catalog-filtered',{count:games.length,expected:Array.isArray(catalog.games)?catalog.games.length:0});
    debug(global,'presentation-check',{flags:{presentation_valid:!!validPresentation,version_match:manifest?.version===2,
      duration_match:manifest?.page_ms===options.sceneDuration*1000,orientation_match:manifest?.orientation===0,
      transition_match:manifest?.transition_included===true,count_match:Array.isArray(manifest?.order)&&manifest.order.length===games.length,
      order_match:Array.isArray(manifest?.order)&&manifest.order.length===games.length&&manifest.order.every((id,n)=>id===(games[n].steamAppId||(/^steam:\d+$/.test(games[n].id)?Number(games[n].id.slice(6)):/^sgdb:\d+$/.test(games[n].id)?-Number(games[n].id.slice(5)):null)))}});
    if(catalog.jsaux?.mode==='sync'&&!validPresentation)debug(global,'lifecycle-disabled',{reason:'presentation-invalid'});
    coordinated=Boolean(catalog.jsaux?.enabled&&catalog.jsaux.mode==='sync'&&!catalog.previewNonce&&validPresentation);
    jsaux=createJsauxLifecycle(global,doc,catalog.jsaux?.mode==='sync'&&!validPresentation?{...catalog,jsaux:null}:catalog);
    stage.classList.toggle('coordinated',coordinated);
    stage.classList.toggle('fade-black',options.transition==='fade-black');
    history = [];
    historyPosition = -1;
    newOrder();
    if (games.length) next();
    else if (!waitingForParent) emptyState();
  }
  function setSettings(partial) {
    if ('showLogos' in partial && !('nameDisplay' in partial))
      partial = { ...partial, nameDisplay: partial.showLogos ? 'logo' : 'hidden' };
    const nextSettings = settings({ ...options, ...partial });
    const structural =
      nextSettings.staticFallback !== options.staticFallback ||
      nextSettings.shuffle !== options.shuffle;
    options = nextSettings;
    catalog.settings = options;
    if (structural) {
      loadCatalog(catalog);
      return;
    }
    for (const scene of stage.children) {
      scene.classList.toggle('reduced', options.reducedMotion);
      scene.classList.toggle('instant', options.reducedMotion);
      placeBranding(scene);
      placeCover(scene);
      placeFrame(scene);
    }
    schedule();
  }
  function message(event) {
    const data = event.data;
    if (!data || data.type !== 'screensaver' || !catalog.previewNonce || data.nonce !== catalog.previewNonce) return;
    // Decky may render into a Steam popup while handlers execute in its opener.
    // A nonce-authenticated command from that exact parent origin is valid too.
    // Installed (non-preview) players never accept this control channel.
    let parentOrigin='';
    try{parentOrigin=global.location.ancestorOrigins?.[0]||new URL(doc.referrer).origin;}catch{}
    if(event.source===global || (event.source!==global.parent&&(!parentOrigin||event.origin!==parentOrigin)))return;
    if (data.action === 'status') { if(current&&!loading)notify(playing?'playing':'paused',current.game); }
    else if (data.action === 'catalog') loadCatalog(data.catalog);
    else if (data.action === 'settings') setSettings(data.settings || data.partial || {});
    else if (data.action === 'play') setPaused(false);
    else if (data.action === 'pause') setPaused(true);
    else if (data.action === 'next') next();
    else if (data.action === 'previous') previous();
  }
  function visibility() {
    if (doc.hidden) {
      debug(global,'lifecycle-exit',{reason:'visibility-hidden'});
      if(jsaux)jsaux.stop('visibility-hidden');
      hiddenPause = playing;
      setPaused(true,true);
    } else if (hiddenPause) {
      hiddenPause = false;
      setPaused(false,true);
    }
  }
  function destroy() {
    if (destroyed) return;
    destroyed = true;
    debug(global,'lifecycle-exit',{reason:'destroyed'});
    if(jsaux)jsaux.stop('destroyed');
    ++generation;
    clearTimer();
    clearTimeout(loadTimer);
    clearTimeout(transitionTimer);
    for (const scene of [...stage.children]) release(scene);
    if(preload){release(preload.scene);preload=null;}
    global.removeEventListener('message', message);
    global.removeEventListener('resize', resizeFrames);
    global.removeEventListener('pagehide', destroy);
    doc.removeEventListener('visibilitychange', visibility);
    games = [];
    order = [];
    history = [];
    global.SteamAnimatedScreensaverPlayer = null;
  }
  global.SteamAnimatedScreensaverPlayer = {
    play: () => setPaused(false),
    pause: () => setPaused(true),
    next:()=>{degrade();next();},
    previous:()=>{degrade();previous();},
    setSettings,
    destroy
  };
  global.addEventListener('message', message);
  global.addEventListener('resize', resizeFrames);
  global.addEventListener('pagehide', destroy, { once: true });
  doc.addEventListener('visibilitychange', visibility);
  loadCatalog(global.SAS_CATALOG, global.parent !== global);
})(typeof window !== 'undefined' ? window : globalThis);
