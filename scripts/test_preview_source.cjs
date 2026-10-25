// Real source Preview HTTP transport + same Steam player in Chromium.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require('playwright');
test('Installed snapshot plays actual original animation and branding after working edits', {timeout:60000},async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'das-installed-player-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const ffmpeg=process.env.DAS_TEST_FFMPEG;assert(ffmpeg);
 const source=path.join(root,'scene.gif');const encoded=spawnSync(ffmpeg,['-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=160x90:rate=8:duration=2','-y',source],{encoding:'utf8',timeout:10000});assert.equal(encoded.status,0,encoded.stderr);
 const code=`
import json,sys
from pathlib import Path
from das.core.catalog import file_sha256
from das.studio.service import StudioService
from das.studio.installer import Installer
from das.studio.preview import Preview
root=Path(sys.argv[1]);service=StudioService(root/'library',games_provider=lambda:[])
service.catalog.configure(dict(show_cover=False,name_display='title',shuffle=False,scene_seconds=12))
source=service.catalog.managed('prepared/source.gif');source.parent.mkdir();source.write_bytes(Path(sys.argv[2]).read_bytes());digest=file_sha256(source)
service.catalog.update(620,dict(name='Actually installed Portal',excluded=False,status='ready',animated=True,width=160,height=90,duration=2,
 media=dict(tv='prepared/source.gif',thumbnail='prepared/source.gif'),sha256=dict(tv=digest,thumbnail=digest),
 crop=dict(mode='16:10',x=20,y=70),branding=dict(mode='title',position='top-left')))
(root/'Steam').mkdir();installer=Installer(service.catalog,root/'Steam',sys.argv[3]);installer.install('fr')
service.catalog.update(620,dict(name='Not installed new choices',pending_change=True));service.catalog.configure(dict(name_display='hidden',scene_seconds=60))
before=service.catalog.path.read_bytes();preview=Preview(service.catalog,sys.argv[3],service)
try:
 result=preview.installed(installer,request_id='i'*32)
 assert service.catalog.path.read_bytes()==before
 print(json.dumps(result),flush=True);sys.stdin.readline()
finally:preview.close();service.shutdown()
`;
 const worker=spawn('python3',['-u','-c',code,root,source,path.resolve('assets/player')],{env:{...process.env,PYTHONPATH:path.resolve('py_modules'),PYTHONPYCACHEPREFIX:'/private/tmp/das36-preview-pycache'},stdio:['pipe','pipe','pipe']});t.after(()=>worker.kill());let stderr='';worker.stderr.on('data',b=>stderr+=b);
 const result=await new Promise((resolve,reject)=>{createInterface({input:worker.stdout}).once('line',line=>{try{resolve(JSON.parse(line));}catch(e){reject(e);}});worker.once('exit',code=>{if(code)reject(Error(stderr));});setTimeout(()=>reject(Error('Snapshot timeout '+stderr)),30000).unref();});
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});t.after(()=>browser.close());
 const page=await browser.newPage({viewport:{width:640,height:360}});const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:'))external.push(r.url());});
 await page.goto(result.url);await page.waitForFunction(()=>[...document.images].some(i=>i.complete&&i.naturalWidth===160));
 await page.getByText('Actually installed Portal',{exact:true}).waitFor();assert.equal(await page.getByText('Not installed new choices',{exact:true}).count(),0);
 await page.waitForTimeout(250);const first=await page.screenshot();await page.waitForTimeout(370);assert.notDeepEqual(await page.screenshot(),first,'installed GIF must visibly move');assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 await fs.mkdir('out/ui/preview-source',{recursive:true});await page.screenshot({path:'out/ui/preview-source/actual-installed-snapshot.png'});
 worker.stdin.end('\n');await new Promise(resolve=>worker.once('exit',resolve));console.log('PASS actual installed snapshot player: old title and original moving GIF, working edits untouched, no external or hardware request. Not SteamOS/hardware proof.');
});
test('Unprepared animated GIF: bounded inspected source -> actual loopback player -> moving frames and exact branding', {timeout:60000},async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'das-source-preview-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const ffmpeg=process.env.DAS_TEST_FFMPEG,probe=process.env.DAS_TEST_FFPROBE;assert(ffmpeg&&probe);
 const source=path.join(root,'scene.gif');
 const encoded=spawnSync(ffmpeg,['-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=160x90:rate=8:duration=2','-y',source],{encoding:'utf8',timeout:10000});
 assert.equal(encoded.status,0,encoded.stderr);
 const code=`
import json,sys
from pathlib import Path
from das.studio.service import StudioService
from das.studio.preview import Preview
from das.studio.media import Media
media=Media(ffmpeg=sys.argv[3]);media._probe=sys.argv[4]
service=StudioService(Path(sys.argv[1])/'library',media=media,games_provider=lambda:[])
service.catalog.configure(dict(show_cover=False,name_display='title',shuffle=False))
service.catalog.update(620,dict(name='Unprepared Portal',excluded=False,status='pending'))
source=service.catalog.managed('sources/source.gif');source.parent.mkdir();source.write_bytes(Path(sys.argv[2]).read_bytes())
service._download=lambda asset,**kw:source
service._assets=lambda *args:[]
preview=Preview(service.catalog,sys.argv[5],service)
before=service.catalog.path.read_bytes()
try:
 result=preview.open(620,dict(asset=dict(id=1,url='https://cdn.steamgriddb.com/fixture.gif',animated=True,width=160,height=90),crop=dict(mode='16:10',x=15,y=80),branding=dict(mode='title',position='top-left')),artwork_only=True)
 assert service.catalog.path.read_bytes()==before
 print(json.dumps(result),flush=True)
 sys.stdin.readline()
finally:preview.close();service.shutdown()
`;
 const worker=spawn('python3',['-u','-c',code,root,source,ffmpeg,probe,path.resolve('assets/player')],{env:{...process.env,PYTHONPATH:path.resolve('py_modules'),PYTHONPYCACHEPREFIX:'/private/tmp/das-preview-pycache'},stdio:['pipe','pipe','pipe']});
 t.after(()=>worker.kill());let stderr='';worker.stderr.on('data',b=>stderr+=b);
 const info=await new Promise((resolve,reject)=>{const lines=createInterface({input:worker.stdout});lines.once('line',line=>{try{resolve(JSON.parse(line));}catch(e){reject(e);}});worker.once('exit',code=>{if(code)reject(new Error(stderr));});setTimeout(()=>reject(new Error('Preview startup timeout '+stderr)),35000).unref();});
 const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});t.after(()=>browser.close());
 const page=await browser.newPage({viewport:{width:640,height:360}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(info.url);await page.waitForFunction(()=>[...document.images].some(i=>i.complete&&i.naturalWidth===160));
 await page.waitForTimeout(600);const first=await page.screenshot();await page.waitForTimeout(370);const second=await page.screenshot();assert.notDeepEqual(first,second,'GIF frames must visibly advance');
 assert.equal(await page.locator('#stage').getByText('Unprepared Portal',{exact:true}).count(),1);assert.deepEqual(errors,[]);
 const checks=await page.evaluate(()=>({imgs:[...document.images].map(i=>({width:i.naturalWidth,height:i.naturalHeight})),overflow:document.documentElement.scrollWidth>innerWidth}));assert.equal(checks.overflow,false);
 await fs.mkdir('out/ui/preview-source',{recursive:true});await page.screenshot({path:'out/ui/preview-source/actual-source-gif.png'});
 const secure=await browser.newPage({viewport:{width:640,height:360}});
 // CDP-fulfilled HTTPS has no real local-IP classification, unlike Steam's
 // actual loopback host. Same test-only grant as test_player.cjs; not shipped.
 await secure.context().grantPermissions(['local-network-access'],{origin:'https://steamloopback.host'});
 await secure.route('https://steamloopback.host/preview-source-test',r=>r.fulfill({status:200,contentType:'text/html',body:`<style>body{margin:0;background:black}img{width:640px;height:360px;object-fit:contain}</style><img src="${info.source_url}">`}));
 await secure.goto('https://steamloopback.host/preview-source-test');await secure.waitForFunction(()=>document.images[0]?.naturalWidth===160);
 const rawFirst=await secure.screenshot();await secure.waitForTimeout(370);const rawSecond=await secure.screenshot();assert.notDeepEqual(rawFirst,rawSecond,'native candidate GIF must animate under the secure Steam origin');await secure.close();
 worker.stdin.end('\n');await new Promise(resolve=>worker.once('exit',resolve));
 console.log('PASS real source GIF frames change in shared player and raw candidate under secure Steam origin; branding; no preparation or catalog mutation. Not SteamOS/hardware evidence.');
});
