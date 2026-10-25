"use strict";
// Real still -> production encoder -> installed player. No Steam/USB authority.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const http=require('node:http');
const {spawnSync}=require('node:child_process');
const {chromium}=require('playwright');

test('Recipe 4 installed player: real VP9, gentle motion, complete loop and no premature stop', {timeout:100000},async t=>{
 const ffmpeg=process.env.DAS_TEST_FFMPEG,probe=process.env.DAS_TEST_FFPROBE;
 assert(ffmpeg&&probe,'Supply isolated codec tools explicitly');
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'das-gentle39-'));
 t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const code=`
import json,sys,shutil
from pathlib import Path
from PIL import Image,ImageDraw
from das.core.catalog import file_sha256
from das.studio.media import Media,still_motion_spec
from das.studio.storage import Store
from das.studio.installer import Installer
root=Path(sys.argv[1]);store=Store(root/'studio')
source=store.managed('media/original.png');source.parent.mkdir()
if sys.argv[5]:shutil.copyfile(sys.argv[5],source)
else:
 image=Image.new('RGB',(320,200),'#284452');draw=ImageDraw.Draw(image)
 for x in range(0,320,20):draw.rectangle((x,0,x+8,199),fill=(120+x//3,48,90))
 image.save(source)
original=file_sha256(source)
store.configure(dict(scene_seconds=60,show_cover=False,show_logo=False,name_display='hidden',shuffle=False,static_fallback=True))
media=Media(sys.argv[2]);media._probe=sys.argv[3]
result=media.animate_still(source,store.managed('prepared'),store.options(),lambda:None,lambda *_:None)
files=dict(tv='media/original.png',thumbnail='media/original.png',still_motion=str(result['tv'].relative_to(store.root)))
store.update(620,dict(name='Gentle motion fixture',status='ready',animated=False,format='png',excluded=False,still_mode='motion',
 media=files,sha256={k:file_sha256(store.managed(v,True)) for k,v in files.items()},
 still_motion_config=still_motion_spec(store.options()),still_motion_info={k:result[k] for k in ('width','height','duration')}))
steam=root/'Steam';steam.mkdir();installer=Installer(store,steam,sys.argv[4]);installer.install()
assert file_sha256(source)==original
print(json.dumps(dict(destination=str(installer.destination),duration=result['duration'],frames=result['frames'])))
`;
 const built=spawnSync(process.env.DAS_TEST_PYTHON||'python3',['-c',code,root,ffmpeg,probe,path.resolve('assets/player'),process.env.DAS_TEST_STILL_SOURCE||''],{
  env:{...process.env,PYTHONPATH:path.resolve('py_modules'),PYTHONPYCACHEPREFIX:'/private/tmp/das-gentle39-pycache'},encoding:'utf8',timeout:45000});
 assert.equal(built.status,0,built.stderr);
 const info=JSON.parse(built.stdout);assert.equal(info.duration,40);assert.equal(info.frames,1200);
 const server=http.createServer(async(req,res)=>{try{
  const file=path.resolve(info.destination,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(!file.startsWith(info.destination+path.sep)){res.writeHead(404);res.end();return;}
  const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.webm':'video/webm','.png':'image/png','.jpg':'image/jpeg'}[path.extname(file)];
  if(!mime){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',mime);res.end(await fs.readFile(file));
 }catch{res.writeHead(404);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 t.after(()=>{server.closeAllConnections();return new Promise(resolve=>server.close(resolve));});
 const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,
  args:['--autoplay-policy=no-user-gesture-required']});t.after(()=>browser.close());
 const page=await browser.newPage({viewport:{width:1280,height:720}});const errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 const origin='http://127.0.0.1:'+server.address().port;await page.goto(origin+'/index.html');
 await page.waitForFunction(()=>{const v=document.querySelector('.scene.visible video.artwork');return v&&!v.paused&&v.currentTime>1;});
 await page.evaluate(()=>{const v=document.querySelector('.scene.visible video.artwork');window.__gentle={loops:0,last:v.currentTime};
  v.addEventListener('timeupdate',()=>{if(v.currentTime+1<window.__gentle.last)window.__gentle.loops++;window.__gentle.last=v.currentTime;});});
 const first=await page.locator('#stage').screenshot();await page.waitForTimeout(2000);
 assert.notDeepEqual(await page.locator('#stage').screenshot(),first,'zoom/pan must remain visible');
 await page.waitForFunction(()=>window.__gentle.loops>=1,{},{timeout:44000});
 const state=await page.evaluate(()=>{const v=document.querySelector('.scene.visible video.artwork');return {duration:v.duration,time:v.currentTime,paused:v.paused,error:v.error?.code||0,loops:window.__gentle.loops,hidden:document.hidden};});
 assert.equal(state.duration,40);assert.equal(state.paused,false);assert.equal(state.error,0);assert.equal(state.hidden,false);
 assert.deepEqual(errors,[]);assert(requests.every(url=>url.startsWith(origin+'/')),'No remote/USB/relay request');
 console.log('PASS real still -> 1200-frame/40s VP9 -> actual installed shared player, visible motion and natural loop:',JSON.stringify(state));
 console.log('Browser/codec evidence only; not a SteamOS/GPU or physical faceplate acceptance test.');
});
