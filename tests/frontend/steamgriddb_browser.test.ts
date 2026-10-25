import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source=readFileSync(new URL('../../src/steamgriddb_browser.ts',import.meta.url),'utf8');
const js=ts.transpileModule(source.replace(/^import.*\n/gm,'').replace(/^export /gm,''),{
  compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.None}
}).outputText;
function harness(mode:'native'|'missing'|'throws'){
  const opened:{kind:string;url:string;bound?:boolean}[]=[];
  const system={OpenInSystemBrowser(this:unknown,url:string){
    if(mode==='throws')throw new Error('Native browser unavailable');
    opened.push({kind:'system',url,bound:this===system});
  }};
  const context=vm.createContext({Navigation:{NavigateToExternalWeb:(url:string)=>opened.push({kind:'steam',url})},
    ...(mode==='missing'?{}:{SteamClient:{System:system}})});
  vm.runInContext(js+'\nthis.open=openSteamGridDBPage;',context);
  return {opened,open:context.open as (page:'login'|'keys')=>string};
}
test('direct Steam login uses the correct OpenID realm and callback, in the system browser',()=>{
  const h=harness('native');assert.equal(h.open('login'),'system');
  assert.equal(h.opened.length,1);assert.equal(h.opened[0].bound,true);
  const url=new URL(h.opened[0].url);
  assert.equal(url.origin,'https://steamcommunity.com');assert.equal(url.pathname,'/openid/login');
  assert.equal(url.searchParams.get('openid.mode'),'checkid_setup');
  assert.equal(url.searchParams.get('openid.realm'),'https://www.steamgriddb.com');
  assert.equal(url.searchParams.get('openid.return_to'),'https://www.steamgriddb.com/login/steam');
  assert.equal(url.searchParams.get('openid.identity'),url.searchParams.get('openid.claimed_id'));
});
test('API preferences use the same system browser, without a secret or popup',()=>{
  const h=harness('native');h.open('login');assert.equal(h.open('keys'),'system');
  assert.equal(h.opened[1].url,'https://www.steamgriddb.com/profile/preferences/api');
  assert(h.opened.every(value=>value.kind==='system'));
});
for(const mode of ['missing','throws'] as const)test('Steam browser fallback preserves direct login and API route: '+mode,()=>{
  const h=harness(mode);assert.equal(h.open('login'),'steam');assert.equal(h.open('keys'),'steam');
  assert.equal(h.opened.length,2);assert(h.opened.every(value=>value.kind==='steam'));
  assert.equal(new URL(h.opened[0].url).pathname,'/openid/login');
  assert.equal(h.opened[1].url,'https://www.steamgriddb.com/profile/preferences/api');
});
