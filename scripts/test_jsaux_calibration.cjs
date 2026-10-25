"use strict";
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
let chromium;try{chromium=require('playwright').chromium;}catch{}
const executable=process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const root=path.resolve(__dirname,'../assets/player');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=','base64');
for(const offset of [0,5000,-10000])test(`Installed calibrated calendar ${offset} ms: correct slot over ten minutes, one session`,
 {skip:!chromium||!fs.existsSync(executable),timeout:60000},async()=>{
 const browser=await chromium.launch({executablePath:executable,headless:true});
 try{
  const page=await browser.newPage();await page.clock.install();
  await page.addInitScript(offset=>{
   window.__calls=[];window.__shown=[];window.__ref=null;const values=new Map();let deadline;
   window.SteamClient={Storage:{GetString:k=>values.get(k)||'',SetString(k,v){
    values.set(k,v);if(!k.endsWith('request.v1'))return;
    const p=JSON.parse(v).payload;window.__calls.push(p);let result={accepted:true};
    if(p.event==='open')result={accepted:true,alignment_ms:offset};
    if(p.event==='clock')result={broker_mono_ms:Math.floor(performance.now()+100000)};
    if(p.event==='ready'){deadline=p.deadline_mono_ms;window.__ref=p.ready_mono_ms+3000;result={gate_accepted:true};}
    if(p.event==='heartbeat'&&performance.now()+100000>=window.__ref)result={accepted:true,
      candidate:{candidate_id:'candidate1',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'},
      timing:{basis:'broker-confirmation-event',reference_mono_ms:window.__ref,uncertainty_ms:1}};
    values.set('decky-animated-screensaver.jsaux.reply.v1',JSON.stringify({session_id:p.session_id,sequence:p.sequence,result}));
   }}};
   new MutationObserver(records=>{for(const r of records){const n=r.target;if(n.classList?.contains('scene')&&n.classList.contains('visible')&&!n.__recorded){n.__recorded=true;window.__shown.push({id:n.game.id,at:performance.now()});}}}).observe(document,{subtree:true,attributes:true,attributeFilter:['class']});
  },offset);
  const games=[1,2,3].map(n=>({id:'steam:'+n,name:'Game '+n,included:true,status:'ready',media:{file:'media/'+n+'.gif',thumbnail:'media/thumb.png',format:'gif',animated:true}}));
  const catalog={version:1,games,bridge_token:'token1',jsaux:{enabled:true,mode:'sync',sync_wait_ms:15000,collection_id:'a'.repeat(64)},
    presentation:{version:2,order:[1,2,3],transition_included:true,page_ms:8000,transition_ms:400,orientation:0},
    settings:{sceneDuration:8,shuffle:false,reducedMotion:true,showCover:false}};
  await page.route('**/*',route=>{
   const url=new URL(route.request().url()),leaf=path.basename(url.pathname);
   if(url.pathname.includes('/media/'))return route.fulfill({contentType:'image/png',body:png});
   if(leaf==='catalog.js')return route.fulfill({contentType:'text/javascript',body:'window.SAS_CATALOG='+JSON.stringify(catalog)});
   if(['index.html','player.js','player.css','diagnostic.js','diagnostic-config.js'].includes(leaf))return route.fulfill({contentType:leaf.endsWith('.js')?'text/javascript':leaf.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(root,leaf))});
   return route.abort();
  });
  await page.goto('https://decky-animated-screensaver.steamloopback.host/index.html');
  await page.clock.runFor(16000);await page.clock.runFor(600000);
  const result=await page.evaluate(()=>({shown:window.__shown,calls:window.__calls,reference:window.__ref,scenes:document.querySelectorAll('.scene').length}));
  const started=result.calls.filter(x=>x.event==='started');assert.equal(started.length,1,JSON.stringify(result));
  assert.equal(started[0].outcome,'software-coordinated');assert.equal(result.calls.filter(x=>x.event==='open').length,1);
  assert.equal(result.calls.filter(x=>x.event==='ready').length,1);assert.equal(result.calls.filter(x=>x.event==='stop').length,0);
  assert(result.shown.length>70);assert(result.scenes<=2);
  const epoch=result.reference-100000+offset,steady=result.shown.filter(x=>x.at>30000);
  for(const event of steady){
   const slot=Math.floor((event.at-epoch+1)/8000);assert.equal(event.id,'steam:'+(slot%3+1),JSON.stringify({offset,epoch,event}));
   assert(Math.abs(event.at-(epoch+slot*8000))<40,JSON.stringify({offset,epoch,event}));
  }
  await page.evaluate(()=>window.SteamAnimatedScreensaverPlayer.destroy());await page.clock.runFor(50);
  assert((await page.evaluate(()=>window.__calls)).some(x=>x.event==='stop'));
 }finally{await browser.close();}
});
