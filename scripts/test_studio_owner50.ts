/** Real secure-origin installed player -> GCA. DAS backend already shut down. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync,existsSync,mkdtempSync,rmSync} from 'node:fs';
import {createServer} from 'node:https';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),{chromium}=require('playwright');
const executable=process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const HOST='decky-animated-screensaver.steamloopback.host';
const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=','base64');
for(const mode of ['sync','async'])test(`${mode}: actual installed browser plays with DAS off, then GCA owns two hours`,
 {skip:!process.env.DAS_TEST_GCA_ROOT||!existsSync(executable),timeout:45000},async()=>{
 const worker=spawn('python3',['tests/backend/studio_owner50_worker.py'],{env:{...process.env,DAS_TEST_MODE:mode},stdio:['pipe','pipe','pipe']});
 let stderr='',serial=0,browser:any,server:any,tls:string|undefined;
 const waiting=new Map<number,{resolve:(v:any)=>void,reject:(e:any)=>void}>();
 worker.stderr.on('data',b=>stderr+=b.toString());
 const setup=new Promise<any>((resolve,reject)=>{
  createInterface({input:worker.stdout}).on('line',raw=>{const x=JSON.parse(raw);if(x.setup)resolve(x);else{const p=waiting.get(x.id);waiting.delete(x.id);x.error?p?.reject(x.error):p?.resolve(x.result);}});
  worker.on('exit',code=>{if(code){reject(Error(stderr));for(const p of waiting.values())p.reject(Error(stderr));}});
 });
 const rpc=(data:any)=>new Promise<any>((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});worker.stdin.write(JSON.stringify({id,...data})+'\n');});
 try{
  const config=await setup;assert.equal(config.catalog.jsaux.controller,'GabeCubeAura');
  assert.equal(config.catalog.jsaux.relay.url,'http://127.0.0.1:37680/jsaux/v1/player');
  tls=mkdtempSync('/private/tmp/das50-tls-');
  execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN='+HOST,'-keyout',path.join(tls,'key.pem'),'-out',path.join(tls,'cert.pem')],{stdio:'ignore'});
  server=createServer({key:readFileSync(path.join(tls,'key.pem')),cert:readFileSync(path.join(tls,'cert.pem'))},(req,res)=>{
   const pathname=new URL(req.url||'/','https://'+HOST).pathname,leaf=path.basename(pathname);
   if(pathname.includes('/media/')){res.setHeader('Content-Type','image/png');res.end(image);return;}
   if(leaf==='catalog.js'){res.setHeader('Content-Type','text/javascript');res.end('window.SAS_CATALOG='+JSON.stringify(config.catalog));return;}
   if(leaf==='index.html'){res.setHeader('Content-Type','text/html');res.end(config.player_html);return;}
   if(leaf==='diagnostic-config.js'){res.setHeader('Content-Type','text/javascript');res.end(config.diagnostic_config);return;}
   if(['player.js','player.css','diagnostic.js'].includes(leaf)){res.setHeader('Content-Type',leaf.endsWith('.js')?'text/javascript':'text/css');res.end(readFileSync('assets/player/'+leaf));return;}
   res.statusCode=404;res.end();
  });
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  browser=await chromium.launch({executablePath:executable,headless:true,args:['--no-proxy-server','--host-resolver-rules=MAP '+HOST+' 127.0.0.1:'+server.address().port]});
  const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[],calls:any[]=[];
  page.on('pageerror',(e:Error)=>errors.push(e.message));
  page.on('request',(r:any)=>{if(r.url().startsWith('http://127.0.0.1:37680/'))calls.push(r.postDataJSON());});
  await page.goto('https://'+HOST+'/index.html');
  await page.waitForFunction(()=>(window as any).DAS_PLAYER_DEBUG?.snapshot().events.some((e:any)=>e.event==='gca-handoff'),{},{timeout:12000}).catch(async(e:Error)=>{
   throw Error(e.message+JSON.stringify({errors,calls,debug:await page.evaluate(()=>(window as any).DAS_PLAYER_DEBUG?.snapshot()),broker:await rpc({report:true})}));
  });
  assert.equal(await page.locator('.scene.visible').count(),1);assert.deepEqual(errors,[]);
  const initial=await rpc({report:true});assert(initial.runtime.steam_owned);assert.equal(initial.state.phase,'active');
  await new Promise(r=>setTimeout(r,9000));
  const report=await rpc({hours:true});assert(report.runtime.steam_owned);assert.equal(report.state.phase,'active');
  assert.equal(calls.filter(p=>p.event==='open').length,1);assert.equal(calls.filter(p=>p.event==='ready').length,1);assert.equal(calls.filter(p=>p.event==='started').length,1);
  assert.equal(report.commands.filter((c:any)=>c[0]==='submit').length,1);
  const count=calls.length;await page.waitForTimeout(2200);assert.equal(calls.length,count);
  const exit=await rpc({exit:true});assert.equal(exit.runtime.steam_owned,false);assert.equal(exit.state.phase,'idle');
  assert.equal(exit.commands.filter((c:any)=>c[0]==='restore').length,1);
 }finally{
  await browser?.close();if(server)await new Promise<void>(r=>server.close(()=>r()));
  worker.stdin.end();await new Promise<void>(r=>worker.exitCode!==null?r():worker.once('exit',()=>r()));
  if(tls)rmSync(tls,{recursive:true,force:true});
 }
});
