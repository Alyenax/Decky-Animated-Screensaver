'use strict';
// Actual plugin player, original demo media, no SteamGridDB key or network.
// Capture is real time; the labelled bar is presentation-only, outside player.
const fs=require('node:fs/promises');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const reference=process.env.DAS_DEMO_REFERENCE||path.resolve(root,'../Steam-Animated-Screensaver');
const data=path.join(reference,'dist/public-launch-v2/live-data');
const player=path.join(root,'assets/player');
const work=path.join(root,'out/readme');
const output=path.join(root,'docs/media/screensaver-demo.gif');
const ffmpeg=process.env.DAS_TEST_FFMPEG||require(path.join(reference,'node_modules/ffmpeg-static'));
const ffprobe=process.env.DAS_TEST_FFPROBE||require(path.join(reference,'node_modules/ffprobe-static')).path;
const gifsicle=process.env.DAS_GIFSICLE||(()=>{try{const value=require('gifsicle');return value.default||value;}catch{throw Error('Set DAS_GIFSICLE to a Gifsicle 1.93+ binary for README compression.');}})();
const duration=16;

async function main(){
  await fs.mkdir(work,{recursive:true});await fs.mkdir(path.dirname(output),{recursive:true});
  const saved=JSON.parse(await fs.readFile(path.join(data,'catalog.json'),'utf8'));
  const files=new Map();const sources=[];
  const games=[];
  for(const number of [1245620,1091500]){
    const g=saved.games.find(g=>g.steamAppId===number);assert(g?.status==='ready');
    const mapped={id:'steam:'+number,name:g.name,included:true,status:'ready',crop:{mode:'inherit',x:50,y:50}};
    for(const role of ['media','cover']){
      const media=g[role];assert(media?.file && !media.file.includes('/') && !media.file.includes('..'));
      const file=path.join(data,'media',media.file),bytes=await fs.readFile(file);
      const sha256=crypto.createHash('sha256').update(bytes).digest('hex');assert.equal(sha256,media.sha256);
      const local='/media/'+media.file;files.set(local,{file,type:role==='cover'?'image/png':'image/webp'});
      mapped[role]={file:local,format:media.format,width:media.width,height:media.height,animated:role==='media',author:{name:media.author.name}};
      sources.push({game:g.name,role,author:media.author.name,sourceURL:media.sourceUrl,sha256,bytes:bytes.length});
      if(role==='media'){
        const thumbnail=path.join(data,'media',media.thumbnail),url='/media/'+media.thumbnail;
        assert(!media.thumbnail.includes('/') && !media.thumbnail.includes('..'));
        files.set(url,{file:thumbnail,type:'image/jpeg'});mapped.media.thumbnail=url;
      }
    }
    games.push(mapped);
  }
  const catalog={version:1,previewNonce:'readme-capture-only',games,settings:{framing:'original',shuffle:false,sceneDuration:180,
    showCover:true,showLogos:true,nameDisplay:'title',coverPosition:'beside-title',reducedMotion:false,transition:'crossfade',language:'en'}};
  const html=`<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#070f19;color:#f1f7ff;font-family:Arial,sans-serif}
    #presentation{opacity:0;display:grid;grid-template-rows:48px 1fr;height:100%}
    header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 18px;background:linear-gradient(110deg,#102332,#1b2035);border-top:4px solid #81e6ef;border-bottom:1px solid #334c61;position:relative;z-index:2}
    .brand{font-size:13px;font-weight:700;letter-spacing:1px;white-space:nowrap}.brand span{color:#81e6ef}.badge{font-size:12px;font-weight:700;letter-spacing:.6px;background:#183842;border:1px solid #47797e;border-radius:20px;padding:6px 12px;color:#c4fbff;white-space:nowrap}
    iframe{display:block;width:100%;height:100%;border:0;background:#05080d}
  </style></head><body><div id="presentation"><header><div class="brand"><span>DECKY</span> ANIMATED SCREENSAVER</div><div id="mode" class="badge">FULL IMAGE · NO CROP</div></header><iframe src="/player/index.html" title="Actual plugin player" allow="autoplay"></iframe></div></body></html>`;
  // A 48px header, including its stripe, leaves exactly 600px for the player.
  const server=http.createServer(async(req,res)=>{
    try{
      const pathname=new URL(req.url,'http://localhost').pathname;
      if(pathname==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
      if(pathname==='/player/catalog.js'){res.setHeader('Content-Type','text/javascript');res.end('window.SAS_CATALOG='+JSON.stringify(catalog)+';');return;}
      const code={'/player/index.html':['index.html','text/html'],'/player/player.js':['player.js','text/javascript'],'/player/player.css':['player.css','text/css']}[pathname];
      const item=code?{file:path.join(player,code[0]),type:code[1]}:files.get(pathname);
      if(!item){res.writeHead(404);res.end();return;}
      res.setHeader('Content-Type',item.type);res.end(await fs.readFile(item.file));
    }catch{res.writeHead(500);res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  // Prefer the Playwright-matched headless shell, not the independently updated
  // desktop Chrome whose recording viewport can differ from its screenshot.
  const browser=await chromium.launch({...(process.env.DAS_TEST_BROWSER?{executablePath:process.env.DAS_TEST_BROWSER}:{}),headless:true,args:['--autoplay-policy=no-user-gesture-required','--window-size=1280,900','--force-device-scale-factor=1']});
  const context=await browser.newContext({viewport:{width:960,height:648},recordVideo:{dir:work,size:{width:960,height:648}}});
  const page=await context.newPage();const errors=[],requests=[],segments=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>requests.push(request.url()));
  let video;
  try{
    await page.goto(origin);
    const frame=page.frames().find(f=>f.url().includes('/player/index.html'));assert(frame);
    await frame.waitForFunction(()=>document.querySelector('.scene.visible img.artwork')?.naturalWidth===1920);
    await frame.waitForFunction(()=>document.querySelector('.scene.visible .caption-cover')?.naturalWidth===600);
    await page.evaluate(()=>{document.querySelector('#presentation').style.opacity='1';window.__captureStarted=performance.now();});
    const mark=async(name,framing)=>{
      await frame.waitForFunction(({name,framing})=>{
        const scene=[...document.querySelectorAll('.scene.visible')].at(-1);
        return scene?.game?.name===name && scene.dataset.framing===framing && scene.querySelector('img.artwork')?.naturalWidth>0;
      },{name,framing});
      const metrics=await frame.evaluate(()=>{
        const scene=[...document.querySelectorAll('.scene.visible')].at(-1),art=scene.querySelector('.artwork'),box=scene.querySelector('.art-frame').getBoundingClientRect();
        return {game:scene.game.name,framing:scene.dataset.framing,source:[art.naturalWidth,art.naturalHeight],objectFit:getComputedStyle(art).objectFit,
          frame:{width:box.width,height:box.height},viewport:{width:innerWidth,height:innerHeight}};
      });
      assert.equal(metrics.viewport.width/metrics.viewport.height,16/10);
      assert.equal(metrics.objectFit,framing==='original'?'contain':'cover');
      if(framing==='16:10')assert(Math.abs(metrics.frame.width/metrics.frame.height-16/10)<1e-6);
      segments.push({...metrics,atSeconds:await page.evaluate(()=>(performance.now()-window.__captureStarted)/1000)});
    };
    const at=async(seconds)=>{const elapsed=await page.evaluate(()=>(performance.now()-window.__captureStarted)/1000);if(seconds>elapsed)await page.waitForTimeout((seconds-elapsed)*1000);};
    const mode=async(value)=>{
      await page.evaluate(value=>{document.querySelector('#mode').textContent=value==='original'?'FULL IMAGE · NO CROP':'16:10 · STEAM DECK';
        const iframe=document.querySelector('iframe');iframe.contentWindow.postMessage({type:'screensaver',action:'settings',settings:{framing:value},nonce:'readme-capture-only'},location.origin);},value);
    };
    const next=()=>page.evaluate(()=>document.querySelector('iframe').contentWindow.postMessage({type:'screensaver',action:'next',nonce:'readme-capture-only'},location.origin));
    await mark('ELDEN RING','original');await page.screenshot({path:path.join(work,'elden-full.png')});
    await at(3.6);await mode('16:10');await mark('ELDEN RING','16:10');await page.screenshot({path:path.join(work,'elden-16x10.png')});
    await at(7.2);await mode('original');await next();await mark('Cyberpunk 2077','original');
    await at(8.6);await page.screenshot({path:path.join(work,'cyberpunk-full.png')});
    await at(10.8);await mode('16:10');await mark('Cyberpunk 2077','16:10');await page.screenshot({path:path.join(work,'cyberpunk-16x10.png')});
    await at(14.4);await mode('original');await next();await mark('ELDEN RING','original');
    await at(duration+.2);assert.deepEqual(errors,[]);assert(requests.every(url=>url.startsWith(origin)));
    video=page.video();
  }finally{await context.close();await browser.close();await new Promise(resolve=>server.close(resolve));}
  const source=await video.path();
  const probe=file=>JSON.parse(execFileSync(ffprobe,['-v','error','-count_frames','-show_streams','-show_format','-of','json',file],{encoding:'utf8'}));
  const info=probe(source),rate=info.streams[0].avg_frame_rate.split('/').map(Number);const fps=rate[0]/rate[1];
  // Locate the first actually painted cyan stripe, not an estimated navigation
  // delay. The player is already decoded when that stripe becomes visible.
  const samples=execFileSync(ffmpeg,['-v','error','-i',source,'-vf','crop=2:2:2:0,scale=1:1,format=rgb24','-f','rawvideo','pipe:1'],{maxBuffer:1024*1024});
  let first=-1;for(let n=0;n<samples.length/3;n++){const r=samples[n*3],g=samples[n*3+1],b=samples[n*3+2];if(r>75&&r<185&&g>185&&b>190){first=n;break;}}
  assert(first>=0,'Presentation first frame not found');const offset=first/fps;
  assert(Number(info.format.duration)>=offset+duration-.08,'Recording truncated');
  // New headless Chrome can crop screencast output to its default physical
  // window and pad with grey, despite correct full-page screenshots. Reject
  // that capture rather than export a GIF with missing game titles.
  const bottom=execFileSync(ffmpeg,['-v','error','-ss',String(offset),'-i',source,'-t',String(duration),'-vf','fps=3,crop=2:2:2:ih-4,scale=1:1,format=rgb24','-f','rawvideo','pipe:1'],{maxBuffer:65536});
  assert([...bottom].every(channel=>channel<110),'Browser recording cropped/padded the lower player edge');
  const filters='fps=20,scale=800:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle';
  const unoptimized=path.join(work,'readme-unoptimized.gif');
  execFileSync(ffmpeg,['-v','error','-ss',String(offset),'-i',source,'-t',String(duration),'-filter_complex',filters,'-an','-loop','0','-y',unoptimized],{maxBuffer:2*1024*1024});
  execFileSync(gifsicle,['-O3','--lossy=100',unoptimized,'-o',output],{maxBuffer:2*1024*1024});
  execFileSync(ffmpeg,['-v','error','-i',output,'-f','null','-'],{maxBuffer:1024*1024});
  const result=probe(output),stream=result.streams[0];
  assert.equal(stream.width,800);assert.equal(stream.height,540);
  // Identical consecutive frames may merge during optimization; their delays
  // are retained. Check total playback time rather than require duplicates.
  assert(Number(stream.nb_read_frames)>=duration*20-6 && Number(stream.nb_read_frames)<=duration*20);
  assert(Math.abs(Number(result.format.duration)-duration)<.08);const bytes=(await fs.stat(output)).size;assert(bytes<8*1024*1024,'README GIF exceeds 8 MiB');
  const report={result:'passed',file:'docs/media/screensaver-demo.gif',width:stream.width,height:stream.height,frames:Number(stream.nb_read_frames),fps:20,durationSeconds:Number(result.format.duration),bytes,
    sha256:crypto.createHash('sha256').update(await fs.readFile(output)).digest('hex'),source:'Original cached artwork from the standalone README demo; actual Decky plugin player in Chromium',
    timing:'Real time. Export reduced to nominal 20fps; duplicate frames may merge with preserved delays. No playback acceleration or generated motion.',compression:'160-colour palette, no dithering, Gifsicle O3 lossy=100',presentation:'Label bar outside the player; player viewport exactly 960×600 (16:10). Not a physical SteamOS recording.',
    segments,sources,firstPaintFrame:first,recordedFPS:fps,videoOffset:offset,bottomEdgeValidated:true,networkRequests:'Loopback only; no API key or remote requests',errors};
  await fs.writeFile(path.join(work,'validation.json'),JSON.stringify(report,null,2)+'\n');
  await fs.writeFile(path.join(root,'docs/media/screensaver-demo.validation.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({file:report.file,width:report.width,height:report.height,frames:report.frames,durationSeconds:report.durationSeconds,bytes,sha256:report.sha256,segments:segments.map(s=>({game:s.game,framing:s.framing,viewport:s.viewport}))},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
