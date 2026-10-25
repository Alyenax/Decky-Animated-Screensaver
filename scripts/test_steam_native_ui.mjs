import {reorder65} from './test_reorder65.mjs';
import {fluid64} from './test_fluid64.mjs';
import {recovery57} from '../tests/steam-runtime/recovery57.mjs';
// Installed Steam CSS + inspected DOM adapters. No Valve assets are redistributed.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
const decode=bytes=>bytes[0]===31&&bytes[1]===139?gunzipSync(bytes):bytes;
import fs from 'node:fs/promises';
import http from 'node:http';
import assert from 'node:assert/strict';
import {rollup} from 'rollup';
import ts from 'typescript';
import {listGeometry55,playerGeometry55} from '../tests/steam-runtime/geometry55.mjs';
import {stability56} from '../tests/steam-runtime/stability56.mjs';
const root=process.cwd(),gca=process.env.DAS_TEST_GCA_ROOT,reference=process.env.DAS_STEAM_REFERENCE;
if(!gca||!reference)throw Error('DAS_TEST_GCA_ROOT and DAS_STEAM_REFERENCE (read-only extracted module metadata) are required');
const native=JSON.parse(await fs.readFile(reference,'utf8')),steamRoot=native.steamRoot;
const assetNames=['library.js','sp.js','css/library.css','css/sp.css'];
const assetHashes=Object.fromEntries(await Promise.all(assetNames.map(async name=>[name,createHash('sha256').update(await fs.readFile(path.join(steamRoot,name))).digest('hex')])));
assert.equal(native.sha256?.['sp.js']||native.js_sha256,assetHashes['sp.js'],'Reference JS metadata is stale: regenerate from this installed Steam before testing');
assert.equal(native.sha256?.['css/sp.css']||native.css_sha256,assetHashes['css/sp.css'],'Reference CSS metadata is stale: regenerate JS/classes/CSS together');
const sourceRef=process.env.DAS_NATIVE_SOURCE_REF||'';
const sourceCache=new Map();
const css=(await fs.readFile(path.join(steamRoot,'css/library.css'),'utf8'))+'\n'+await fs.readFile(path.join(steamRoot,'css/sp.css'),'utf8');
const require=createRequire(path.join(root,'package.json')),fromDecky=createRequire(require.resolve('@decky/rollup/package.json'));
const {nodeResolve}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-node-resolve'))),{default:commonjs}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-commonjs'))),{chromium}=require('playwright');
const runtime=process.env.DAS_UI_DEPS||'/private/tmp/das43-ui-deps/node_modules';
const gcaRPC=['extendFreeTimer','getQuickArtwork','setFaceplatePower','setFaceplateRouting','setLightBarBrightness','setSetting','startFreeTimer','stopFreeTimer'];
const bundle=await rollup({input:path.join(root,'tests/ui/native-panels.tsx'),plugins:[{
 name:'native-inspected-adapters',resolveId(source,importer){
  if(source==='@decky/api')return '\0decky-api';
  if(importer?.endsWith('/custom-components/ReorderableList.tsx')&&source==='../components')return path.join(root,'tests/ui/steam-decky.tsx');
  if(source==='@decky/ui')return path.join(root,'tests/ui/steam-decky.tsx');
  if(source==='gca-onboarding-production')return path.join(gca,'src/components/FirstRunOnboarding.tsx');
  if(source==='gca-quick-production')return path.join(gca,'src/components/CompactQuickPanel.tsx');
  if(source==='gca-settings-production')return path.join(gca,'src/index.tsx');
  if(source==='gca-localized-production')return path.join(gca,'src/localized_ui.tsx');
  if(source==='gca-language')return path.join(gca,'src/i18n.ts');



  if(source==='./client')return '\0collection-client';
  if(source==='react')return path.join(runtime,'react/index.js');
  if(source==='react/jsx-runtime')return path.join(runtime,'react/jsx-runtime.js');
  if(source==='react-dom/client')return path.join(runtime,'react-dom/client.js');
 },load(id){
  if(id==='\0decky-api')return 'export const callable=(name)=>(...args)=>window.__gcaQaRpc(name,args);export const definePlugin=()=>null;export const routerHook={addRoute(){},removeRoute(){}};export const toaster={toast(){}};export const addEventListener=()=>()=>{};export const removeEventListener=()=>{};export const openFilePicker=async()=>null;';
  if(id==='\0gca-rpc')return gcaRPC.map(name=>`export async function ${name}(){return window.__gcaStatus;}`).join('\n');
  if(id==='\0gca-voice')return 'export async function getGabeStatus(){return {voice_ready:false}};export async function setGabeListening(){};export async function gabeAction(){};';
  if(id==='\0gca-session')return 'export const GabeSettingsSession=({children})=>children;';
  if(id==='\0collection-client')return 'export const client=(...args)=>window.__collectionRpc(...args);';
 },transform(code,id){if(sourceRef&&id.startsWith(path.join(root,'src')+path.sep)){if(!sourceCache.has(id))sourceCache.set(id,execFileSync('git',['show',sourceRef+':'+path.relative(root,id)],{cwd:root,encoding:'utf8'}));code=sourceCache.get(id);}if(id===path.join(gca,'src/index.tsx'))code+='\nexport {GabeCubeAuraSettings};';if(/\.tsx?$/.test(id))return ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;}
 },nodeResolve({browser:true,extensions:['.js','.tsx','.ts','.json']}),commonjs(),{name:'production',transform(code){return code.replaceAll('process.env.NODE_ENV','"production"');}}]});
const {output}=await bundle.generate({format:'iife'});await bundle.close();
const gcaPreview=await fs.readFile(path.join(gca,'tests/browser/settings_preview.mjs'),'utf8');
const python=gcaPreview.slice(gcaPreview.indexOf('const python=`')+14,gcaPreview.indexOf('`;\nconst status='));
const status=JSON.parse(execFileSync('python3',['-c',python],{cwd:gca,env:{...process.env,PYTHONPATH:path.join(gca,'py_modules')},encoding:'utf8'}));
status.version=JSON.parse(await fs.readFile(path.join(gca,'package.json'),'utf8')).version;status.available=true;status.onboarding_completed=true;status.faceplate.steamgriddb={configured:false,validation_state:'missing'};status.faceplate.delivery={state:'idle'};
const voiceSource=(process.env.DAS_NATIVE_FLUID64_ONLY==='1'||process.env.DAS_NATIVE_REORDER65_ONLY==='1')?'':await fs.readFile(path.join(gca,'tests/frontend/gabe_settings_tabs.test.ts'),'utf8');
const voice=(process.env.DAS_NATIVE_FLUID64_ONLY==='1'||process.env.DAS_NATIVE_REORDER65_ONLY==='1')?{}:Function(voiceSource.slice(voiceSource.indexOf('function fixture('),voiceSource.indexOf('\nfunction mount('))+';return fixture();')();
const update={phase:'current',installed_version:status.version,available:false,bundle_components:['plugin'],channel:'private',private_tools:true,private_auth_configured:true,private_auth_state:'connected',private_repository:'Alyenax/GabeCubeAura-Lab',auto_check:true,auto_install:false,notifications:true,check_interval_minutes:60,test_build:true,error:'',release_notes:''};
const diagnostics={private_tools:true,automatic_upload:false,last_error:'',last_upload_url:'',pending:false};
const init=gcaPreview.slice(gcaPreview.indexOf('const init=`')+12,gcaPreview.indexOf('`;\nconst artwork='));
const rpcData=Function('status','voice','update','diagnostics','return `'+init+'`;')(status,voice,update,diagnostics);
const rpcInit=rpcData+`;const baseRPC=window.__gcaQaRpc;window.__gcaQaRpc=async(name,args)=>{if(name==='get_onboarding')return {draft:{},bar_detected:true,faceplate_detected:true,faceplate_busy:false,voice_verified:false};if(name==='save_onboarding_draft')return args[0];return baseRPC(name,args);};`;
// Serve official fonts in-memory to avoid host/browser TLS-proxy differences.
// No font or stylesheet is saved into the repository or runtime package.
const fontBase='https://community.fastly.steamstatic.com/public/shared/',fontCache=new Map();
const fontCSS=decode(execFileSync('curl',['--fail','--location','--compressed','--max-time','20','-sS',fontBase+'css/motiva_sans.css'],)).toString('utf8').replaceAll(fontBase+'fonts/','/steam-font/');
const html=`<!doctype html><html class="GamepadMode GamepadUI"><meta charset="utf-8"><style>${css}</style><style>html,body,#surface,#root{height:100%;margin:0}body{font-family:"Motiva Sans",Arial,sans-serif;background:#0e141b;color:#dcdedf;--basicui-header-height:40px;--gamepadui-current-footer-height:40px}#root[data-qam]{width:340px;margin:0 auto;padding-top:16px;background:#23262e}</style><body><div id="surface"><div id="root"></div></div><script>window.__steamNative=${JSON.stringify(native)};${rpcInit}</script><script src="/app.js"></script></body></html>`;
const server=http.createServer(async(req,res)=>{
 if(/^\/custom_fonts\/clientui\.uifont\?MotivaSans-[A-Za-z]+$/.test(req.url))req.url='/steam-font/'+req.url.split('?')[1]+'.ttf?v=4.015';
 if(req.url==='/steam-font.css'){res.setHeader('Content-Type','text/css');res.end(fontCSS);return;}
 if(/^\/steam-font\/MotivaSans-[A-Za-z]+\.ttf(?:\?v=[\d.]+)?$/.test(req.url)){
  if(!fontCache.has(req.url))fontCache.set(req.url,decode(execFileSync('curl',['--fail','--location','--compressed','--max-time','20','-sS',fontBase+'fonts/'+req.url.slice('/steam-font/'.length)])));
  res.setHeader('Content-Type','font/ttf');res.end(fontCache.get(req.url));return;
 }
 if(req.url==='/app.js'){res.setHeader('Content-Type','text/javascript');res.end(output[0].code);return;}
 if(/^\/[a-f0-9]{40}\/[a-f0-9]{24}$/.test(req.url)){res.setHeader('Content-Type','text/html');res.end('<!doctype html><body style="margin:0;background:#15283a;color:#dcdedf;display:grid;place-content:center;height:100vh;font:18px sans-serif">Isolated preview fixture<script>parent.postMessage({type:"screensaver-player",nonce:"fixture",status:"playing"},location.origin)</script>');return;}
 if(/^\/images\/\d+\.jpg$/.test(req.url)){try{res.setHeader('Content-Type','image/jpeg');res.end(await fs.readFile(path.join(root,'../output/audits/DAS_UX_2026-10-19/assets',path.basename(req.url))));return;}catch{res.statusCode=404;res.end();return;}}
 if(req.url.startsWith('/images/')){const file=path.resolve(steamRoot,'.'+req.url);if(file.startsWith(steamRoot+'/'))try{res.end(await fs.readFile(file));return;}catch{}res.statusCode=404;res.end();return;}
 res.setHeader('Content-Type','text/html');res.end(html);
});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
if(process.env.DAS_NATIVE_SERVE_ONLY==='1'){console.log('NATIVE QA http://127.0.0.1:'+server.address().port);await new Promise(()=>{});}
const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const orderOnly65=process.env.DAS_NATIVE_REORDER65_ONLY==='1';
const fluidOnly64=process.env.DAS_NATIVE_FLUID64_ONLY==='1';
const recoveryOnly57=process.env.DAS_NATIVE_RECOVERY57_ONLY==='1';
const stabilityOnly56=process.env.DAS_NATIVE_STABILITY56_ONLY==='1';
const managementOnly60=process.env.DAS_NATIVE_MANAGEMENT60_ONLY==='1';
const copyOnly59=process.env.DAS_NATIVE_COPY59_ONLY==='1';
const focused55=orderOnly65||fluidOnly64||managementOnly60||copyOnly59||process.env.DAS_NATIVE_FOCUS55_ONLY==='1'||stabilityOnly56||recoveryOnly57;
const out=path.join(root,'out/ui',orderOnly65?'steam-native65-order':fluidOnly64?'steam-native64-editor':sourceRef?'steam-native-alpha54-regression':managementOnly60?'steam-native60-management':copyOnly59?'steam-native59-copy':recoveryOnly57?'steam-native57-recovery':stabilityOnly56?'steam-native56-stability':focused55?'steam-native56-focused':'steam-native');await fs.mkdir(out,{recursive:true});
try{
 const page=await browser.newPage({viewport:{width:800,height:900}}),errors=[];page.setDefaultTimeout(5000);page.on('requestfailed',request=>console.log('REQUEST FAILED',request.url(),request.failure()?.errorText));page.on('pageerror',error=>errors.push(error.message));
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 const fonts=await page.evaluate(async()=>{const faces=await document.fonts.load('16px \"Motiva Sans\"');await document.fonts.ready;return faces.map(face=>({family:face.family,status:face.status}));});
 assert(fonts.some(face=>face.family==='Motiva Sans'&&face.status==='loaded'),'Steam Motiva Sans must load; no silent fallback-font validation');
 const captures=[],geometry=[];
 if(orderOnly65)await reorder65({page,captureDir:path.join(out,'reorder65'),mount:async(lang,options)=>{await page.evaluate(({lang,options})=>window.__collection.mount(lang,options),{lang,options});await page.waitForTimeout(420);},button:key=>page.locator(`[data-collection-focus="${key}"]`),check:name=>{geometry.push({name,passed:true});console.log('PASS '+name);}});
 if(fluidOnly64)await fluid64({page,captureDir:path.join(out,'fluid64'),mount:async(lang,options)=>{await page.evaluate(({lang,options})=>window.__collection.mount(lang,options),{lang,options});await page.waitForTimeout(420);},button:key=>page.locator(`[data-collection-focus="${key}"]`),check:name=>{geometry.push({name,passed:true});console.log('PASS '+name);}});
 const surfaces=orderOnly65||fluidOnly64?[]:managementOnly60?['das-collection','das-add','das-undo','das-delete']:copyOnly59?['das-collection','das-add','das-game','das-faceplate','das-updates']:stabilityOnly56||recoveryOnly57?[]:focused55?['das-list','das-add-list','das-player','das-faceplate']:['gca-quick','gca-settings','gca-onboarding','das-quick','das-collection','das-settings','das-add','das-game','das-faceplate','das-updates','das-list','das-add-list','das-player'];
 for(const width of [800,1280])for(const classic of [true,false])for(const lang of ['fr','en'])for(const surface of surfaces){
  await page.setViewportSize({width,height:focused55&&width===1280?720:800});
  const qam=surface.endsWith('quick');await page.evaluate(({surface,lang,qam,classic})=>{window.__classic=classic;(document.getElementById('surface')||document.getElementById('QuickAccess-Menu')).id=qam?'QuickAccess-Menu':'surface';const root=document.getElementById('root');if(qam)root.setAttribute('data-qam','');else root.removeAttribute('data-qam');if(surface.startsWith('gca-'))window.__gca.mount(surface.slice(4),lang);else window.__collection.mount(lang,{quick:qam,add:surface==='das-add'||surface==='das-add-list',jsaux:['das-game','das-faceplate'].includes(surface),...(surface==='das-faceplate'?{jsauxState:{reason:'',calibration:{available:true,offset_ms:0},prepared:{ready:true,bytes:16384,sync_admissible:true}}}:{})});},{surface,lang,qam,classic});
  await page.waitForTimeout(350);
  if(surface==='das-list'||surface==='das-add-list'){await page.getByRole('combobox',{name:lang==='fr'?'Présentation':'View',exact:true}).selectOption('list');await page.waitForTimeout(350);}
  if(managementOnly60){
   if(surface==='das-undo'){await page.locator('[data-collection-focus=clear-selection]').click();await page.locator('[data-collection-focus=undo-selection]').waitFor();}
   if(surface==='das-delete'){await page.locator('[data-collection-focus=manage-collection]').click();await page.locator('[data-collection-focus=delete-collection]').click();await page.locator('[data-collection-focus=cancel-delete]').waitFor();}
   const region=page.locator(surface==='das-delete'?'.collection-management-confirm':surface==='das-undo'?'.collection-selection-undo':'.collection-management-actions');
   const bounds=await region.evaluate(node=>{const p=node.getBoundingClientRect();return [...node.querySelectorAll('[data-collection-focus]')].map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,w:r.width,h:r.height,overflow:n.scrollWidth>n.clientWidth+2,parent:{x:p.x,right:p.right}};});});
   assert(bounds.length===(surface==='das-undo'?1:2),'Expected management controls');for(const b of bounds)assert(b.x>=b.parent.x-1&&b.right<=b.parent.right+1&&b.w>=120&&b.h>=36&&!b.overflow,'Readable, contained native management controls');
   if(bounds.length===2)assert(bounds[0].right<=bounds[1].x+1||bounds[0].bottom<=bounds[1].y+1,'Management controls never overlap');
  }
  if(surface==='das-player'){await page.locator('[data-collection-focus="primary"]').click();await page.locator('.collection-player-controls').waitFor();}
  if(surface==='das-game'){await page.locator('.collection-card').first().click();await page.locator('.collection-detail').waitFor();}
  if(copyOnly59&&surface==='das-game'){
   const bounds=await page.locator('.collection-background-actions').evaluate(node=>{const col=node.closest('[data-detail-column]').getBoundingClientRect();return [...node.querySelectorAll('button')].map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,w:b.width,h:b.height,overflow:n.scrollWidth>n.clientWidth+2,colRight:col.right};});});
   assert.equal(bounds.length,2);assert(Math.abs(bounds[0].y-bounds[1].y)<1&&bounds[0].right<=bounds[1].x+1);assert(bounds.every(b=>b.w>90&&b.right<=b.colRight+1&&!b.overflow),'Native animation/still controls stay contained and readable');
  }

  if(surface==='das-faceplate'||surface==='das-updates'){
   await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();await page.locator('[data-collection-focus="settings-'+(surface==='das-faceplate'?'jsaux':'updates')+'"]').click();
  }
  if(focused55&&!copyOnly59&&surface==='das-faceplate'){
   await page.getByRole('button',{name:lang==='fr'?'Détails Faceplate JSAUX':'Faceplate JSAUX details',exact:true}).click();
   await page.locator('.native-item').filter({has:page.getByText(lang==='fr'?'Alignement visuel':'Visual alignment',{exact:true})}).getByRole('button',{name:lang==='fr'?'Ajuster':'Adjust',exact:true}).click();
   const actions=await page.locator('.collection-player-controls button').evaluateAll(nodes=>nodes.map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height,right:b.right};}));
   assert.equal(actions.length,2,'Faceplate timing correction has2 compact actions');assert(Math.abs(actions[0].y-actions[1].y)<=1&&actions[0].right<=actions[1].x+1,'Faceplate timing actions share a nonoverlapping row');
  }
  if(surface==='das-settings'){await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();await page.waitForTimeout(100);}
  if(errors.length)throw Error(JSON.stringify(errors));
  const tag=`${surface}-${lang}-${width}-${classic?'classic':'current'}`;
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,tag+' page overflow');
  if(qam)assert(await page.locator('.'+native.modules.panel.PanelSection).count()>0,tag+' native PanelSection');
  else if(!['gca-onboarding','das-game','das-faceplate','das-updates','das-player','das-delete'].includes(surface)){
   await page.locator('[role="tabpanel"]').waitFor({state:'visible'});
   const content=await page.locator('[role="tabpanel"]').boundingBox();assert(content.width>width*.45&&content.height>150,tag+' visible content bounds');
   assert.equal(await page.locator('[role="tabpanel"] [data-native-scroll-panel]').count(),0,tag+' no nested tab scroller');
  }
  if(['das-collection','das-add','das-list','das-add-list'].includes(surface)){
   const toolbar=await page.locator('.collection-search-view').evaluate((el,fieldClass)=>{
    const fields=[...el.children],rects=fields.map(n=>n.getBoundingClientRect()),labels=fields.map(n=>n.querySelector('.collection-toolbar-label')?.getBoundingClientRect());
    const controls=fields.map(n=>n.querySelector('input,.DialogDropDown')?.getBoundingClientRect());
    return {count:fields.length,nativeFields:el.querySelectorAll('.'+fieldClass).length,widths:rects.map(b=>b.width),labels:labels.map(b=>b?{y:b.y,h:b.height}:null),controls:controls.map(b=>b?{y:b.y,h:b.height,w:b.width}:null),backgrounds:fields.map(n=>getComputedStyle(n).backgroundColor)};
   },native.modules.dialog.Field);
   assert.equal(toolbar.count,3,'Search / filter or source / View share one three-column toolbar');
   assert.equal(toolbar.nativeFields,0,'Toolbar labels and controls have no extra native Field background/padding');
   assert(toolbar.labels.every(Boolean)&&toolbar.controls.every(Boolean),'Every toolbar column has a compact label and one native control');
   assert(toolbar.backgrounds.every(c=>c==='rgba(0, 0, 0, 0)'||c==='transparent'),'Toolbar columns do not add opaque field panels');
   for(let i=0;i<3;i++){
    assert(Math.abs(toolbar.widths[0]-toolbar.widths[i])<=1,'Three symmetric toolbar widths');
    assert(Math.abs(toolbar.labels[0].y-toolbar.labels[i].y)<=1&&toolbar.labels[i].h<=28,'Compact labels share a baseline');
    assert(Math.abs(toolbar.controls[0].y-toolbar.controls[i].y)<=1,'Three native controls share a baseline');
    assert(Math.abs(toolbar.controls[0].h-toolbar.controls[i].h)<=1&&toolbar.controls[i].h>=40&&toolbar.controls[i].h<=56,'Controls retain compact equal native heights');
    assert(toolbar.controls[i].w>=180,'Each equal column retains usable control width');
   }
  }
  const detail=surface==='das-list'||surface==='das-add-list'?await listGeometry55(page):surface==='das-player'?await playerGeometry55(page):undefined;
  if(surface==='das-add-list'){
   await page.locator('.collection-game-copy strong').first().evaluate(el=>el.textContent='A very long game title that must never run underneath the selection check mark and must remain within its independent text column');
   const longTitle=await page.locator('.collection-select-card').first().evaluate(el=>{const title=el.querySelector('.collection-game-copy strong'),check=el.querySelector('.collection-selection-check');if(!title||!check)return {missing:true};const t=title.getBoundingClientRect(),c=check.getBoundingClientRect();return {missing:false,right:t.right,checkX:c.x};});
   assert(!longTitle.missing&&longTitle.right<=longTitle.checkX+1,'Long Add list title reserves the selection check box space');
  }
  const issues=await page.evaluate(({field,left,right})=>[...document.querySelectorAll('.'+field)].flatMap(el=>{
   const l=el.querySelector('.'+left)?.getBoundingClientRect(),r=el.querySelector('.'+right)?.getBoundingClientRect(),b=el.getBoundingClientRect();
   const fails=[];if(el.scrollWidth>el.clientWidth+2)fails.push('field overflow: '+el.textContent);
   if(l&&r&&r.width&&l.right>r.left+1&&Math.min(l.bottom,r.bottom)>Math.max(l.top,r.top))fails.push('label/control overlap: '+el.textContent);
   return fails;
  }),{field:native.modules.dialog.Field,left:native.modules.dialog.FieldLeftColumn,right:native.modules.dialog.FieldRightColumn});
  assert.deepEqual(issues,[],tag+' fields');geometry.push({tag,passed:true,...(detail?{detail}:{})});
  await page.screenshot({path:path.join(out,tag+'.png')});captures.push(tag+'.png');
  // Apply Steam's own focus class; this tests visual paint and geometry, not the controller engine.
  const target=page.locator('button:not(:disabled),[role="checkbox"],[role="slider"]').first();
  if(await target.count()){
   await target.evaluate(el=>{el.classList.add('gpfocus');el.closest('.native-item')?.classList.add('gpfocuswithin');});
   await page.screenshot({path:path.join(out,tag+'-focus.png')});captures.push(tag+'-focus.png');
  }
  if(!qam&&surface!=='gca-onboarding'){await page.locator(['das-game','das-faceplate','das-updates','das-player','das-delete'].includes(surface)?'.collection-nested-scroll [data-native-scroll-panel]':'[role="tabpanel"]').evaluate(el=>el.scrollTop=el.scrollHeight);await page.waitForTimeout(50);await page.screenshot({path:path.join(out,tag+'-bottom.png')});captures.push(tag+'-bottom.png');}
 }
 // Inspect every GBA category/subtab with real production contents, not sample fields.
 if(!focused55){await page.setViewportSize({width:1280,height:800});
 await page.evaluate(()=>{window.__classic=true;(document.getElementById('surface')||document.getElementById('QuickAccess-Menu')).id='surface';document.getElementById('root').removeAttribute('data-qam');window.__gca.mount('settings','fr');});
 await page.waitForTimeout(350);
 const categories=await page.locator('.'+native.modules.sidebar.PagedSettingsDialog_PageListItem).allTextContents();
 for(let categoryIndex=0;categoryIndex<categories.length;categoryIndex++){
  const category=categories[categoryIndex];
  await page.locator('.'+native.modules.sidebar.PagedSettingsDialog_PageListItem).nth(categoryIndex).click();await page.waitForTimeout(100);
  assert.deepEqual(errors,[],category+' initial errors');
  const tabs=await page.getByRole('tab').allTextContents();
  for(const tab of tabs){
   await page.getByRole('tab',{name:tab,exact:true}).click();await page.waitForTimeout(150);
   assert.deepEqual(errors,[],category+'/'+tab+' page errors');
   const panel=page.locator('[role="tabpanel"]');assert((await panel.innerText()).trim().length>10,'Nonempty '+category+'/'+tab);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'GBA '+category+'/'+tab+' overflow');
   const filename='gca-page-'+captures.length+'.png';await page.screenshot({path:path.join(out,filename)});captures.push(filename);geometry.push({tag:'GBA '+category+'/'+tab,passed:true});
  }
 }}
 if(recoveryOnly57)await recovery57(page,out,captures,geometry);
 const stability=[];
 if(stabilityOnly56){await page.setViewportSize({width:1280,height:720});for(const lang of ['fr','en']){stability.push(await stability56(page,lang));await page.screenshot({path:path.join(out,'stable-collection-'+lang+'.png')});captures.push('stable-collection-'+lang+'.png');}}
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(out,'evidence.json'),JSON.stringify({source_ref:sourceRef||'working tree',native_asset_sha256:assetHashes,fonts,font_sha256:Object.fromEntries([...fontCache].map(([name,bytes])=>[name,createHash('sha256').update(bytes).digest('hex')])),font_stylesheet_url:"https://community.fastly.steamstatic.com/public/shared/css/motiva_sans.css",surfaces:geometry.length,captures,geometry,stability,limitations:'Installed Steam stylesheet and more faithful DOM/RPC adapters; real navigation algorithm has a separate harness; neither is a live SteamOS CEF/controller session.'},null,2));
 if(stabilityOnly56)console.log(`PASS: ${stability.length} FR/EN slow-RPC selection/scope stability paths. Captures: ${out}`);
 else if(orderOnly65)console.log(`PASS: ${geometry.length} native Decky order/Steam CSS scenarios. Captures: ${out}`);
 else if(fluidOnly64)console.log(`PASS: ${geometry.length} FR/EN native Steam CSS image editor layouts. Captures: ${out}`);
 else console.log(`PASS: ${geometry.length} native CSS surfaces, including explicit list media/text/action bounds and four full Player action bounds. Source: ${sourceRef||'working tree'}. Captures: ${out}`);
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
