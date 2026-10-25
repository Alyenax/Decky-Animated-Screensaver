// Real codecs + backend source fallback + local transport + Chromium.
// Originals are generated locally; no API key or hardware is used.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require('playwright');
test('Broken thumbnails and >32MiB animated WebP -> bounded still/motion with real moving pixels', {timeout:120000},async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'das-candidate-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const ffmpeg=process.env.DAS_TEST_FFMPEG,probe=process.env.DAS_TEST_FFPROBE;assert(ffmpeg&&probe);
 for(const [name,extra] of [['scene.gif',[]],['scene.webp',['-c:v','libwebp_anim','-loop','0']]]){
  const result=spawnSync(ffmpeg,['-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=8:duration=9',...extra,'-y',path.join(root,name)],{encoding:'utf8',timeout:20000});assert.equal(result.status,0,result.stderr);
 }
 const code=`
import json,sys,struct
from pathlib import Path
from das.studio.service import StudioService
from das.studio.preview import Preview
from das.studio.media import Media,webp_info
root=Path(sys.argv[1]);media=Media(ffmpeg=sys.argv[2]);media._probe=sys.argv[3]
service=StudioService(root/'library',media=media,games_provider=lambda:[])
preview=Preview(service.catalog,sys.argv[4],service)
service.catalog.update(620,dict(name='Portal'))
before=service.catalog.path.read_bytes()
sources=service.catalog.managed('sources');sources.mkdir()
raw=(root/'scene.webp').read_bytes();large=sources/'large.webp'
# Valid RIFF metadata padding. 33MiB original, but the gallery discards metadata.
with large.open('wb') as stream:
 stream.write(b'RIFF'+struct.pack('<I',len(raw)-8+8+33*1024*1024)+b'WEBP')
 stream.write(raw[12:]);stream.write(b'EXIF'+struct.pack('<I',33*1024*1024))
 for _ in range(33):stream.write(b'X'*(1024*1024))
gif=sources/'scene.gif';gif.write_bytes((root/'scene.gif').read_bytes())
requests=[]
def download(asset,**kw):
 requests.append(dict(thumbnail=kw.get('thumbnail'),maximum=kw['maximum']))
 if kw.get('thumbnail'):raise OSError('Broken remote thumbnail fixture')
 assert kw['maximum']==128*1024*1024
 return large if asset['id']==1 else gif
service._download=download
service._candidates[(620,'animation')]=[dict(id=n,url='https://cdn.steamgriddb.com/'+str(n)+'.webp',thumb='https://cdn.steamgriddb.com/thumb/broken.webp',animated=True,width=320,height=180) for n in (1,2)]
try:
 still=preview.candidate(620,'animation',1,request_id='s'*32)
 motion=preview.candidate(620,'animation',1,True,'m'*32)
 native=next(service.catalog.managed('candidate-previews-v1').glob('*.webp'))
 info=webp_info(native)
 assert info['duration']<=6.2 and info['frames']<=72
 assert native.stat().st_size<8*1024*1024 and large.stat().st_size>32*1024*1024
 assert service.catalog.path.read_bytes()==before
 print(json.dumps(dict(still=still,motion=motion,original_bytes=large.stat().st_size,preview_bytes=native.stat().st_size,frames=info['frames'],seconds=info['duration'])),flush=True)
 sys.stdin.readline()
 motion2=preview.candidate(620,'animation',2,True,'g'*32)
 print(json.dumps(motion2),flush=True)
 sys.stdin.readline()
finally:preview.close();service.shutdown()
`;
 const worker=spawn('python3',['-u','-c',code,root,ffmpeg,probe,path.resolve('assets/player')],{env:{...process.env,PYTHONPATH:path.resolve('py_modules'),PYTHONPYCACHEPREFIX:'/private/tmp/das35-pycache'},stdio:['pipe','pipe','pipe']});t.after(()=>worker.kill());
 let stderr='';worker.stderr.on('data',b=>stderr+=b);const lines=createInterface({input:worker.stdout});const values=[],waiters=[];lines.on('line',line=>{const value=JSON.parse(line);if(waiters.length)waiters.shift()(value);else values.push(value);});
 const next=()=>new Promise((resolve,reject)=>{if(values.length)return resolve(values.shift());waiters.push(resolve);const timer=setTimeout(()=>reject(Error('Worker timeout '+stderr)),50000);timer.unref();worker.once('exit',code=>{if(code)reject(Error(stderr));});});
 const result=await next();const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});t.after(()=>browser.close());
 const page=await browser.newPage({viewport:{width:640,height:360}});
 // Test-only grant for the CDP-fulfilled HTTPS origin, as in the shared-player
 // suite. It is not shipped and does not bypass production Steam permissions.
 await page.context().grantPermissions(['local-network-access'],{origin:'https://steamloopback.host'});
 await page.route('https://steamloopback.host/candidate-test',r=>r.fulfill({contentType:'text/html',body:`<img src="${result.motion.source_url}">`}));
 await page.goto('https://steamloopback.host/candidate-test');await page.waitForFunction(()=>document.images[0]?.naturalWidth===320);
 const first=await page.screenshot();await page.waitForTimeout(450);assert.notDeepEqual(await page.screenshot(),first,'WebP prefix must visibly animate');
 await page.setContent(`<img src="${result.still.still}">`);await page.waitForFunction(()=>document.images[0]?.naturalWidth===320);const still=await page.screenshot();await page.waitForTimeout(450);assert.deepEqual(await page.screenshot(),still,'JPEG must remain fixed');
 worker.stdin.write('\n');const gif=await next();assert.equal(gif.source_format,'webm');
 await page.goto(gif.source_url);await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2);await page.locator('video').evaluate(v=>{v.muted=true;return v.play();});const a=await page.screenshot();await page.waitForTimeout(450);assert.notDeepEqual(await page.screenshot(),a,'GIF proxy WebM must visibly animate');
 worker.stdin.end('\n');await new Promise(resolve=>worker.once('exit',resolve));console.log('PASS real codec candidate previews '+JSON.stringify({original_bytes:result.original_bytes,preview_bytes:result.preview_bytes,frames:result.frames,seconds:result.seconds})+'; broken-thumb fallback, fixed JPEG, animated WebP and GIF->WebM. Not SteamOS/hardware.');
});
