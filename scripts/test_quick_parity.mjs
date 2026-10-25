// Compare actual React primitives and computed browser geometry. This is not a
// SteamOS capture; both sides use the same browser-only native-control adapter.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import http from 'node:http';
import assert from 'node:assert/strict';
import {rollup} from 'rollup';
import ts from 'typescript';

const root=process.cwd(),gca=process.env.DAS_TEST_GCA_ROOT;
if(!gca)throw new Error('DAS_TEST_GCA_ROOT must name the actual reference checkout');
const require=createRequire(path.join(root,'package.json'));
const runtime=process.env.DAS_UI_DEPS||'/private/tmp/das-ui-test-deps/node_modules';
const fromDecky=createRequire(require.resolve('@decky/rollup/package.json'));
const {nodeResolve}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-node-resolve')));
const {default:commonjs}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-commonjs')));
const {chromium}=require(process.env.DAS_PLAYWRIGHT||'playwright');
const bundle=await rollup({input:path.join(root,'tests/ui/quick-controls.tsx'),plugins:[{
  name:'native-and-gca-adapters',resolveId(source){
    if(source==='@decky/ui'||source==='../localized_ui')return path.join(root,'tests/ui/decky.tsx');
    if(source==='gca-compact-style')return path.join(gca,'src/components/compact_quick_style.ts');
    if(source==='gca-reference-action')return path.join(gca,'src/components/QuickAction.tsx');
    if(source==='./client')return '\0no-backend';
    if(source==='react')return path.join(runtime,'react/index.js');
    if(source==='react/jsx-runtime')return path.join(runtime,'react/jsx-runtime.js');
    if(source==='react-dom/client')return path.join(runtime,'react-dom/client.js');
  },load(id){if(id==='\0no-backend')return 'export const client=()=>Promise.reject(new Error("No live backend"));';},
  transform(code,id){if(/\.tsx?$/.test(id))return ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;}
},nodeResolve({browser:true,extensions:['.js','.tsx','.ts','.json']}),commonjs(),{
  name:'production',transform(code){return code.replaceAll('process.env.NODE_ENV','"production"');}
}]});
const {output}=await bundle.generate({format:'iife'});await bundle.close();
const style=`body{margin:0;background:#101822;color:#f0f5fa;font:16px Arial,sans-serif}main{display:flex;gap:32px;justify-content:center;padding:24px}article{width:340px;min-width:0}h1{font-size:12px;color:#b8c9d8;font-weight:400;margin:0 0 20px}button{font:inherit;cursor:pointer;padding:10px;color:inherit;background:#304050}p{margin:0}.reference-status{font:400 14px/1.4 Arial,sans-serif}@media(max-width:720px){main{flex-direction:column;align-items:center;padding:12px}article{max-width:100%}}`;
const html=`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${style}</style><div id="root"></div><script src="/app.js"></script>`;
const server=http.createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/app.js'?'text/javascript':'text/html');res.end(req.url==='/app.js'?output[0].code:html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
await fs.mkdir('out/ui',{recursive:true});
try{
 const page=await browser.newPage({viewport:{width:820,height:1100}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));await page.goto(`http://127.0.0.1:${server.address().port}/`);
 const shape=node=>{const s=getComputedStyle(node);return {background:s.backgroundColor,color:s.color,font:s.font,border:s.border,borderRadius:s.borderRadius,boxShadow:s.boxShadow};};
 for(const lang of ['fr','en'])for(const matrix of [true,false])for(const phase of ['current','available','ready','expired']){
  await page.evaluate(([lang,matrix,phase])=>window.__parity.show(lang,matrix,phase),[lang,matrix,phase]);
  await page.waitForTimeout(80);
  const ref=page.locator('#gca-compact-root'),target=page.locator('#das-compact-root');
  await target.waitFor();
  assert.deepEqual(await target.evaluate(shape),await ref.evaluate(shape),`root ${lang}/${matrix}/${phase}`);
  const refs=ref.locator('button'),targets=target.locator('button');assert.equal(await targets.count(),phase==='current'?2:3);
  assert.equal(await target.locator('[data-das-quick-zone=updates]').count(),phase==='current'?0:1);
  for(let n=0;n<(phase==='current'?2:3);n++){
   assert.deepEqual(await targets.nth(n).evaluate(shape),await refs.nth(n).evaluate(shape),`button ${n} ${lang}/${matrix}/${phase}`);
   for(const element of [refs.nth(n),targets.nth(n)])await element.evaluate(node=>node.classList.add('gpfocus'));
   const focus=node=>{const s=getComputedStyle(node);return {background:s.backgroundColor,outline:s.outline,offset:s.outlineOffset,shadow:s.boxShadow};};
   assert.deepEqual(await targets.nth(n).evaluate(focus),await refs.nth(n).evaluate(focus));
   for(const element of [refs.nth(n),targets.nth(n)])await element.evaluate(node=>node.classList.remove('gpfocus'));
  }
  if(phase==='current'){
   assert.equal(await target.getByRole('button',{name:lang==='fr'?'Mises à jour':'Updates',exact:true}).count(),0);
  }else{
   assert((await targets.first().textContent()).includes('0.1.0-alpha.48'));
   await targets.first().click();assert.deepEqual(await page.evaluate(()=>window.__quickCalls),[['updates']]);
  }
  assert.equal(await target.getByRole('button',{name:lang==='fr'?'Réglages':'Settings',exact:true}).count(),0,'No duplicate Settings action in the body');
  const gear=page.locator('.das-quick-gear');assert.equal(await gear.count(),1);assert.equal(await gear.getAttribute('aria-label'),lang==='fr'?'Réglages':'Settings');await gear.click();assert.deepEqual(await page.evaluate(()=>window.__quickCalls),phase==='current'?[['gear','settings']]:[['updates'],['gear','settings']]);
  assert.equal(await target.evaluate(node=>node.scrollWidth>node.clientWidth),false);
  await page.screenshot({path:`out/ui/quick-parity-${lang}-${matrix?'jsaux':'tv'}-${phase}.png`,fullPage:true});
 }
 assert.deepEqual(errors,[]);console.log('PASS: 16 FR/EN + TV/JSAUX + current/available/ready/expired-auth scenarios; shared GCA/DAS native action surfaces match root/button/focus paint; duplicate Settings removed and header gear retained; update action only when available, no empty section when current; no download/install or hardware call.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
