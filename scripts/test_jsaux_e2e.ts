/** Actual player -> real loopback HTTP -> actual plugin -> Unix broker.
 * Browser Origin is supplied by the Node adapter; physical USB is simulated. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));
for(const mode of ['sync','async'])test(`Installed ${mode}: three common-preparation/player/broker/restore cycles`,
  {skip:!process.env.DAS_TEST_GCA_ROOT||!process.env.DAS_TEST_FFMPEG,timeout:30000},async()=>{
  const worker=spawn('python3',['tests/backend/jsaux_e2e_worker.py'],{env:{...process.env,DAS_TEST_MODE:mode,PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let stderr='',serial=0;const waiting=new Map<number,{resolve:(x:any)=>void,reject:(x:any)=>void}>();
  worker.stderr.on('data',b=>stderr+=b.toString());
  const setup=new Promise<any>((resolve,reject)=>{
    const lines=createInterface({input:worker.stdout});
    lines.on('line',raw=>{const x=JSON.parse(raw);if(x.setup)resolve(x.catalog);else{const p=waiting.get(x.id);waiting.delete(x.id);if(x.error)p?.reject(x.error);else p?.resolve(x.result);}});
    worker.on('exit',code=>{if(code){reject(new Error(stderr));for(const p of waiting.values())p.reject(new Error(stderr));}});
  });
  const rpc=(payload:any)=>new Promise<any>((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});worker.stdin.write(JSON.stringify({id,...payload})+'\n');});
  let player:any;
  try{
    const catalog=await setup;assert.equal(catalog.jsaux.mode,mode);
    let nativeCalls=0;const storage={GetString:()=>{nativeCalls++;throw Error('Legacy native must not be used');},SetString:()=>{nativeCalls++;throw Error('Legacy native must not be used');}};
    const context:any={module:{exports:{}},URL,Date};vm.runInNewContext(readFileSync('assets/player/player.js','utf8'),context);
    const win:any={performance,crypto:webcrypto,setTimeout,clearTimeout,addEventListener:()=>{},removeEventListener:()=>{},
      location:{href:'https://steamloopback.host/config/uioverrides/screensavers/decky-animated-screensaver/index.html'},SteamClient:{Storage:storage},AbortController,TextDecoder,
      fetch:(url:string,options:any)=>fetch(url,{...options,headers:{...options.headers,Origin:'https://steamloopback.host'}})};
    win.parent=win;const doc={referrer:'',hidden:false};let shown=0;
    // A real preview must never open, not even with native Storage present.
    const preview=context.module.exports.createJsauxLifecycle(win,doc,{...catalog,previewNonce:'preview'});preview.ready(()=>{});preview.stop();assert.equal(nativeCalls,0);
    let report:any;
    for(let cycle=0;cycle<3;cycle++){
      if(cycle)await rpc({new_activation:'activation-'+cycle});
      player=context.module.exports.createJsauxLifecycle(win,doc,catalog);player.ready(()=>shown++);
      for(let i=0;i<160;i++){await sleep(25);report=await rpc({report:true});if(report.jsaux.phase==='active')break;}
      assert.equal(shown,cycle+1);assert.equal(report.jsaux.phase,'active',JSON.stringify(report));
      assert.equal(report.commands.filter((x:any)=>x[0]==='submit').length,cycle+1,JSON.stringify(report));
      if(mode==='sync')assert.equal(report.delivery.calibration.last.reference_basis,'broker-confirmation-event');
      assert.equal(nativeCalls,0);assert(report.jsaux.player_relay.requests>=3);
      assert(report.jsaux.events.some((e:any)=>e.event==='player-ready'));
      player.stop();await sleep(650);report=await rpc({report:true});
      assert.equal(report.commands.filter((x:any)=>x[0]==='restore').length,cycle+1,JSON.stringify(report));
      assert.equal(report.jsaux.phase,'idle');
    }
  }finally{player?.stop();worker.stdin.end();await new Promise<void>(resolve=>{if(worker.exitCode!==null)resolve();else{const timer=setTimeout(()=>{worker.kill('SIGKILL');resolve();},3000);worker.once('exit',()=>{clearTimeout(timer);resolve();});}});}
});
