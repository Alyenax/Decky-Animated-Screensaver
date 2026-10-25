// Browser cascade regression with sentinel Steam styles, not real SteamOS.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import ts from 'typescript';
const root=process.cwd(),gca=process.env.DAS_TEST_GCA_ROOT;
if(!gca)throw new Error('DAS_TEST_GCA_ROOT must identify the GBA checkout');
const require=createRequire(path.join(root,'package.json')),{chromium}=require('playwright');
const classes=new Proxy({}, {get:(_,key)=>`steam_${String(key)}_newhash additional_token`});
const decky={gamepadDialogClasses:classes,gamepadSliderClasses:classes,quickAccessControlsClasses:classes,gamepadTabbedPageClasses:classes,findClassModule:()=>classes};
async function load(file,imports={}){
 const source=await fs.readFile(file,'utf8'),exports={};
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports,require:name=>name==='@decky/ui'?decky:imports[name]??{}},{filename:file});
 return exports;
}
const native=await load(path.join(root,'src/native_ui.ts'));
assert.equal(native.nativeClassSelector('.scope',undefined,'Field'),'.scope [data-das-native-unavailable="Field"]');
assert.equal(native.nativeClassSelector('.scope',{Field:'new_hash second_hash'},'Field'),'.scope [class~="new_hash"][class~="second_hash"]');
const settingsNative=await load(path.join(gca,'src/settings_native.ts'));
const styles=[
 (await load(path.join(gca,'src/components/compact_quick_style.ts'))).COMPACT_QUICK_CSS,
 (await load(path.join(gca,'src/components/QuickAction.tsx'))).QUICK_CONTROL_CSS,
 (await load(path.join(gca,'src/settings_theme.ts'),{'./settings_native':settingsNative})).SETTINGS_CSS,
 (await load(path.join(root,'src/QuickControls.tsx'))).QUICK_CONTROL_CSS,
 (await load(path.join(root,'src/theme.ts'))).CSS,
 (await load(path.join(root,'src/collectionTheme.ts'),{'./native_ui':native})).COLLECTION_CSS,
].join('\n');
const baseline=`body{font:16px sans-serif;background:#171e28;color:white;margin:0}*{box-sizing:border-box}
.DialogButton,.steam_Field_newhash,.native-toggle,.native-slider,input{background:rgb(37,48,59);color:rgb(221,232,243);border:2px solid rgb(99,110,121);border-radius:7px;box-shadow:inset 0 0 0 1px rgb(11,22,33);outline:0px solid transparent}
.DialogButton.gpfocus,.steam_Field_newhash.gpfocus{background:rgb(211,222,233);color:rgb(22,33,44);outline:3px solid rgb(55,166,177);box-shadow:inset 0 0 0 2px rgb(122,133,144)}
.DialogButton:disabled{background:rgb(77,88,99);color:rgb(133,144,155);opacity:.45}
.DialogButton{display:block;min-height:40px;max-width:100%;font:inherit}
.fixture{width:100%;max-width:340px}#gca-settings-root.fixture,.das-route.fixture{position:relative;inset:auto;max-width:100%;height:600px}`;
const controls=(extra='')=>`<button class="DialogButton ${extra}">Native action</button><div class="steam_Field_newhash additional_token"><span>Native field</span><div class="native-toggle">Toggle</div><div class="native-slider">Slider</div><input aria-label="Native text" value="Steam" /></div>`;
const html=`<style id="steam">${baseline}</style><div id="gca-compact-root" class="fixture">${controls('gca-compact-wide')}<div class="gca-compact-line"><span>Ambience</span><button class="DialogButton gca-quick-choice-trigger">Atmosphere</button></div></div><div id="das-compact-root" class="fixture">${controls('das-quick-action')}</div><div id="gca-settings-root" class="fixture"><div class="gca-native-field">${controls('gca-native-button')}</div></div><div class="das-route fixture"><div class="das collection-frame"><div class="collection-content">${controls('collection-action')}</div></div></div><style id="plugin"></style>`;
const browser=await chromium.launch({executablePath:process.env.DAS_TEST_BROWSER||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 for(const width of [320,340,736,800,1280]){
  await page.setViewportSize({width,height:900});await page.setContent(html);
  for(const state of ['normal','focused','disabled']){
   await page.evaluate(state=>document.querySelectorAll('button').forEach(button=>{button.disabled=state==='disabled';button.classList.toggle('gpfocus',state==='focused');}),state);
   const paint=()=>Array.from(document.querySelectorAll('button,.steam_Field_newhash,.native-toggle,.native-slider,input')).map(node=>{const s=getComputedStyle(node);return {background:s.backgroundColor,color:s.color,border:s.border,borderRadius:s.borderRadius,outline:s.outline,shadow:s.boxShadow,opacity:s.opacity};});
   await page.locator('#plugin').evaluate(node=>node.textContent='');const before=await page.evaluate(paint);
   await page.locator('#plugin').evaluate((node,css)=>node.textContent=css,styles);const after=await page.evaluate(paint);
   assert.deepEqual(after,before,`native paint ${width}/${state}`);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`horizontal overflow ${width}/${state}`);
  }
 }
 assert.deepEqual(errors,[]);
 console.log('PASS: native normal/focused/disabled paint preserved on GBA QAM/settings and DAS QAM/Studio at 5 widths (15 cascade scenarios); dynamic/missing class resolution; no page errors or horizontal overflow. Browser sentinel evidence only.');
}finally{await browser.close();}
