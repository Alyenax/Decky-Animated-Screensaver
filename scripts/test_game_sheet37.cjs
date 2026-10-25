// Actual player, actual GIF and opener-to-popup control. No Decky/JSAUX proof.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawnSync}=require('node:child_process');
const {chromium}=require('playwright');
test('Popup controls reach the actual player; independent corners and cover-left collisions never overlap', {timeout:60000},async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'das-sheet37-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const ffmpeg=process.env.DAS_TEST_FFMPEG;assert(ffmpeg);
 for(const [name,input] of [['scene.gif','testsrc=size=160x90:rate=8:duration=2'],['cover.png','color=c=blue:size=80x120'],['logo.png','color=c=pink:size=160x60']]){
  const args=['-hide_banner','-loglevel','error','-f','lavfi','-i',input,...(name.endsWith('.png')?['-frames:v','1']:[]),'-y',path.join(root,name)];
  const result=spawnSync(ffmpeg,args,{encoding:'utf8',timeout:10000});assert.equal(result.status,0,result.stderr);
 }
 const assets=path.resolve('assets/player');
 const server=http.createServer(async(req,res)=>{try{
  if(req.url==='/host'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><iframe src="/player/index.html" style="position:fixed;inset:0;border:0;width:100%;height:100%"></iframe>');return;}
  let data,mime;
  if(req.url==='/player/catalog.js'){data="window.SAS_CATALOG={version:1,previewNonce:'nonce37',games:[],settings:{}};";mime='text/javascript';}
  else if(['/player/index.html','/player/player.js','/player/player.css','/player/diagnostic.js','/player/diagnostic-config.js'].includes(req.url)){
   data=await fs.readFile(path.join(assets,path.basename(req.url)));mime=req.url.endsWith('.html')?'text/html':req.url.endsWith('.css')?'text/css':'text/javascript';
  }else if(['/media/scene.gif','/media/cover.png','/media/logo.png'].includes(req.url)){
   data=await fs.readFile(path.join(root,path.basename(req.url)));mime=req.url.endsWith('.gif')?'image/gif':'image/png';
  }else{res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',mime);res.end(data);
 }catch{res.writeHead(500);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>{server.closeAllConnections();return new Promise(resolve=>server.close(resolve));});
 const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});t.after(()=>browser.close());
 const page=await browser.newPage();page.setDefaultTimeout(5000);await page.goto(origin+'/host');console.log('Main host loaded.');
 const popupEvent=page.waitForEvent('popup');await page.evaluate(url=>{window.previewPopup=window.open(url);},origin+'/host');const popup=await popupEvent;popup.setDefaultTimeout(5000);await popup.waitForLoadState();await popup.bringToFront();console.log('Popup host loaded.');
 const frame=popup.frames().find(f=>f.url().includes('/player/index.html'));assert(frame);await frame.waitForFunction(()=>window.SteamAnimatedScreensaverPlayer);
 const send=data=>page.evaluate(data=>window.previewPopup.document.querySelector('iframe').contentWindow.postMessage({type:'screensaver',nonce:'nonce37',...data},location.origin),data);
 const game=id=>({id:'steam:'+id,name:'Game '+id,status:'ready',included:true,media:{file:'/media/scene.gif',thumbnail:'/media/scene.gif',format:'gif',animated:true},cover:{file:'/media/cover.png',animated:false},logo:{file:'/media/logo.png',animated:false}});
 await send({action:'catalog',catalog:{version:1,previewNonce:'nonce37',games:[game(1),game(2),game(3)],settings:{shuffle:false,sceneDuration:180,nameDisplay:'both',reducedMotion:true}}});
 await frame.waitForFunction(()=>document.querySelector('.scene.visible')?.game.id==='steam:1');
 console.log('Actual player received catalog from its popup opener.');
 await send({action:'pause',nonce:'wrong'});await popup.waitForTimeout(100);assert.equal(await frame.locator('.scene.visible.paused').count(),0,'wrong nonce is refused');
 await send({action:'pause'});await frame.waitForFunction(()=>document.querySelector('.scene.visible')?.classList.contains('paused'));
 await popup.waitForTimeout(250);const still=await frame.locator('#stage').screenshot();await popup.waitForTimeout(350);const stillB=await frame.locator('#stage').screenshot();
 if(!stillB.equals(still)){await fs.mkdir('out/ui/game-sheet37',{recursive:true});await fs.writeFile('out/ui/game-sheet37/pause-a.png',still);await fs.writeFile('out/ui/game-sheet37/pause-b.png',stillB);console.log(await frame.evaluate(()=>({hidden:document.hidden,scenes:[...document.querySelectorAll('.scene')].map(s=>({classes:s.className,imgs:[...s.querySelectorAll('img')].map(i=>({class:i.className,hidden:i.hidden,src:i.getAttribute('src'),snapshot:!!i._sasSnapshot}))}))})));}
 assert(stillB.equals(still),'pause really freezes GIF pixels');
 await send({action:'play'});await frame.waitForFunction(()=>!document.querySelector('.scene.visible')?.classList.contains('paused'));
 await popup.waitForTimeout(220);const moving=await frame.locator('#stage').screenshot();await popup.waitForTimeout(350);assert(!(await frame.locator('#stage').screenshot()).equals(moving),'play really resumes GIF pixels');
 await send({action:'next'});await frame.waitForFunction(()=>document.querySelector('.scene.visible')?.game.id==='steam:2');
 await send({action:'previous'});await frame.waitForFunction(()=>document.querySelector('.scene.visible')?.game.id==='steam:1');
 for(const width of [1280,800,480]){
  await popup.setViewportSize({width,height:Math.round(width*10/16)});
  for(const corner of ['bottom-left','bottom-right','top-left','top-right'])for(const logoCorner of ['bottom-left','bottom-right','top-left','top-right']){
   await send({action:'catalog',catalog:{version:1,previewNonce:'nonce37',games:[{...game(1),coverPosition:corner,branding:{mode:'logo',position:logoCorner}}],settings:{shuffle:false,sceneDuration:180,reducedMotion:true,nameDisplay:'both',coverPosition:'bottom-right',logoPosition:'top-right'}}});
   await frame.waitForFunction(({corner,logoCorner})=>{const s=document.querySelector('.scene.visible');return s?.dataset.coverPosition===corner&&s.dataset.logoPosition===logoCorner&&s.querySelector('.game-logo')?.naturalWidth>0&&s.classList.contains('branding-pair')===(corner===logoCorner);},{corner,logoCorner});
   const boxes=await frame.evaluate(()=>{const s=document.querySelector('.scene.visible');const rect=selector=>{const r=s.querySelector(selector).getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};};return {cover:rect('.caption-cover'),logo:rect('.game-logo'),width:innerWidth,height:innerHeight};});
   const {cover,logo}=boxes;
   const detail=JSON.stringify({width,corner,logoCorner,boxes});
   if(corner===logoCorner)assert(cover.right+1<=logo.left,detail);
   else{
    const anchor=(box,c)=>{
     assert(Math.abs((c.endsWith('left')?box.left:width-box.right)-width*.056)<1,detail);
     assert(Math.abs((c.startsWith('top')?box.top:boxes.height-box.bottom)-boxes.height*.07)<1,detail);
    };
    anchor(cover,corner);anchor(logo,logoCorner);
    assert(cover.right<=logo.left||logo.right<=cover.left||cover.bottom<=logo.top||logo.bottom<=cover.top,detail);
   }
   for(const box of [cover,logo])assert(box.left>=0&&box.top>=0&&box.right<=width+.5&&box.bottom<=boxes.height+.5,JSON.stringify({width,corner,boxes}));
   if(corner===logoCorner){
    if(corner.endsWith('left'))assert(Math.abs(cover.left-width*.056)<1);
    else assert(Math.abs(logo.right-width*.944)<1);
   }
   if(corner.startsWith('top'))assert(Math.abs(cover.top-boxes.height*.07)<1);
   else assert(Math.abs(cover.bottom-boxes.height*.93)<1);
  }
 }
 await fs.mkdir('out/ui/game-sheet37',{recursive:true});await popup.screenshot({path:'out/ui/game-sheet37/actual-paired-player.png'});
 // Existing global choices remain independent when a game inherits its logo.
 await send({action:'catalog',catalog:{version:1,previewNonce:'nonce37',games:[{...game(1),coverPosition:'top-left',branding:{mode:'logo',position:'inherit'}}],settings:{shuffle:false,sceneDuration:180,reducedMotion:true,nameDisplay:'logo',logoPosition:'bottom-right'}}});
 await frame.waitForFunction(()=>{const s=document.querySelector('.scene.visible');return s?.dataset.logoPosition==='bottom-right'&&s.querySelector('.game-logo')?.naturalWidth>0&&!s.classList.contains('branding-pair');});
 // Hiding the cover does not displace a separately anchored logo.
 const cornerBefore=await frame.locator('.scene.visible .game-logo').boundingBox();
 await send({action:'settings',settings:{showCover:false}});
 await frame.waitForFunction(()=>!document.querySelector('.scene.visible')?.classList.contains('has-cover'));
 assert.deepEqual(await frame.locator('.scene.visible .game-logo').boundingBox(),cornerBefore);
 await send({action:'settings',settings:{showCover:true,logoPosition:'top-left'}});
 await frame.waitForFunction(()=>document.querySelector('.scene.visible')?.classList.contains('branding-pair'));
 // A hidden-mode game disables pairing.
 await send({action:'catalog',catalog:{version:1,previewNonce:'nonce37',games:[{...game(1),coverPosition:'top-left',branding:{mode:'hidden',position:'top-left'}}],settings:{shuffle:false,sceneDuration:180,reducedMotion:true,logoPosition:'top-left'}}});
 await frame.waitForFunction(()=>{const s=document.querySelector('.scene.visible');return s?.querySelector('.game-logo')?.hidden&&!s.classList.contains('branding-pair');});
 const fallback=game(4);delete fallback.cover;
 await send({action:'catalog',catalog:{version:1,previewNonce:'nonce37',games:[fallback],settings:{shuffle:false,sceneDuration:180,reducedMotion:true}}});
 await frame.waitForFunction(()=>document.querySelector('.scene.visible')?.game.id==='steam:4');await send({action:'pause'});
 await frame.waitForFunction(()=>document.querySelector('canvas.frozen-cover'));const fallbackA=await frame.locator('#stage').screenshot();await popup.waitForTimeout(350);assert((await frame.locator('#stage').screenshot()).equals(fallbackA),'fallback cover and ambient GIF stop too');
 await send({action:'settings',settings:{showCover:false}});await frame.waitForFunction(()=>document.querySelector('canvas.frozen-cover')?.hidden===true);
 await send({action:'settings',settings:{showCover:true}});await frame.waitForFunction(()=>document.querySelector('canvas.frozen-cover')?.hidden===false);
 await send({action:'play'});await frame.waitForFunction(()=>!document.querySelector('canvas.frozen-cover'));
 console.log('PASS real opener-to-popup Previous/Pause/Play/Next, nonce refusal, frozen/resumed GIF/ambient/fallback-cover pixels; 48 independent/collision layouts, inherited settings and hidden elements. Not SteamOS or hardware evidence.');
});
