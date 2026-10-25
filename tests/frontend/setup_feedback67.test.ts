import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import {createElement,Fragment} from 'react';
const source=readFileSync(new URL('../../src/SettingsPanels.tsx',import.meta.url),'utf8');
const nodes=(n:any):any[]=>!n?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
const text=(n:any):string=>n==null?'':typeof n==='string'||typeof n==='number'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const flush=()=>new Promise(r=>setImmediate(r));
function harness(request:()=>Promise<any>,fr=false){
 const hooks:any[]=[];let index=0;const effects:(()=>any)[]=[];
 const tr=(en:string,french:string)=>fr?french:en;
 const context:any={React:{createElement,Fragment},WeakMap,JSON,Math,tr,
 useRef:(v:any)=>{const i=index++;return hooks[i]??={current:v};},
 useState:(v:any)=>{const i=index++;if(!(i in hooks))hooks[i]=typeof v==='function'?v():v;return [hooks[i],(next:any)=>hooks[i]=next];},
 useEffect:(fn:()=>any,deps:any[])=>{const i=index++,old=hooks[i];if(!old||deps.some((d,j)=>d!==old[j])){hooks[i]=deps;effects.push(fn);}},
 jsauxVisible:()=>false,jsauxBusy:()=>false,busy:()=>false,shouldPoll:()=>false,faceplateSummary:()=>null,faceplateEffectiveMode:()=>'',stageText:(x:string)=>x,
 PanelSection:'section',PanelSectionRow:'row',TextField:'input',ButtonItem:'button',ToggleField:'toggle',DropdownItem:'select',Field:'field',Focusable:'focus',DialogButton:'dialog',RecoveryCard:'recovery'};
 const run=async()=>request();
 vm.runInNewContext(ts.transpileModule(source.replace(/^import .*$/gm,'').replace('export function SettingsPanels','function SettingsPanels'),{compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText+'\nthis.render=SettingsPanels;',context);
 return {render(){index=0;const tree=context.render({state:{key_configured:true,connection:'saved',options:{static_fallback:true},media_tools:{available:true,installed:true,state:'ready'},job:{state:'idle'}},run,saving:false,section:'setup',onCollection:()=>{}});while(effects.length)effects.shift()?.();return nodes(tree);}};
}
test('Setup puts numbered optional import last, with emphasis in both languages',()=>{
 for(const fr of [false,true]){const ui=harness(async()=>({}),fr),view=ui.render();const headings=view.filter(n=>n.type==='h2');assert.equal(headings.length,3);assert.match(text(headings[0]),/^1 · SteamGridDB/);assert.match(text(headings[1]),/^2 · /);assert.match(text(headings[2]),/^3 · /);
 const optional=nodes(headings[2]).find(n=>n.type==='strong');assert.equal(optional.props.style.color,'#ffd27a');assert.equal(text(optional),fr?'Facultatif':'Optional');
 assert(view.some(n=>n.type==='strong'&&nodes(n).some(child=>child.type==='u'&&text(child).startsWith(fr?'Ignorez cette étape':'Skip this'))));
 const button=view.find(n=>n.type==='button'&&n.props.label===(fr?'Importer les jeux possédés':'Import owned games'));assert.equal(button,view.filter(n=>n.type==='button').at(-1));
 }
});
test('saved key test blocks repeat clicks and shows a green tick only for verified result',async()=>{
 let calls=0,done:any;const ui=harness(()=>{calls++;return new Promise(r=>done=r);});ui.render();const button=ui.render().find(n=>n.props?.label==='Test saved key');button.props.onClick();button.props.onClick();assert.equal(calls,1);assert(ui.render().find(n=>n.props?.label==='Test saved key').props.disabled);
 done({key_configured:true,connection:'verified'});await flush();const result=ui.render().find(n=>n.props?.['data-saved-key-result']==='verified');assert.equal(text(result),'✓ Saved key verified.');assert.equal(result.props.style.color,'#8bd49c');assert.equal(result.props.role,'status');
});
test('failure, missing result and unverified result cannot show a successful key test',async()=>{
 for(const outcome of [undefined,{key_configured:true,connection:'saved'},new Error('Offline')]){
 const ui=harness(async()=>{if(outcome instanceof Error)throw outcome;return outcome;},true);ui.render();ui.render().find(n=>n.props?.label==='Tester la clé enregistrée').props.onClick();await flush();const view=ui.render();assert(!view.some(n=>n.props?.['data-saved-key-result']==='verified'));assert(view.some(n=>n.props?.role==='alert'));assert.equal(view.find(n=>n.props?.label==='Tester la clé enregistrée').props.disabled,false);
 }
});


test('assistance omits manual SteamGridDB IDs and retains storage and recovery actions',()=>{
 const assistance=readFileSync(new URL('../../src/AssistancePanel.tsx',import.meta.url),'utf8');
 assert.doesNotMatch(assistance,/SteamGridDB game ID|Identifiant du jeu SteamGridDB|Add by SteamGridDB ID|setManual|TextField/);
 for(const action of ['Verify library','Verify Steam files','Clear unused cache','Import previous GCA library'])assert(assistance.includes(action));
 const collection=readFileSync(new URL('../../src/CollectionStudio.tsx',import.meta.url),'utf8');assert.match(collection,/Search games|Search for games|Search/);
});
