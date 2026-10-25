/** Real secure-origin Chrome -> actual loopback HTTP -> DAS -> GCA broker.
 * Native Steam Storage is deliberately broken; physical USB is simulated. */
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
const ORIGIN='https://decky-animated-screensaver.steamloopback.host';
const STEAM_HOST='uioverride-decky-animated-screensaver.steamscreensavers.host';
const STEAM_ALIAS='decky-animated-screensaver.steamscreensavers.host';
const FOREIGN_HOST='other-plugin.steamscreensavers.host';
const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=','base64');

for(const scenario of process.env.DAS_TEST_EXIT_SOAK?['exit-soak']:['sync','async','steam-screensaver-sync','steam-screensaver-async','steam-screensaver-alias','foreign-screensaver','invalid-presentation','json-blocked','runtime-error','catalog-error','all-network-blocked','csp-blocked','path-refused'])test(`Secure-origin installed ${scenario}: actual player, isolated diagnostics and safe fallback`,
  {skip:!process.env.DAS_TEST_GCA_ROOT||!process.env.DAS_TEST_FFMPEG||!existsSync(executable),timeout:scenario==='exit-soak'?180000:40000},async()=>{
  const mode=scenario.endsWith('async')?'async':'sync',fault=!['sync','async','steam-screensaver-sync','steam-screensaver-async','steam-screensaver-alias','exit-soak'].includes(scenario);
  const worker=spawn('python3',['tests/backend/jsaux_e2e_worker.py'],{env:{...process.env,DAS_TEST_MODE:mode,DAS_TEST_GAME_COUNT:scenario==='exit-soak'?'24':'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let stderr='',serial=0;const waiting=new Map<number,{resolve:(x:any)=>void,reject:(x:any)=>void}>();
  worker.stderr.on('data',b=>stderr+=b.toString());
  const setup=new Promise<any>((resolve,reject)=>{
    const lines=createInterface({input:worker.stdout});
    lines.on('line',raw=>{const x=JSON.parse(raw);if(x.setup)resolve(x);else{const p=waiting.get(x.id);waiting.delete(x.id);if(x.error)p?.reject(x.error);else p?.resolve(x.result);}});
    worker.on('exit',code=>{if(code){reject(new Error(stderr));for(const p of waiting.values())p.reject(new Error(stderr));}});
  });
  const rpc=(payload:any)=>new Promise<any>((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});worker.stdin.write(JSON.stringify({id,...payload})+'\n');});
  let browser:any,httpsServer:any,tlsDir:string|undefined;
  try{
    const {catalog,player_html,diagnostic_config,fixture_media}=await setup;
    if(scenario==='invalid-presentation')catalog.presentation.order=[];
    assert.equal(catalog.jsaux.relay.kind,'http-loopback-v1');
    assert(player_html.includes('connect-src '+catalog.jsaux.relay.url+' '));
    // Real loopback TLS, not route.fulfill: an intercepted mock document has an
    // unknown/public IP address space and cannot model Steam's loopback origin.
    // Only this temporary fixture certificate is ignored; no CORS/LNA flags.
    tlsDir=mkdtempSync('/private/tmp/das15-test-tls-');
    execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=decky-animated-screensaver.steamloopback.host',
      '-keyout',path.join(tlsDir,'key.pem'),'-out',path.join(tlsDir,'cert.pem')],{stdio:'ignore'});
    httpsServer=createServer({key:readFileSync(path.join(tlsDir,'key.pem')),cert:readFileSync(path.join(tlsDir,'cert.pem'))},(req,res)=>{
      const pathname=new URL(req.url||'/',ORIGIN).pathname,leaf=path.basename(pathname);
      if(pathname.includes('/media/')){res.setHeader('Content-Type',scenario==='exit-soak'?'image/gif':'image/png');res.end(scenario==='exit-soak'?Buffer.from(fixture_media,'base64'):image);return;}
      if(leaf==='catalog.js'){res.setHeader('Content-Type','text/javascript');res.end(scenario==='catalog-error'?'function {':'window.SAS_CATALOG='+JSON.stringify(catalog));return;}
      if(leaf==='diagnostic-config.js'){res.setHeader('Content-Type','text/javascript');res.end(diagnostic_config);return;}
      if(leaf==='player.js'&&scenario==='runtime-error'){res.setHeader('Content-Type','text/javascript');res.end('function {');return;}
      if(leaf==='index.html'){res.setHeader('Content-Type','text/html');res.end(scenario==='csp-blocked'?player_html.replace(/connect-src [^;]+;/,"connect-src 'none';"):player_html);return;}
      if(['player.js','player.css','diagnostic.js'].includes(leaf)){res.setHeader('Content-Type',leaf.endsWith('.js')?'text/javascript':'text/css');res.end(readFileSync('assets/player/'+leaf));return;}
      res.statusCode=404;res.end();
    });
    await new Promise<void>(resolve=>httpsServer.listen(0,'127.0.0.1',resolve));
    const hosts=['decky-animated-screensaver.steamloopback.host','steamloopback.host',STEAM_HOST,STEAM_ALIAS,FOREIGN_HOST];
    browser=await chromium.launch({executablePath:executable,headless:true,args:['--no-proxy-server','--host-resolver-rules='+hosts.map(host=>`MAP ${host} 127.0.0.1:${httpsServer.address().port}`).join(', ')]});
    const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[],messages:string[]=[];page.on('pageerror',(e:any)=>errors.push(e.message));
    page.on('console',(m:any)=>{if(m.type()==='error')messages.push(m.text());});
    const debugConsole:string[]=[];page.on('console',(m:any)=>{if(m.text().startsWith('[DAS-JSAUX-DEBUG]'))debugConsole.push(m.text());});
    page.on('requestfailed',(r:any)=>messages.push(r.failure()?.errorText||'REQUEST_FAILED'));
    if(scenario==='json-blocked')await page.route('http://127.0.0.1:37679/jsaux/v1/player',r=>r.abort('blockedbyclient'));
    if(scenario==='all-network-blocked')await page.route('http://127.0.0.1:37679/**',r=>r.abort('blockedbyclient'));
    await page.addInitScript(()=>{(window as any).__nativeReads=0;(window as any).__nativeWrites=0;
      (window as any).SteamClient={Storage:{GetString(){(window as any).__nativeReads++;throw Error('Fixture native read rejected');},SetString(){(window as any).__nativeWrites++;throw Error('Fixture native write rejected');}}};});
    const host=scenario==='foreign-screensaver'?FOREIGN_HOST:scenario==='steam-screensaver-alias'?STEAM_ALIAS:scenario.startsWith('steam-screensaver-')?STEAM_HOST:'decky-animated-screensaver.steamloopback.host';
    await page.goto(scenario==='path-refused'?'https://steamloopback.host/unexpected/index.html':`https://${host}/index.html`);
    if(fault){
      await sleep(1200);const report=await rpc({report:true});
      const local=await page.evaluate(()=>(window as any).DAS_PLAYER_DEBUG.snapshot());
      assert.equal(report.commands.filter((x:any)=>x[0]==='submit').length,0,JSON.stringify(report));
      assert(debugConsole.length>0);assert(!debugConsole.join('').includes(catalog.bridge_token));
      if(['all-network-blocked','csp-blocked'].includes(scenario)){
        assert.equal(report.jsaux.player_relay.diagnostic_accepted,0);assert.equal(report.jsaux.player_relay.requests,0);
        assert(local.events.some((e:any)=>e.event==='request-failed'));assert(debugConsole.some(x=>x.includes('diagnostic-failed')));
        if(scenario==='csp-blocked')assert(local.events.some((e:any)=>e.event==='csp-violation'&&e.resource==='loopback-player'));
      }else if(scenario==='foreign-screensaver'){
        assert.equal(report.jsaux.player_relay.diagnostic_accepted,0);assert.equal(report.jsaux.player_relay.requests,0);
        assert(local.events.some((e:any)=>e.event==='lifecycle-disabled'&&e.reason==='origin-refused'));
        assert(report.delivery.player_debug.http.some((e:any)=>e.reason==='ORIGIN_REFUSED'&&e.origin.category==='screensaver-other'));
        assert(!JSON.stringify(report.delivery).includes(FOREIGN_HOST));
      }else{
        assert(report.jsaux.player_relay.diagnostic_accepted>0,JSON.stringify({report,local,errors,messages}));
        const received=report.delivery.player_debug.browser.runs.at(-1).events;
        const expected=['invalid-presentation','path-refused'].includes(scenario)?'lifecycle-disabled':scenario==='json-blocked'?'request-failed':'js-error';
        assert(received.some((e:any)=>e.event===expected),JSON.stringify(received));
        if(scenario==='invalid-presentation')assert(received.some((e:any)=>e.reason==='presentation-invalid'));
        if(scenario==='runtime-error')assert(received.some((e:any)=>e.resource==='runtime'));
        if(scenario==='catalog-error')assert(received.some((e:any)=>e.resource==='catalog'));
        if(scenario==='path-refused')assert(received.some((e:any)=>e.reason==='origin-refused'&&e.flags.origin_valid===true&&e.flags.path_expected===false));
      }
      return;
    }
    let report:any;
    for(let n=0;n<200;n++){
      report=await rpc({report:true});
      if(report.jsaux.phase==='active')break;
      await sleep(50);
    }
    await page.waitForFunction(()=>document.querySelectorAll('.scene.visible').length===1,{},{timeout:2500});
    const evidence=await page.evaluate(()=>({transport:(window as any).DAS_JSAUX_TRANSPORT,reads:(window as any).__nativeReads,writes:(window as any).__nativeWrites,visible:document.querySelectorAll('.scene.visible').length}));
    assert.equal(report.jsaux.phase,'active',JSON.stringify({report,evidence,errors,messages}));
    assert.equal(evidence.transport.kind,'http-loopback-v1');assert.equal(evidence.reads,0);assert.equal(evidence.writes,0);
    assert.equal(evidence.visible,1);assert.deepEqual(errors,[]);
    assert.equal(report.commands.filter((x:any)=>x[0]==='submit').length,1);
    if(mode==='sync'){
      assert.equal(report.delivery.calibration.last.reference_basis,'broker-confirmation-event');
      assert(report.delivery.calibration.last.uncertainty_ms<=26);
      assert.equal(report.delivery.calibration.last.optical,'not-measured');
    }
    assert(report.jsaux.player_relay.requests>=(mode==='sync'?7:3));assert.equal(report.jsaux.player_relay.errors,0);
    for(let n=0;n<50;n++){report=await rpc({report:true});if(report.jsaux.player_relay.diagnostic_accepted>0&&report.delivery.player_debug.browser.runs.at(-1)?.events.some((e:any)=>e.event==='tv-start'))break;await sleep(50);}
    assert(report.jsaux.player_relay.diagnostic_accepted>0);
    assert(report.delivery.player_debug.browser.runs.at(-1).events.some((e:any)=>e.event==='tv-start'));
    if(scenario.startsWith('steam-screensaver-')){
      assert(report.delivery.player_debug.browser.runs.at(-1).events.some((e:any)=>e.event==='boot'&&e.reason==='screensaver-host'));
      assert(report.delivery.player_debug.http.some((e:any)=>e.stage==='http-received'&&e.origin?.category==='screensaver-plugin'&&e.origin.allowed===true));
    }
    assert(!JSON.stringify(report.delivery).includes(catalog.bridge_token));
    if(scenario==='exit-soak'){
      const began=Date.now();
      for(const mark of [30000,90000,121000,130000]){
        await sleep(Math.max(0,mark-(Date.now()-began)));
        await page.evaluate(()=>{(window as any).DAS_PLAYER_DEBUG.flush();});
        report=await rpc({report:true});
        assert.equal(report.jsaux.phase,'active',JSON.stringify(report));
        assert.equal(report.commands.filter((x:any)=>x[0]==='submit').length,1);
        assert.equal(report.commands.filter((x:any)=>x[0]==='restore').length,0);
        assert.equal(await page.locator('.scene.visible').count(),1);
        assert(await page.locator('.scene').count()<=3);
        const state=await page.evaluate(()=>(window as any).DAS_PLAYER_DEBUG.snapshot());
        assert(state.events.some((e:any)=>e.ms>=mark-15000),JSON.stringify(state));
        assert(JSON.stringify(state).length<14000);
        console.log('soak checkpoint',mark,'ms: active, one simulated upload, rolling trace retained');
      }
      await rpc({steam_inactive:true});
      for(let n=0;n<80;n++){
        await sleep(50);report=await rpc({report:true});
        if(report.delivery.player_debug.browser.runs.at(-1)?.events.some((e:any)=>e.event==='broker-refused'&&e.reason==='STEAM_INACTIVE'))break;
      }
      const terminal=report.delivery.player_debug.browser.runs.at(-1).events;
      assert(terminal.some((e:any)=>e.event==='broker-refused'&&e.reason==='STEAM_INACTIVE'&&e.ms>120000),JSON.stringify(report));
      assert.equal(report.commands.filter((x:any)=>x[0]==='restore').length,1);
      assert.equal(report.commands.filter((x:any)=>x[0]==='submit').length,1);
      assert.deepEqual(errors,[]);return;
    }
    await page.evaluate(()=>{(window as any).SteamAnimatedScreensaverPlayer.pause();});
    for(let n=0;n<40;n++){report=await rpc({report:true});if(report.jsaux.phase==='idle'&&report.commands.some((x:any)=>x[0]==='restore'))break;await sleep(50);}
    assert.equal(report.commands.filter((x:any)=>x[0]==='restore').length,1,JSON.stringify({report,transport:await page.evaluate(()=>(window as any).DAS_JSAUX_TRANSPORT),messages}));assert.equal(report.jsaux.phase,'idle');
  }finally{
    await browser?.close();if(httpsServer)await new Promise<void>(resolve=>httpsServer.close(()=>resolve()));
    if(tlsDir)rmSync(tlsDir,{recursive:true,force:true});worker.stdin.end();
    await new Promise<void>(resolve=>{if(worker.exitCode!==null)resolve();else{const timer=setTimeout(()=>{worker.kill('SIGKILL');resolve();},3000);worker.once('exit',()=>{clearTimeout(timer);resolve();});}});
  }
});
