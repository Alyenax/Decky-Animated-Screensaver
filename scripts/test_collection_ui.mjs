import {settings66} from './test_settings66.mjs';
import {reorder65} from './test_reorder65.mjs';
import {fluid64} from './test_fluid64.mjs';
// Production components in a real browser, with simulated Decky controls/RPC.
// This is not native SteamOS, authentication, encoder or hardware evidence.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import http from 'node:http';
import assert from 'node:assert/strict';
import {mockupParity54} from './test_mockup_parity54.mjs';
import {selectionRecovery57} from './test_selection_recovery57.mjs';
import {collectionManagement60} from './test_collection_management60.mjs';
import {selectAll61} from './test_select_all61.mjs';
import {diagnostics62} from './test_diagnostics62.mjs';
import {storage63} from './test_storage63.mjs';
import {correction55} from './test_correction55.mjs';
import {rollup} from 'rollup';
import ts from 'typescript';
const root=process.cwd(),require=createRequire(path.join(root,'package.json'));
const runtime=process.env.DAS_UI_DEPS||'/private/tmp/das-ui-test-deps/node_modules';
const fromDecky=createRequire(require.resolve('@decky/rollup/package.json'));
const {nodeResolve}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-node-resolve')));
const {default:commonjs}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-commonjs')));
const {chromium}=require(process.env.DAS_PLAYWRIGHT||'playwright');
const bundle=await rollup({input:path.join(root,'tests/ui/collection.tsx'),plugins:[{
 name:'decky-rpc-adapters',resolveId(source,importer){
  if(importer?.endsWith('/custom-components/ReorderableList.tsx')&&source==='../components')return path.join(root,'tests/ui/decky.tsx');
  if(source==='@decky/api')return path.join(root,'tests/ui/api66.ts');
  if(source==='@decky/ui')return path.join(root,'tests/ui/decky.tsx');
  if(source==='./client')return '\0collection-client';
  if(source==='react')return path.join(runtime,'react/index.js');
  if(source==='react/jsx-runtime')return path.join(runtime,'react/jsx-runtime.js');
  if(source==='react-dom/client')return path.join(runtime,'react-dom/client.js');
 },load(id){if(id==='\0collection-client')return 'export const client=(name,payload)=>window.__collectionRpc(name,payload);';},
 transform(code,id){if(/\.tsx?$/.test(id))return ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;}
},nodeResolve({browser:true,extensions:['.js','.tsx','.ts','.json']}),commonjs(),{name:'production',transform:code=>code.replaceAll('process.env.NODE_ENV','"production"')} ]});
const {output}=await bundle.generate({format:'iife'});await bundle.close();console.log('Production UI test bundle ready');
const html='<!doctype html><meta charset="utf-8"><style>html,body,#root{height:100%;margin:0}body{background:#101822;color:#edf4fc;font:18px Arial,sans-serif}button,input,select{font:inherit;color:inherit;background:#30495c;border:1px solid #526b80;padding:9px;cursor:pointer}button:focus{outline:3px solid #9df0ed;outline-offset:-3px}.native-item,.native-field{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0}.native-item>div:first-child,.native-field>div:first-child{min-width:0;flex:1}.native-item>div:last-child,.native-field>div:last-child{flex-shrink:0}input{max-width:55%}.native-field input{max-width:100%;width:220px}button:disabled{opacity:.45}h2{font-size:23px}small{display:block}section{padding:14px}*{box-sizing:border-box}</style><div id="root"></div><script src="/app.js"></script>';
const images=process.env.DAS_UI_IMAGES||path.resolve(root,'../output/audits/DAS_UX_2026-10-19/assets');
const server=http.createServer(async(req,res)=>{
 if(/^\/a{40}\/c{24}$/.test(req.url)){res.setHeader('Content-Type','image/gif');res.end(Buffer.from('47494638396101000100800000ff00000000ff21ff0b4e45545343415045322e30030100000021f904000f0000002c000000000100010000020244010021f904000f0000002c00000000010001000002024c01003b','hex'));return;}
 if(/^\/images\/\d+\.jpg$/.test(req.url)){res.setHeader('Content-Type','image/jpeg');try{res.end(await fs.readFile(path.join(images,path.basename(req.url))));}catch{res.statusCode=404;res.end();}return;}
 if(req.url==='/app.js'){res.setHeader('Content-Type','text/javascript');res.end(output[0].code);return;}
 if(/^\/[ab]{40}\/[ab]{24}$/.test(req.url)){res.setHeader('Content-Type','text/html');res.end('<body style="background:#152235;color:white">Prepared player fixture<script>window.addEventListener("message",e=>{if(e.data?.action==="status"||e.data?.action==="play"||e.data?.action==="pause")parent.postMessage({type:"screensaver-player",nonce:"fixture",status:e.data.action==="pause"?"paused":"playing"},location.origin)});</script>');return;}
 res.setHeader('Content-Type','text/html');res.end(html);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
if(process.env.DAS_UI_SERVE_ONLY==='1'){console.log(`DAS UI QA: http://127.0.0.1:${server.address().port}/`);await new Promise(()=>{});}
const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
await fs.mkdir('out/ui/collection',{recursive:true});const results=[];
try{
 const page=await browser.newPage({viewport:{width:1280,height:800}}),errors=[],requests=[],fixtureRequests=[];
 const fixturePNG='https://cdn2.steamgriddb.com/thumb/das32-fixture.png',fixtureWebP='https://cdn2.steamgriddb.com/thumb/das32-fixture.webp',fixtureLegacy='https://s3.amazonaws.com/steamgriddb/thumb/das32-fixture.png';
 const fixtureSquare='https://cdn2.steamgriddb.com/thumb/square.png';const fixtureURLs=[fixturePNG,fixtureWebP,fixtureLegacy,fixtureSquare];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(fixtureURLs.includes(r.url()))fixtureRequests.push(r.url());else if(!r.url().startsWith('http://127.0.0.1:')&&!r.url().startsWith('data:'))requests.push(r.url());});
 page.setDefaultTimeout(30000);
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 const fixtureImage=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=32;c.height=24;const x=c.getContext('2d');x.fillStyle='#ec428c';x.fillRect(0,0,32,24);const png=c.toDataURL('image/png').split(',')[1],webp=c.toDataURL('image/webp').split(',')[1];c.height=32;x.fillStyle='#ec428c';x.fillRect(0,0,32,32);return {png,webp,square:c.toDataURL('image/png').split(',')[1]};});
 for(const url of fixtureURLs)await page.route(url,r=>r.fulfill({status:200,contentType:url.endsWith('.webp')?'image/webp':'image/png',body:Buffer.from(url===fixtureSquare?fixtureImage.square:url.endsWith('.webp')?fixtureImage.webp:fixtureImage.png,'base64')}));
 const mount=async(lang='fr',options={})=>{await page.evaluate(({lang,options})=>window.__collection.mount(lang,options),{lang,options});await page.waitForTimeout(420);};
 const button=key=>page.locator(`[data-collection-focus="${key}"]`);
 const check=(name)=>{results.push({name,passed:true});console.log('PASS '+name);};
 await settings66({page,mount,button,check});
 if(process.env.DAS_UI_SETTINGS66_ONLY!=='1'){
 await reorder65({page,mount,button,check});
 if(process.env.DAS_UI_REORDER65_ONLY!=='1'){
 await fluid64({page,mount,button,check});
 if(process.env.DAS_UI_FLUID64_ONLY!=='1'){
 if(process.env.DAS_UI_STORAGE63_ONLY!=='1'){
 if(process.env.DAS_UI_DIAGNOSTICS62_ONLY!=='1'){
 await collectionManagement60({page,mount,button,check});
 await selectAll61({page,mount,button,check});
 }
 await diagnostics62({page,mount,button,check});
 }
 await storage63({page,mount,button,check});
 if(process.env.DAS_UI_MANAGEMENT60_ONLY!=='1'&&process.env.DAS_UI_DIAGNOSTICS62_ONLY!=='1'&&process.env.DAS_UI_STORAGE63_ONLY!=='1'){
 await selectionRecovery57({page,mount,button,check});
 for(const lang of ['fr','en']){
  await mount(lang);await page.getByRole('tab',{name:lang==='fr'?'Ajouter des jeux':'Add games'}).click();
  const stillToggle=page.getByLabel(lang==='fr'?'Inclure les images fixes':'Include still images');
  await stillToggle.check();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='configure'&&c[1].patch.static_fallback===true));
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install'].includes(c[0])).length,0);
  check('visible fallback toggle changes preference without preparing '+lang);
  await mount(lang);await page.locator('.collection-card').first().click();await button('pick-still_tv').waitFor();
  await button('pick-still_tv').click();await button('asset-400').click();await button('save').click();
  const saved=(await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_draft');assert.equal(saved[1].patch.choices.still_tv,400);assert.equal(saved[1].patch.still_mode,'motion');
  check('direct still-image choice from game background saves exact role '+lang);
  await mount(lang,{gameRunning:true,first:true});await button('primary').click();await button('confirm').click();
  await page.locator('[data-recovery-card]').waitFor();assert.match(await page.locator('[data-recovery-card]').innerText(),lang==='fr'?/Fermez le jeu.*surcharge/:/Close.*game.*overload/i);
  assert.equal(await page.locator('[data-activity-state=preparing]').count(),0);
  check('game admission failure stays actionable without generic Decky error '+lang);
 }

 if(!process.env.DAS_UI_ONLY_RECOVERY57){
 await correction55({page,mount,button,check});
 if(!process.env.DAS_UI_ONLY_CORRECTION55&&!process.env.DAS_UI_SKIP_PARITY54)await mockupParity54({page,mount,button,check});
 if(!process.env.DAS_UI_ONLY_CORRECTION55&&!process.env.DAS_UI_ONLY_PARITY54){
 for(const lang of ['fr','en']){
  await mount(lang,{quick:true});
  assert.equal(await page.getByRole('button',{name:/Mise à jour disponible|Update available/}).count(),0);
  assert.equal(await page.getByRole('button',{name:lang==='fr'?'Mises à jour':'Updates',exact:true}).count(),0);
  assert.equal(await page.locator('[data-das-quick-zone=updates]').count(),0);
  await page.evaluate(()=>window.__collection.update({phase:'available',available:true,available_version:'0.1.0-alpha.33'}));
  const notice=page.getByRole('button',{name:(lang==='fr'?'Mise à jour disponible':'Update available')+' · 0.1.0-alpha.33',exact:true});
  await notice.waitFor();await notice.focus();await page.keyboard.press('Enter');
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='open-updates').length,1);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['update_prepare','update_install'].includes(c[0])).length,0);
  await page.evaluate(()=>window.__collection.update({phase:'ready'}));
  await page.getByRole('button',{name:(lang==='fr'?'Mise à jour prête':'Update ready')+' · 0.1.0-alpha.33',exact:true}).waitFor();
  await page.evaluate(()=>window.__collection.update({phase:'updated',available:false,installed_version:'0.1.0-alpha.33'}));
  assert.equal(await page.getByRole('button',{name:/Mise à jour prête|Update ready/}).count(),0);
  assert.equal(await page.locator('[data-das-quick-zone=updates]').count(),0);
  await mount(lang,{update:{phase:'available',available:true,available_version:'0.1.0-alpha.33'}});
  await page.locator('[data-plugin-update]').click();await page.locator('[data-updates-panel]').waitFor();
  await page.waitForFunction(()=>document.querySelector('[data-update-primary="download"] button')===document.activeElement);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['update_prepare','update_install'].includes(c[0])).length,0);
  check('persistent plugin update action / live detection / explicit Updates navigation / primary focus '+lang);
  await mount(lang,{quick:true,update:{phase:'error',available:true,available_version:'0.1.0-alpha.33',auth:{state:'expired'}}});
  await page.getByRole('button',{name:(lang==='fr'?'Mise à jour disponible':'Update available')+' · 0.1.0-alpha.33',exact:true}).click();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='open-updates').length,1);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['update_prepare','update_install','update_auth_start'].includes(c[0])).length,0);
  await mount(lang,{update:{phase:'error',available:true,available_version:'0.1.0-alpha.33',auth:{state:'expired'}}});
  await page.locator('[data-plugin-update]').click();await page.locator('[data-updates-panel]').waitFor();
  await page.getByRole('button',{name:lang==='fr'?'Télécharger la mise à jour':'Download update',exact:true}).waitFor();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['update_prepare','update_install','update_auth_start'].includes(c[0])).length,0);
  check('known update stays actionable after network failure without auto-download '+lang);
 }
 if(!process.env.DAS_UI_ONLY_UPDATES){
 for(const width of [1280,960,800])for(const lang of ['fr','en']){
  await page.setViewportSize({width,height:800});await mount(lang);
  assert.equal(await page.getByRole('tab').count(),3);assert.equal(await page.locator('.collection-card').count(),8);
  const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
   columns:getComputedStyle(document.querySelector('.collection-grid')).gridTemplateColumns.split(' ').length,
   owners:[...document.querySelectorAll('[role="tabpanel"],.collection-scroll-owner div')].filter(e=>e.scrollHeight>e.clientHeight&&['auto','scroll'].includes(getComputedStyle(e).overflowY)).length}));
  assert.equal(geometry.overflow,false);assert.equal(geometry.columns,width>1100?4:3);assert.equal(geometry.owners,1);
  const fieldInsets=await page.locator('.native-item,.native-field').evaluateAll(nodes=>nodes.map(node=>{const s=getComputedStyle(node);return [s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft].map(parseFloat);}));
  assert(fieldInsets.length>0);assert(fieldInsets.every(values=>values.every(Number.isFinite)),'native fields retain valid inherited spacing');
  await page.screenshot({path:`out/ui/collection/collection-${lang}-${width}.png`});check(`collection geometry ${lang} ${width}`);
 }
 await page.setViewportSize({width:1280,height:800});await mount();
 const card=page.locator('.collection-card').first();await card.click();
 for(const [role,id] of [['animation',100],['cover',200],['logo',300]]){
  await button('pick-'+role).click();await button('asset-'+id).waitFor();await button('asset-'+id).click();
 }
 let calls=await page.evaluate(()=>window.__collection.calls());assert.equal(calls.filter(c=>['workspace_prepare','choose','prepare','workspace_draft'].includes(c[0])).length,0);
 await button('save').click();await page.locator('.collection-grid').waitFor();
 calls=await page.evaluate(()=>window.__collection.calls());const saved=calls.find(c=>c[0]==='workspace_draft');
 assert.deepEqual(saved[1].patch.choices,{animation:100,cover:200,logo:300});
 await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('data-collection-focus')),'primary');assert((await page.locator('.collection-workflow').innerText()).includes('1 modification à préparer'));check('three edits / one draft / no conversion / focus returns to next collection action');
 await button('primary').click();assert.equal(await page.getByRole('heading',{name:'Mettre à jour ma collection ?'}).count(),1);assert.equal(await button('confirm').innerText(),'Préparer et installer');
 assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_prepare').length,0);
 await button('confirm').click();await button('pause').waitFor();await button('pause').click();await button('resume').click();await button('cancel').click();
 calls=await page.evaluate(()=>window.__collection.calls());for(const action of ['workspace_prepare','pause','resume','cancel'])assert(calls.some(c=>c[0]===action));check('explicit confirmation then pause/resume/cancel');
 assert.equal(calls.find(c=>c[0]==='workspace_prepare')[1].mode,'missing','incremental preparation is explicit in the request');
 for(const lang of ['fr','en']){
  await mount(lang);assert.equal(await button('rebuild-all').count(),0);await button('manage-collection').click();await button('rebuild-all').click();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_prepare').length,0);
  assert.equal(await button('confirm').innerText(),lang==='fr'?'Tout reconstruire et installer':'Rebuild and install');await button('confirm').click();await button('pause').waitFor();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_prepare')[1].mode,'all');
  await mount(lang,{pending:true});assert.equal(await button('primary').innerText(),lang==='fr'?'Préparer et installer':'Prepare and install');await button('primary').click();await button('confirm').click();await button('pause').waitFor();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_prepare')[1].mode,'missing');check('explicit missing vs rebuild-all scope / no auto preparation '+lang);
 }
 await mount('fr',{first:true});assert.equal(await button('primary').innerText(),'Préparer et installer');
 assert((await page.locator('.collection-workflow').innerText()).includes('8 jeux'));
 assert.equal(await button('primary').count(),1);for(const old of ['preview-existing','prepare-again','add','steam','activity'])assert.equal(await button(old).count(),0);
 assert.equal(await page.locator('.collection-header [data-collection-focus]').count(),0);
 const workflowPosition=await page.evaluate(()=>({cta:document.querySelector('.collection-workflow').getBoundingClientRect().bottom,grid:document.querySelector('.collection-grid').getBoundingClientRect().top}));assert(workflowPosition.cta<workflowPosition.grid);
 await button('primary').click();assert.equal(await button('confirm').innerText(),'Préparer et installer');assert.equal(await page.getByRole('button',{name:'Continuer',exact:true}).count(),0);
 await button('confirm').click();await button('pause').waitFor();assert.equal((await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_prepare')[1].mode,'missing');check('first creation has one top action / automatic preparation and installation / explicit confirmation');
 await mount('fr',{emptyCollection:true});assert.equal(await page.getByRole('button',{name:'Ajouter des jeux',exact:true}).count(),1);assert.equal(await button('choose').count(),0);check('empty collection has one Add games action, without duplicate empty-state button');
 for(const [outcome,title] of [['installed','Collection installée'],['unchanged','Collection déjà à jour'],['empty','Aucun jeu à installer']]){
  await mount('fr',{activity:true,task:{state:'done',outcome,tv_state:outcome==='installed'?'installed':outcome==='empty'?'empty':'unchanged',faceplate_state:'unavailable'},sceneCount:5});
  await page.getByRole('heading',{name:title,exact:true}).waitFor();for(const control of ['pause','resume','cancel'])assert.equal(await button(control).count(),0);
  if(outcome==='empty'){assert.equal(await button('preview-installed').count(),0);assert((await page.locator('.collection-activity').innerText()).includes('Rien n’a été installé'));}
  else{assert.equal(await button('preview-installed').count(),1);assert(!(await page.locator('[data-workflow-outputs]').innerText()).includes('JSAUX'));}
  await page.screenshot({path:`out/ui/collection/result-${outcome}.png`});if(outcome==='empty'){await button('allow-still-images').click();await page.waitForFunction(()=>window.__collection.state().options.static_fallback===true);assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install'].includes(c[0])).length,0);}check('terminal '+outcome+' is honest / no obsolete or grey work controls');
 }
 await mount('fr',{activity:true,task:{state:'partial',tv_state:'prepared',faceplate_state:'repair_required',error:'JSAUX_PREPARATION_REQUIRED'},jsaux:true,jsauxState:{reason:'',prepared:{ready:false}}});
 assert.equal(await button('fix-games').count(),0);assert.equal(await button('prepare-faceplate').count(),1);assert((await page.locator('[data-workflow-outputs]').innerText()).includes('TV : visuels préparés'));
 await button('prepare-faceplate').click();await button('confirm').click();await page.locator('[data-activity-state="applying"]').waitFor();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='workspace_install'&&c[1].confirm&&c[1].repair_faceplate===true));check('JSAUX-only partial result keeps TV ready / repair does not open empty game-error filter');
 await mount('fr',{activity:true,task:{state:'paused',operation:'install',error:'GAME_RUNNING',tv_state:'prepared'}});await button('resume').waitFor();assert.equal(await button('pause').count(),0);assert.equal(await page.locator('.collection-activity [role="alert"]').count(),0);assert((await page.locator('.collection-activity').innerText()).includes('Fermez le jeu'));
 await button('resume').click();await button('pause').waitFor();check('interrupted installation exposes Resume, not Pause / game-running wait is not an error');
 await mount('fr',{activity:true,jobState:'paused_game',task:{state:'paused',operation:'prepare',error:'GAME_RUNNING',tv_state:'prepared'}});await page.locator('[data-activity-state="waiting_game"]').waitFor();assert.equal(await button('resume').count(),0);assert((await page.locator('.collection-activity').innerText()).includes('reprendra automatiquement'));check('automatic game pause stays automatic even when workspace state is paused');
 await mount('fr',{activity:true,task:{state:'done',outcome:'installed',tv_state:'installed',faceplate_state:'disabled'}});assert(!(await page.locator('[data-workflow-outputs]').innerText()).includes('JSAUX'));check('never configured faceplate stays absent from successful TV-only result');
 await mount('fr',{activity:true,jsaux:true,jsauxPhase:'active',task:{state:'done',outcome:'installed',tv_state:'installed',faceplate_state:'installed'}});await page.getByRole('heading',{name:'Collection installée',exact:true}).waitFor();assert.equal(await button('cancel').count(),0);assert.equal(await page.locator('.collection-activity progress').count(),0);check('completed installation is not a 100-percent preparation when the old faceplate display is active');
 await mount('fr',{activity:true,jsaux:true,jsauxPhase:'active',task:{state:'partial',error:'PREPARATION_BUSY',tv_state:'prepared',faceplate_state:'repair_required'}});await page.locator('[data-activity-state=partial]').waitFor();assert.equal(await button('cancel').count(),0);check('faceplate refusal is a partial result to repair, not an endless preparation');
 await mount('fr',{activity:true,skipped:true,task:{state:'done',outcome:'unchanged',tv_state:'unchanged',faceplate_state:'disabled'}});assert((await page.locator('.collection-activity').innerText()).includes('jeux sans animation n’ont pas été ajoutés'));assert(!(await page.locator('.collection-activity').innerText()).includes('Aucun nouveau fichier n’était nécessaire'));check('unchanged with skipped games explains omissions, not a false no-work success');
 await mount('fr',{needsUpdate:true});assert.equal(await button('primary').innerText(),'Préparer et installer');await button('primary').click();await button('confirm').click();await page.locator('[data-activity-state="applying"]').waitFor();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='workspace_install'));assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_prepare').length,0);check('already prepared media has explicit update hint and installs without redundant preparation');
 await mount('fr',{activity:true,task:{state:'error',error:'decode_failed'}});await page.getByRole('heading',{name:'Mise à jour non terminée'}).waitFor();assert.equal(await button('cancel').count(),0);assert((await page.locator('.collection-activity').innerText()).includes('ancienne collection installée est conservée'));check('failed operation retains old collection / no false installation or Cancel button');
 await mount('fr',{sceneCount:5});assert((await page.locator('.collection-workflow').innerText()).includes('8 jeux'));assert.equal(await page.evaluate(()=>window.__collection.state().installation.scene_count),5);await button('primary').click();await page.locator('iframe.player').waitFor();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='preview_installed'));assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='preview').length,0);check('installed count is independent from prepared count / main result uses installed snapshot');
 await mount('fr',{pending:true});await button('manage-collection').click();await button('preview-installed').click();await page.locator('iframe.player').waitFor();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='preview_installed'));check('pending choices can inspect installed collection without applying them');
 for(const code of ['key_missing','probe_failed']){
  await mount('fr',{detailsFailure:code});await page.locator('.collection-card').first().click();await page.locator('[data-recovery-card] .das-recovery-primary').click();await page.getByLabel('Coller la clé API').waitFor();assert.equal(await page.locator('[data-recovery-card]').count(),0);assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['tools','workspace_prepare','workspace_install'].includes(c[0])).length,0);check('recovery '+code+' opens actual setup, without automatic repair or download');
 }
 for(const code of ['storage_limit','arbitrary_unknown']){
  await mount('fr',{detailsFailure:code});await page.locator('.collection-card').first().click();await page.locator('[data-recovery-card] .das-recovery-primary').click();await page.getByRole('heading',{name:'Stockage et assistance',exact:true}).waitFor();assert.equal(await page.locator('[data-recovery-card]').count(),0);check('recovery '+code+' opens storage and assistance');
 }
 for(const code of ['not_ready','JSAUX_SYNC_WINDOW','download_failed']){
  await mount('fr',{detailsFailure:code});await page.locator('.collection-card').first().click();await page.locator('[data-recovery-card] .das-recovery-primary').click();await button('primary').waitFor();assert.equal(await page.getByLabel('Afficher').inputValue(),'collection');assert.equal(await page.locator('[data-recovery-card]').count(),0);assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])).length,0);check('recovery '+code+' returns to collection, never starts a surprise retry');
 }
 await mount('fr',{detailsFailure:'invalid_media',error:true});await page.locator('.collection-card').first().click();await page.locator('[data-recovery-card] .das-recovery-primary').click();await page.waitForFunction(()=>document.querySelectorAll('.collection-card').length===1);assert.equal(await page.getByLabel('Afficher').inputValue(),'attention');check('choose/retry recovery filters affected games only when such issues exist');
 await mount('fr',{detailsFailure:'busy',busy:true});await page.locator('.collection-card').first().click();await page.locator('[data-recovery-card] .das-recovery-primary').click();await page.locator('[data-activity-state="preparing"]').waitFor();assert.equal(await page.locator('[data-recovery-card]').count(),0);check('busy recovery opens actual activity instead of absent Preparation tab');
 await mount('fr',{detailsFailure:'AUTH_DENIED',jsaux:true});await page.locator('.collection-card').first().click();await page.locator('[data-recovery-card] .das-recovery-primary').click();await page.locator('[data-jsaux-card]').waitFor();assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='jsaux_refresh'&&c[1].force===true).length,1);assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])).length,0);check('connection recovery forces read-only rediscovery, opens available JSAUX panel and never transfers');
 await mount('fr',{skipped:true});await page.locator('[data-skipped-info]').waitFor();
 assert.equal(await page.locator('.collection-attention').count(),0);assert((await page.locator('.collection-card').filter({hasText:'Elden Ring'}).innerText()).includes('Sans animation · non inclus'));
 await page.getByLabel('Afficher').selectOption('attention');await page.waitForFunction(()=>!document.querySelector('.collection-card'));assert.equal(await page.locator('.collection-attention').count(),1,'only the filter reminder, no missing-animation error');
 await button('allow-still-images').click();await page.waitForFunction(()=>window.__collection.state().options.static_fallback===true);assert.equal(await page.locator('[data-skipped-info]').count(),0);assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install'].includes(c[0])).length,0);check('missing animation is neutral / excluded from repairs / direct still-image preference');
 await mount('fr',{add:true});assert.equal(await page.getByRole('tab',{name:'Ajouter des jeux'}).getAttribute('aria-selected'),'true');
 calls=await page.evaluate(()=>window.__collection.calls());assert(calls.some(c=>c[0]==='workspace_library'&&c[1].filter==='installed'));
 await page.locator('.collection-card').filter({hasText:'Balatro'}).locator('.collection-customize').click();await button('save').click();
 calls=await page.evaluate(()=>window.__collection.calls());assert.equal(calls.find(c=>c[0]==='workspace_draft')[1].patch.excluded,false);check('Add destination / installed games / newly added game included');
 await mount('fr');await page.getByRole('tab',{name:'Ajouter des jeux'}).click();let additions=0;for(const name of ['Balatro','Dead Cells']){await page.getByLabel('Rechercher un jeu').fill(name);const selection=page.locator('.collection-select-main').filter({hasText:name});await selection.waitFor();await selection.click();await page.waitForFunction(count=>window.__collection.state().workspace.pending_count===count,++additions);}
 await page.getByRole('tab',{name:'Ma collection'}).click();assert.equal(await page.evaluate(()=>window.__collection.state().workspace.pending_count),2);assert((await page.locator('.collection-workflow').innerText()).includes('2 modifications à préparer'));assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_prepare').length,0);await button('primary').click();assert((await page.locator('.collection-confirm').innerText()).includes('Les visuels inchangés sont réutilisés'));await button('confirm').click();await button('pause').waitFor();assert.equal((await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_prepare')[1].mode,'missing');check('two successive direct additions accumulate two pending games / one explicit incremental preparation');
 await mount();await page.locator('.collection-card').first().click();await button('pick-animation').click();await button('asset-100').waitFor();
 await button('asset-100').focus();await page.keyboard.press('Escape');await button('pick-animation').waitFor();assert.equal(await page.locator('.collection-detail').count(),1);
 await button('pick-animation').focus();await page.keyboard.press('Escape');await page.getByRole('tab',{name:'Ma collection'}).waitFor();check('Back exits candidates then sheet, not entire plugin');
 await page.getByRole('tab',{name:'Réglages'}).click();await button('settings-appearance').click();
 await page.getByLabel('Présentation de la collection').selectOption('compact');await button('back').click();await page.getByRole('tab',{name:'Ma collection'}).click();
 assert.equal(await page.locator('.collection-grid.compact').count(),1);check('saved compact layout');
 for(const width of [1280,960,800])for(const native of [false,true]){
 await page.setViewportSize({width,height:800});await mount('fr',{native,unprepared:true});await page.locator('.collection-card').first().click();
 await button('pick-animation').waitFor();await page.locator('.collection-sheet-preview iframe.player').waitFor();
 assert.equal(await page.locator('.collection-sheet-preview').getByRole('button',{name:/Précédent|Suivant|Fermer l’aperçu/}).count(),0,'single-game inline player has no collection navigation or global close');
 const sourcePreview=(await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='preview_recipe');assert(sourcePreview,'an unprepared sheet opens the actual animated source player');
 assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','prepare','workspace_draft'].includes(c[0])).length,0,'preview never prepares or saves');
 const rows=await page.locator('.collection-field').evaluateAll(nodes=>nodes.slice(0,3).map(n=>{const label=n.querySelector('.collection-label'),action=n.querySelector('[data-collection-focus]');return {label:label.getBoundingClientRect().width,action:action.getBoundingClientRect().width,height:n.getBoundingClientRect().height};}));
 for(const [index,row] of rows.entries()){assert(row.label>=140);assert(row.height<(index===0?170:120));if(index>0)assert(row.action<=140);}
 const background=page.locator('.collection-background-actions');assert.equal(await background.getByRole('button').count(),2);const backgroundBounds=await background.evaluate(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right};});for(const b of await background.getByRole('button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right};}))){assert(b.left>=backgroundBounds.left-1&&b.right<=backgroundBounds.right+1);}
 assert.equal(await button('back').evaluate(e=>e.getBoundingClientRect().width),112);
 assert.equal(await page.getByRole('button',{name:/classic|classique/i}).count(),0);
 await page.screenshot({path:'out/ui/collection/detail-'+width+'-'+native+'.png'});check('unprepared illustrated sheet / bounded native actions '+width+'/'+native);
 }
 await mount('fr',{unprepared:true});await page.locator('.collection-card').first().click();await page.locator('.collection-sheet-preview iframe.player').waitFor({timeout:10000});
 await page.getByLabel('Cadrage').first().selectOption('16:10',{timeout:10000});
 assert.equal(await page.getByLabel('Cadrage').first().inputValue(),'16:10');
 await page.waitForFunction(()=>window.__collection.calls().filter(c=>c[0]==='preview_recipe').length>=2,null,{timeout:10000});await page.locator('.collection-sheet-preview iframe.player').waitFor({timeout:10000});
 calls=await page.evaluate(()=>window.__collection.calls());assert.equal(calls.filter(c=>c[0]==='preview_recipe').at(-1)[1].patch.crop.mode,'16:10');assert.equal(calls.filter(c=>['workspace_prepare','workspace_draft'].includes(c[0])).length,0);check('animated source preview before preparation / current crop without saving');
 assert.equal(await page.getByLabel('Comparer la version installée').count(),0,'a newly unprepared game cannot promise installed membership');
 await mount('fr');await page.locator('.collection-card').first().click();await page.locator('.collection-sheet-preview iframe').waitFor();await page.getByLabel('Comparer la version installée').check();await page.waitForFunction(()=>window.__collection.calls().some(c=>c[0]==='preview_installed'&&c[1].appid));await page.getByLabel('Comparer la version installée').uncheck();await page.waitForFunction(()=>window.__collection.calls().filter(c=>c[0]==='preview_recipe').length>=2);check('game sheet distinguishes installed snapshot from unsaved choices, without preparation');
 await mount('fr',{add:true});await page.getByLabel('Source des jeux').selectOption('online');
 await page.getByLabel('Rechercher un jeu').fill('Ba');await page.waitForTimeout(500);
 assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='browse_search').length,0);
 await page.getByLabel('Rechercher un jeu').fill('Baldur');await page.waitForFunction(()=>document.querySelectorAll('.collection-card').length===1);
 await page.locator('.collection-customize').click();await button('save').waitFor();check('live online search at three characters / one field / opens sheet');
 await mount('fr',{add:true});await page.getByLabel('Source des jeux').selectOption('online');
 await page.getByLabel('Rechercher un jeu').fill('slow');await page.waitForTimeout(450);await page.getByLabel('Rechercher un jeu').fill('Hades');await page.waitForTimeout(1600);
 assert.equal(await page.locator('.collection-card').count(),1);assert((await page.locator('.collection-card').innerText()).includes('Hades'));check('late response cannot replace newer search');
 await page.getByLabel('Source des jeux').selectOption('top');await page.locator('.collection-rank').first().waitFor();
 assert((await page.locator('.collection-rank').first().innerText()).includes('#1'));check('Steam Top order, rank and timestamp');
 await mount('fr',{add:true,topError:true});await page.getByLabel('Source des jeux').selectOption('top');await button('retry-discovery').waitFor();assert((await page.locator('[role="status"]').filter({hasText:'Connexion Steam non vérifiée'}).innerText()).includes('Connexion Steam non vérifiée'));await button('retry-discovery').click();await page.locator('.collection-rank').first().waitFor();check('structured Python failure is readable and retry restores Top without leaving page');
 await page.screenshot({path:'out/ui/collection/top-steam.png'});
 await page.getByLabel('Source des jeux').selectOption('online');await page.getByLabel('Rechercher un jeu').fill('offline');await page.getByRole('status').filter({hasText:'La recherche Steam est indisponible'}).waitFor();assert.equal(await page.locator('.collection-card').count(),0);check('network failure is explicit, no stale search result');
 await mount('fr',{classic:true});assert.equal(await page.getByRole('tab').count(),3);assert.equal(await page.getByRole('button',{name:/classique|classic/i}).count(),0);check('saved classic preference cannot restore removed interface');
 await page.getByRole('tab',{name:'Réglages'}).click();await button('settings-assistance').click();await page.getByRole('button',{name:'Stockage et imports'}).click();await page.getByLabel('Cadence de fluidification').waitFor();check('advanced controls remain available without classic interface');
 await button('back').evaluate(e=>e.focus({preventScroll:true}));await page.locator('[data-native-scroll-panel]').evaluate(e=>{e.scrollTop=35;});await page.keyboard.press('ArrowUp');assert.equal(await page.locator('[data-native-scroll-panel]').evaluate(e=>e.scrollTop),0);check('Up on first content action reveals heading without leaving route');
 await mount('fr',{missing:true});await button('primary').click();assert.equal(await page.locator('.collection-settings-form').count(),1);await page.getByLabel('Coller la clé API').waitFor();await page.screenshot({path:'out/ui/collection/setup-fr.png'});check('missing setup opens real setup controls');
 await mount('fr');await page.getByRole('tab',{name:'Réglages'}).click();const settingsWidth=await page.locator('.collection-settings').evaluate(node=>node.getBoundingClientRect().width);await page.screenshot({path:'out/ui/collection/settings-fr.png'});await button('settings-updates').click();await page.locator('[data-updates-panel]').waitFor();assert.equal(await page.locator('[data-updates-panel]').evaluate(node=>node.getBoundingClientRect().width),settingsWidth);await page.screenshot({path:'out/ui/collection/updates-fr.png'});check('settings and update panels share a stable padded content width');
 await mount('fr',{error:true});assert((await page.locator('.collection-workflow').innerText()).includes('Vérifiez les jeux concernés'));await button('primary').click();await page.waitForFunction(()=>document.querySelectorAll('.collection-card').length===1);await page.locator('.collection-card').click();assert.equal(await page.locator('.collection-attention').count(),1);check('error directs to actual game needing repair');
 await mount('fr',{jsaux:true});assert.equal(await button('prepare-batches').count(),1);
 await page.screenshot({path:'out/ui/collection/jsaux-attention.png'});check('JSAUX capacity fallback offers one preparation action');
 await page.getByRole('tab',{name:'Réglages'}).click();await button('settings-jsaux').click();await page.getByLabel('Transition Faceplate JSAUX').selectOption('slide');
 assert.equal(await page.getByLabel('Cadrage Faceplate JSAUX').inputValue(),'square');
 await page.getByLabel('Cadrage Faceplate JSAUX').selectOption('fill');
 assert.equal(await page.getByLabel('Cadrage Faceplate JSAUX').inputValue(),'fill');
 assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='jsaux_configure'&&c[1].patch.framing==='fill'));
 assert.equal(await page.getByRole('button',{name:'Réparer les images JSAUX',exact:true}).count(),0);
 assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_install','jsaux_prepare','workspace_prepare'].includes(c[0])).length,0);
 await button('back').click();await page.getByRole('tab',{name:'Ma collection'}).click();await button('primary').waitFor();assert.equal(await button('independent-choice').count(),0);
 assert.equal(await page.locator('[data-ui-part=faceplate-preparation-status][data-status=pending]').count(),1);
 await button('primary').click();await button('confirm').click();await page.locator('[data-activity-state="applying"]').waitFor();
 const repairRequest=(await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_install');assert.equal(repairRequest[1].confirm,true);
 assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['jsaux_prepare','workspace_prepare'].includes(c[0])).length,0);check('JSAUX adjustments live beside preparation, Back returns focus, one collection update applies them');
 for(const lang of ['fr','en']){
  await mount(lang,{jsaux:true});
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();
  await button('settings-jsaux').click();
  const framing=page.getByLabel(lang==='fr'?'Cadrage Faceplate JSAUX':'Faceplate JSAUX framing');
  assert.equal(await framing.inputValue(),'square');
  await framing.selectOption('fill');await page.waitForTimeout(80);
  assert.equal(await framing.inputValue(),'fill');
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_install','jsaux_prepare','workspace_prepare'].includes(c[0])).length,0);
  await page.screenshot({path:`out/ui/collection/framing-fill-${lang}.png`});
  await button('back').click();await page.getByRole('tab',{name:lang==='fr'?'Ma collection':'My collection',exact:true}).click();
  await page.locator('.collection-card').first().click();
  assert.equal(await page.locator('[data-faceplate-crop]').count(),0);
  await button('pick-panel').click();await button('asset-400').click();
  const vertical=page.getByLabel(lang==='fr'?'Cadrage vertical':'Vertical framing',{exact:true});
  assert.equal(await vertical.inputValue(),'50');
  for(let n=0;n<25;n++)await vertical.press('ArrowLeft');
  const chosenCrop=Number(await vertical.inputValue());
  assert(chosenCrop>=20&&chosenCrop<=30,'D-pad changes vertical crop by approximately 25 steps');
  await button('use-panel').click();await button('save').click();
  const edited=(await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_draft')[1].patch;
  assert.deepEqual(edited.faceplate_crop,{x:50,y:chosenCrop});assert.deepEqual(edited.crop,{mode:'inherit',x:50,y:50});
  assert.equal(await button('centre-panel').count(),0);
  check('Faceplate crop is edited beside its chosen image, preserves TV framing, and saves without preparation '+lang);
 }
 for(const lang of ['fr','en'])for(const reason of ['STEAM_INACTIVE','STEAM_STATE_STALE','ACTIVATION_CLOSED','FLASH_DEFERRED']){
  await mount(lang,{jsaux:true,jsauxState:{reason,installed:true,prepared:{ready:true,sync_admissible:true}}});
  assert.equal(await page.locator('.collection-faceplate.needs-action,.collection-attention').count(),0);
  assert.equal(await page.locator('[data-ui-part=faceplate-preparation-status]').count(),1);assert.equal(await button('jsaux').count(),0);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_install','jsaux_prepare','workspace_prepare'].includes(c[0])).length,0);
  check('neutral JSAUX '+reason+' / no unsolicited preparation '+lang);
 }
 for(const width of [1280,1920])for(const lang of ['fr','en']){
  await page.setViewportSize({width,height:width===1920?1080:800});
  await mount(lang,{jsaux:true,jsauxState:{reason:'STEAM_INACTIVE',installed:true,prepared:{ready:true,sync_admissible:true}}});
  await page.screenshot({path:`out/ui/collection/unified-jsaux-${lang}-${width}.png`});
  assert.equal(await page.locator('.collection-faceplate.needs-action,.collection-attention').count(),0);
  assert.equal(await page.getByRole('tab',{selected:true}).innerText(),lang==='fr'?'Ma collection':'My collection');
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();await button('settings-jsaux').click();await page.getByRole('heading',{name:'Faceplate JSAUX',exact:true}).waitFor();
  assert.equal(await page.getByLabel(lang==='fr'?'Mode de lecture':'Playback mode').count(),1);
  assert.equal(await page.getByLabel(lang==='fr'?'Transition Faceplate JSAUX':'Faceplate JSAUX transition').count(),1);
  assert.equal(await page.locator('[data-jsaux-duration] input').count(),0);
  await page.screenshot({path:`out/ui/collection/unified-jsaux-adjust-${lang}-${width}.png`});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);check('JSAUX adjustments in collection / compact sync controls '+lang+' '+width);
 }
 await page.setViewportSize({width:1280,height:800});
 await mount('fr',{jsaux:true,jsauxState:{reason:'BROKER_UNAVAILABLE',detected:false,compatible:false}});
 assert.equal(await button('jsaux').count(),0);assert.equal(await page.locator('[data-ui-part=faceplate-preparation-status]').count(),0);
 await page.getByRole('tab',{name:'Réglages'}).click();assert.equal(await button('settings-jsaux').count(),0);check('disconnected Faceplate has no routine command or missing-device card');
 await mount('fr',{jsaux:true,jsauxState:{reason:'AUTH_DENIED'}});await button('check-gca').click();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='jsaux_refresh'&&c[1].force));
 check('connection check remains available inside Faceplate settings');
 await mount('fr',{jsaux:true});
 await page.getByRole('tab',{name:'Réglages'}).click();await button('settings-assistance').click();await page.getByRole('button',{name:'Reconnecter GabeCubeAura'}).click();assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='jsaux_refresh'&&c[1].force));
 await page.getByRole('button',{name:'Enregistrer un diagnostic local',exact:true}).click();assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='diagnostic').length,1);assert.equal(await page.getByRole('button',{name:'Envoyer le diagnostic sur GitHub',exact:true}).count(),0);check('connection retry is read-only and complete diagnostics save locally');
 await mount();const beforeIdle=(await page.evaluate(()=>window.__collection.calls())).length;await page.waitForTimeout(2500);assert.equal((await page.evaluate(()=>window.__collection.calls())).length,beforeIdle);check('idle interface has no state poll or periodic conversion');
 await mount();await button('primary').click();await page.locator('iframe.player').waitFor();assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='preview_installed').length,1);
 const playerBounds=await page.locator('iframe.player').evaluate(node=>{const r=node.getBoundingClientRect();return {width:r.width,height:r.height};});
 assert(Math.abs(playerBounds.width/playerBounds.height-16/9)<0.01,'prepared preview preserves its actual 16:9 viewport');assert(playerBounds.height<=360,'preview remains bounded without distorting its aspect ratio');
 assert.equal(await page.getByRole('button',{name:/plein écran|fullscreen/i}).count(),0);await button('back').focus();await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('iframe'));check('bounded actual Player / no fullscreen / closes on Back');
 await mount('en',{quick:true,jsaux:true});assert.equal(await page.locator('#das-compact-root').getByRole('button').count(),2);assert.equal(await page.locator('#das-compact-root').getByRole('button',{name:'Settings',exact:true}).count(),0);assert.equal(await page.locator('[data-das-quick-card] .das-quick-meta').count(),1);assert.equal(await page.locator('.das-quick>.collection-quick-note').count(),0);await page.getByRole('button',{name:'Open my collection',exact:true}).click();await page.getByRole('button',{name:'Add games',exact:true}).click();assert.deepEqual((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='open').map(c=>c[1].tab),['library','library']);check('two QAM navigation actions without duplicate Settings / JSAUX state grouped inside status');
 await mount('en',{quick:true,busy:true});await page.getByRole('button',{name:'View progress',exact:true}).click();assert.equal((await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='open')[1].tab,'preparation');check('busy QAM opens progress instead of promising to prepare');
 await mount('fr',{candidateThumb:fixturePNG});await page.locator('.collection-card').first().click();await page.waitForFunction(()=>window.__collection.imageReport().events.some(e=>e.stage==='ready'&&e.source==='sgdb'));assert(fixtureRequests.includes(fixturePNG));assert.equal(await button('asset-100').count(),0);check('actual still bytes preloaded on sheet open before candidate picker');
 await page.evaluate(urls=>window.__collection.images(urls),[fixtureLegacy,fixtureWebP]);await page.waitForFunction(()=>document.querySelectorAll('[data-image-state="ready"]').length===2);assert.equal(await page.locator('canvas').count(),1);assert.equal(await page.locator('img').count(),1);assert(fixtureRequests.includes(fixtureWebP)&&fixtureRequests.includes(fixtureLegacy));check('legacy HTTPS PNG accepted and WebP thumb freezes to canvas without CORS headers');
 await page.setViewportSize({width:1280,height:800});await mount('fr',{jsaux:true});await page.locator('.collection-card').first().click();await page.locator('.collection-sheet-preview iframe').waitFor();
 const leftSave=button('save');await leftSave.focus();
 await leftSave.evaluate(node=>node.dispatchEvent(new CustomEvent('das-test-direction',{bubbles:true,cancelable:true,detail:{button:12}})));
 assert.equal(await page.evaluate(()=>document.activeElement.closest('[data-detail-column]')?.dataset.detailColumn),'settings');
 await button('pick-animation').focus();await button('pick-animation').evaluate(node=>node.dispatchEvent(new CustomEvent('das-test-direction',{bubbles:true,cancelable:true,detail:{button:11}})));
 assert.equal(await page.evaluate(()=>document.activeElement.closest('[data-detail-column]')?.dataset.detailColumn),'preview');check('D-pad bridges both sheet columns through native focus path');
 const actionGaps=await page.locator('.collection-sheet-save').evaluate(node=>{const boxes=[...node.querySelectorAll('[data-collection-focus]')].map(e=>e.getBoundingClientRect());return {gap:parseFloat(getComputedStyle(node).gap),space:boxes[1].left-boxes[0].right,vertical:boxes[1].top-boxes[0].bottom};});assert(actionGaps.gap>=12);assert(actionGaps.space>=10||actionGaps.vertical>=10);check('JSAUX and Save actions cannot touch, native controls included');
 assert.equal(await page.locator('[data-detail-column="preview"]').getByRole('button',{name:/^(Pause|Lecture)$/}).count(),0);
 assert.equal(await button('pick-panel').evaluate(e=>e.closest('[data-detail-column]')?.getAttribute('data-detail-column')),'preview');
 await page.getByLabel('Position du logo').selectOption('bottom-right');
 await page.getByLabel('Position de la jaquette').selectOption('top-left');assert.equal(await page.getByLabel('Position du logo').inputValue(),'bottom-right');assert.equal(await page.getByLabel('Position du logo sans jaquette').count(),0);assert.equal(await page.getByRole('option',{name:'À côté de la jaquette',exact:true}).count(),0);await button('save').click();const savedCorners=(await page.evaluate(()=>window.__collection.calls())).find(c=>c[0]==='workspace_draft')[1].patch;assert.equal(savedCorners.cover_position,'top-left');assert.equal(savedCorners.branding.position,'bottom-right');check('game sheet keeps logo and cover independently selectable and saves both corners, without compact transport');
 await mount('fr',{jsaux:true});await page.locator('.collection-card').first().click();
 await button('pick-animation').click();await button('asset-100').waitFor();await button('asset-100').focus();await page.waitForFunction(()=>document.querySelector('.candidate-motion')?.naturalWidth===1);const frames=[];for(let i=0;i<4;i++){frames.push(await page.locator('.candidate-artwork').screenshot());await page.waitForTimeout(95);}assert(frames.some(frame=>!frame.equals(frames[0])),'focused GIF visibly animates');
 const sourceCalls=(await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='candidate_preview'&&c[1].motion);assert.equal(sourceCalls.length,1);check('focused candidate plays real GIF frames with one bounded derivative request');
 await mount('fr',{candidateMany:true,candidateThumb:'https://cdn.steamgriddb.com/thumb/missing.webp'});await page.locator('.collection-card').first().click();await button('pick-animation').click();await button('asset-100').waitFor();
 await page.waitForFunction(()=>document.querySelectorAll('.collection-candidate .collection-picture[data-image-state="ready"]').length===8);
 await button('asset-100').focus();await page.waitForFunction(()=>document.querySelectorAll('.candidate-motion').length===1);await page.waitForTimeout(400);
 const unfocused=page.locator('[data-collection-focus="asset-101"] .candidate-artwork');const fixedA=await unfocused.screenshot();await page.waitForTimeout(220);assert.deepEqual(await unfocused.screenshot(),fixedA);
 await button('asset-101').focus();await page.waitForTimeout(600);assert.equal(await page.locator('.candidate-motion').count(),1);assert.equal(await button('asset-100').locator('.candidate-motion').count(),0);assert.equal(await button('asset-100').locator('.collection-picture img').count(),1);
 await button('asset-101').locator('.candidate-motion').evaluate(node=>node.dispatchEvent(new Event('error')));await page.waitForFunction(()=>!document.querySelector('.candidate-motion'));assert.equal(await button('asset-101').locator('.collection-picture img').count(),1);check('browser playback failure removes motion and restores its retained still');
 await button('asset-none').focus();await page.waitForTimeout(100);assert.equal(await page.locator('.candidate-motion').count(),0);check('eight backend stills with unavailable remote thumbnails / only focused card animates / blur restores fixed image');
 await mount('fr',{candidateMany:true,motionError:true});await page.locator('.collection-card').first().click();await button('pick-animation').click();await button('asset-107').waitFor();await button('asset-107').focus();await page.getByText('Aperçu fixe · l’original reste sélectionnable',{exact:true}).waitFor();
 assert.equal(await button('asset-107').locator('.collection-picture img').count(),1);assert.equal(await page.getByText('Ce fichier dépasse la limite de l’aperçu, choisissez une animation plus légère…',{exact:true}).count(),0);await button('asset-107').click();await button('save').waitFor();check('failed motion retains still and selection, without instructing user to discard original');
 await mount('fr',{jsaux:true,square:true,candidateThumb:fixtureSquare});await page.locator('.collection-card').first().click();await button('pick-panel').click();await button('asset-400').waitFor();await page.waitForFunction(()=>document.querySelector('.collection-candidate .collection-picture img')?.naturalWidth===32);const fit=await page.locator('.collection-candidate .collection-picture').evaluate(node=>({ratio:node.getBoundingClientRect().width/node.getBoundingClientRect().height,fit:getComputedStyle(node.querySelector('img')).objectFit}));assert(Math.abs(fit.ratio-460/215)<.02);assert.equal(fit.fit,'contain');check('square candidates keep gallery height without cropping their content');
 await mount();const header=await page.locator('[role="tablist"]').boundingBox();for(const bumper of [6,6,5,5,6,5]){await page.locator('.native-tabs').evaluate((node,button)=>node.dispatchEvent(new CustomEvent('das-test-bumper',{bubbles:true,detail:{button}})),bumper);await page.waitForTimeout(220);const box=await page.locator('[role="tablist"]').boundingBox();assert.equal(box.y,header.y);assert.equal(box.x,header.x);assert.equal(await page.locator('.collection-frame').evaluate(node=>node.scrollTop),0);}check('repeated L1/R1 tab changes keep outer header fixed');
 const beforeBack=await page.evaluate(()=>window.__dasBackCount||0);await page.locator('.collection-frame').evaluate(node=>node.dispatchEvent(new CustomEvent('das-test-cancel',{bubbles:true,cancelable:true})));assert.equal(await page.evaluate(()=>window.__dasBackCount),beforeBack+1);check('B leaves DAS through Steam navigation at final level');
 await mount();await page.locator('.collection-card').first().click();await page.locator('iframe.player').waitFor();await page.waitForTimeout(12500);assert.equal(await page.getByText('L’aperçu ne répond pas. Fermez-le puis réessayez.',{exact:true}).count(),0);check('status handshake recovers a missed initial iframe message without false timeout');
 const popupEvent=page.waitForEvent('popup');await page.evaluate(()=>window.__collection.popup());const popup=await popupEvent;await popup.getByRole('button',{name:'Pause',exact:true}).click();await popup.getByRole('button',{name:'Lecture',exact:true}).waitFor();await popup.getByRole('button',{name:'Lecture',exact:true}).click();await popup.getByRole('button',{name:'Pause',exact:true}).waitFor();await popup.close();check('production Player mounted in a different owner window receives real pause/play acknowledgement');

 }
 }
 }
 }
 }
 }
 assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
 await fs.writeFile('out/ui/collection/validation.json',JSON.stringify({evidence:'Actual production components with browser-only Decky/RPC adapters. Not SteamOS or hardware.',results,errors,externalRequests:requests},null,2));
 }
 console.log(`PASS ${results.length} production React browser scenarios; no external requests; no page errors.`);
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
