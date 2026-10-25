'use strict';
// Actual installer/catalog/player + real 720p PNGs. No codec, Steam or USB mocks
// are used as evidence for hardware: this is local browser playback only.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),http=require('node:http');
const {spawnSync}=require('node:child_process'),{chromium}=require('playwright');
test('original stills use gentle transforms, fixed/reduced stay fixed, and playback continues',{timeout:50000},async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'das-motion56-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const code=`
import sys,json
from pathlib import Path
from PIL import Image,ImageDraw
from das.studio.storage import Store
from das.studio.installer import Installer
from das.core.catalog import file_sha256
root=Path(sys.argv[1]);store=Store(root/'studio')
store.configure(dict(scene_seconds=8,shuffle=False,static_fallback=True,show_cover=False,show_logo=False,name_display='hidden'))
originals={}
for number,mode in ((620,'motion'),(621,'fixed')):
 source=store.managed('media/original'+str(number)+'.png');source.parent.mkdir(exist_ok=True)
 image=Image.new('RGB',(1280,720),'#27394c');draw=ImageDraw.Draw(image)
 for x in range(0,1280,64):draw.rectangle((x,0,x+20,719),fill=((x//8)%255,90,160))
 draw.text((560,330),mode,fill='white');image.save(source);digest=file_sha256(source);originals[str(source)]=digest
 store.update(number,dict(name='Still '+str(number),status='ready',animated=False,format='png',width=1280,height=720,excluded=False,still_mode=mode,media=dict(tv='media/'+source.name,thumbnail='media/'+source.name),sha256=dict(tv=digest,thumbnail=digest)))
steam=root/'Steam';steam.mkdir();installer=Installer(store,steam,sys.argv[2]);installer.install()
assert all(file_sha256(Path(name))==digest for name,digest in originals.items())
print(json.dumps(dict(destination=str(installer.destination),originals_preserved=True)))
`;
 const built=spawnSync(process.env.DAS_TEST_PYTHON||'python3',['-c',code,root,path.resolve('assets/player')],{env:{...process.env,PYTHONPATH:path.resolve('py_modules'),PYTHONPYCACHEPREFIX:'/private/tmp/das56-motion-pycache'},encoding:'utf8',timeout:15000});
 assert.equal(built.status,0,built.stderr);const info=JSON.parse(built.stdout);
 const requests=[],server=http.createServer(async(req,res)=>{try{
  const name=new URL(req.url,'http://localhost').pathname;requests.push(name);
  const target=path.resolve(info.destination,'.'+name);if(!target.startsWith(info.destination+path.sep)){res.writeHead(404);res.end();return;}
  const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png'}[path.extname(target)];
  if(!mime){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime);res.end(await fs.readFile(target));
 }catch{res.writeHead(404);res.end();}});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>{server.closeAllConnections();return new Promise(resolve=>server.close(resolve));});
 const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});t.after(()=>browser.close());
 const page=await browser.newPage({viewport:{width:1280,height:720}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+server.address().port+'/index.html');await page.locator('.scene.visible.gentle img.artwork').waitFor();
 assert.equal(await page.locator('video').count(),0,'Still motion never requires a video decoder');
 const scales=await page.locator('.scene.visible .artwork').evaluate(async art=>{const animation=art.getAnimations()[0];if(!animation)throw Error('Gentle CSS motion absent');animation.pause();const values=[];
  for(const time of [0,15000,30000,45000,60000]){animation.currentTime=time;await new Promise(requestAnimationFrame);const matrix=new DOMMatrix(getComputedStyle(art).transform);values.push({time,scale:matrix.a,x:matrix.e,y:matrix.f});}
  animation.currentTime=0;animation.play();return values;
 });
 assert(Math.abs(scales[0].scale-1)<.0001&&Math.abs(scales[2].scale-1.18)<.0001&&Math.abs(scales[4].scale-1)<.0001);
 assert(scales.every(v=>v.scale>=1&&v.scale<=1.1801&&v.x>=0&&v.x<=38.401&&Math.abs(v.y)<.001),'Bounded 18% zoom with a 3% lateral pan at the default anchor');
 assert(Math.abs(scales[0].x)<.001&&Math.abs(scales[2].x-38.4)<.001&&Math.abs(scales[4].x)<.001,'Lateral movement returns continuously to its starting point');
 const panBounds=await page.locator('.scene.visible .artwork').evaluate(async art=>{
  const animation=art.getAnimations()[0];animation.pause();const samples=[];
  for(const anchor of [0,28,50,100]){
   art.style.setProperty('--crop-x',anchor+'%');art.style.setProperty('--crop-y',(100-anchor)+'%');animation.currentTime=0;await new Promise(requestAnimationFrame);const base=art.getBoundingClientRect();
   for(const time of [0,7500,15000,22500,30000,45000,60000]){animation.currentTime=time;await new Promise(requestAnimationFrame);const box=art.getBoundingClientRect();samples.push({anchor,time,covers:box.left<=base.left+.01&&box.right>=base.right-.01&&box.top<=base.top+.01&&box.bottom>=base.bottom-.01});}
  }
  art.style.removeProperty('--crop-x');art.style.removeProperty('--crop-y');animation.currentTime=0;animation.play();return samples;
 });
 assert(panBounds.every(sample=>sample.covers),'Zoom and pan never uncover the original artwork frame, including extreme crop anchors');
 await page.waitForFunction(()=>document.querySelector('.scene.visible')?.game?.id==='steam:621',null,{timeout:11000});
 assert.equal(await page.locator('.scene.visible .artwork').evaluate(art=>art.getAnimations().length),0,'Fixed choice has no CSS animation');
 await page.waitForFunction(()=>document.querySelector('.scene.visible')?.game?.id==='steam:620',null,{timeout:11000});
 await page.evaluate(()=>window.SteamAnimatedScreensaverPlayer.setSettings({reducedMotion:true}));
 assert.equal(await page.locator('.scene.visible .artwork').evaluate(art=>art.getAnimations().length),0,'Reduce motion disables movement without replacing the image');
 assert.equal(await page.locator('#empty').isVisible(),false);assert.deepEqual(errors,[]);
 assert(!requests.some(name=>/\.(webm|gif|mp4)$/.test(name)),'No generated motion video loaded');
 const evidence={originalsPreserved:info.originals_preserved,scales,panBounds,naturalCycle:'gentle → fixed → gentle',fixedAnimationCount:0,reducedAnimationCount:0,videoRequests:0,pageErrors:errors,limitations:'Actual installer and browser playback; not SteamOS/GPU/physical controller proof.'};
 await fs.mkdir('out/ui/motion61',{recursive:true});await fs.writeFile('out/ui/motion61/evidence.json',JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
});
