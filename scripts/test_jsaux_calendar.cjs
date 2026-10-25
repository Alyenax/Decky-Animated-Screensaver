"use strict";
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
let chromium;try{chromium=require('playwright').chromium;}catch{}
const executable=process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const root=path.resolve(__dirname,'../assets/player');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=','base64');
test('Actual installed player: absolute slots, placeholder, one preload, pause revokes',
 {skip:!chromium||!fs.existsSync(executable),timeout:60000},async()=>{
 const browser=await chromium.launch({executablePath:executable,headless:true});
 try{
  const page=await browser.newPage();await page.clock.install();
  await page.addInitScript(()=>{
   window.__calls=[];window.__shown=[];const values=new Map();let deadline;
   window.SteamClient={Storage:{GetString:k=>values.get(k)||'',SetString(k,v){
    values.set(k,v);if(!k.endsWith('request.v1'))return;
    const p=JSON.parse(v).payload;window.__calls.push(p);let result={accepted:true};
    if(p.event==='clock')result={broker_mono_ms:Math.floor(performance.now()+100000)};
    if(p.event==='ready'){deadline=p.deadline_mono_ms;result={accepted:true,gate_accepted:true};}
    if(p.event==='heartbeat')result={accepted:true,candidate:performance.now()+100000>=deadline-9000?{candidate_id:'candidate1',deadline_mono_ms:deadline,phase_basis:'gif-end-ack-assumption',optical_alignment:'unknown'}:null};
    values.set('decky-animated-screensaver.jsaux.reply.v1',JSON.stringify({session_id:p.session_id,sequence:p.sequence,result}));
   }}};
   new MutationObserver(records=>{for(const r of records){const n=r.target;if(n.classList?.contains('scene')&&n.classList.contains('visible')&&!n.__recorded){n.__recorded=true;window.__shown.push({id:n.game.id,at:performance.now()});}}}).observe(document,{subtree:true,attributes:true,attributeFilter:['class']});
  });
  const games=[1,2,3].map(n=>({id:'steam:'+n,name:'Game '+n,included:true,status:'ready',media:{file:'media/'+n+'.gif',thumbnail:'media/thumb.png',format:'gif',animated:true}}));
  const catalog={version:1,games,bridge_token:'token1',jsaux:{enabled:true,mode:'sync',sync_wait_ms:15000,collection_id:'a'.repeat(64)},presentation:{version:2,order:[1,2,3],transition_included:true,page_ms:8000,transition_ms:400,orientation:0},settings:{sceneDuration:8,shuffle:false,transition:'fade-black',showLogos:true,showCover:false}};
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url()),leaf=path.basename(url.pathname);
   if(url.pathname.includes('/media/')){if(leaf==='2.gif')return route.fulfill({status:404,body:''});return route.fulfill({contentType:'image/png',body:png});}
   if(leaf==='catalog.js')return route.fulfill({contentType:'text/javascript',body:'window.SAS_CATALOG='+JSON.stringify(catalog)});
   if(['index.html','player.js','player.css','diagnostic.js','diagnostic-config.js'].includes(leaf))return route.fulfill({contentType:leaf.endsWith('.js')?'text/javascript':leaf.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(root,leaf))});
   return route.abort();
  });
  await page.goto('https://decky-animated-screensaver.steamloopback.host/index.html');
  await page.clock.runFor(4000);
  assert.equal(await page.evaluate(()=>window.__shown.length),1,'Decoded first frame must be visible while waiting, never a blank screen');
  assert.equal(await page.evaluate(()=>document.querySelectorAll('.matrix-wait.visible').length),1);
  assert.equal(await page.evaluate(()=>window.__calls.filter(x=>x.event==='started').length),0,'Visible still must not advance the presentation before the receipt');
  await page.clock.runFor(4000);await page.waitForFunction(()=>window.__shown.length>0);
  assert.equal(await page.evaluate(()=>window.__calls.find(x=>x.event==='started')?.outcome),'software-coordinated');
  assert.equal(await page.evaluate(()=>document.querySelectorAll('.matrix-wait').length),0);
  await page.clock.runFor(76*8000);
  const result=await page.evaluate(()=>({shown:window.__shown,calls:window.__calls,scenes:document.querySelectorAll('.scene').length,placeholders:document.querySelectorAll('.matrix-placeholder').length}));
  assert(result.shown.length>=75,JSON.stringify(result));
  assert.equal(result.calls.filter(x=>x.event==='stop').length,0,'Multiple GIF loops and ten minutes must not release an active screensaver');
  for(let i=2;i<result.shown.length;i++)assert(Math.abs(result.shown[i].at-result.shown[1].at-(i-1)*8000)<40,JSON.stringify(result.shown));
  assert(result.shown.some(x=>x.id==='steam:2'));assert(result.scenes<=2);
  assert.equal(result.calls.filter(x=>x.event==='ready').length,1);
  await page.evaluate(()=>window.SteamAnimatedScreensaverPlayer.pause());
  await page.clock.runFor(50);assert((await page.evaluate(()=>window.__calls)).some(x=>x.event==='stop'));
  await page.evaluate(()=>window.SteamAnimatedScreensaverPlayer.destroy());
 }finally{await browser.close();}
});
