import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {createElement,Fragment} from 'react';

const transpile=(file:string)=>ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8')
  .replace(/^import[\s\S]*?;\n/gm,'').replace(/^export /gm,''),
  {compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
const source=transpile('../../src/UpdatesPanel.tsx');
const i18n=transpile('../../src/i18n.ts');
function harness(locale='en'){
  let cursor=0,serial=0;
  const values:any[]=[],deps:any[]=[],effects:Function[]=[],cleanups:Function[]=[];
  const calls:string[]=[],timers=new Map<number,Function>();
  let hold:Promise<unknown>|undefined;
  const state:any={channel:'stable',auto_check:true,interval_minutes:1440,phase:'idle',error:'',
    auth:{state:'disconnected',user_code:'',verification_uri:'',expires_at:0},repository:'Alyenax/Decky-Animated-Screensaver',
    repository_state:'unchecked',installed_version:'0.1.0-alpha.11',available_version:'',available:false,checked_at:0,percent:0,confirmation:''};
  const run=async(action:string)=>{calls.push(action);await hold;};
  const context=vm.createContext({React:{createElement,Fragment},URL,
    localStorage:{getItem:()=>locale},navigator:{language:locale},useSyncExternalStore:()=>{},
    Navigation:{NavigateToExternalWeb:(url:string)=>calls.push(url)},
    useRef(initial:any){const i=cursor++;if(!(i in values))values[i]={current:initial};return values[i];},
    useState(initial:any){const i=cursor++;if(!(i in values))values[i]=initial;return[values[i],(value:any)=>values[i]=value];},
    useEffect(fn:Function,next:any[]){const i=cursor++;if(!deps[i]||next.some((v,n)=>v!==deps[i][n])){cleanups[i]?.();deps[i]=next;effects.push(()=>cleanups[i]=fn());}},
    setInterval(fn:Function){timers.set(++serial,fn);return serial;},clearInterval:(id:number)=>timers.delete(id),
    ButtonItem:'button',DropdownItem:'dropdown',PanelSection:'section',PanelSectionRow:'row',ToggleField:'toggle'});
  vm.runInContext(i18n+'\n'+source+'\nthis.component=UpdatesPanel;',context);
  const nodes=(tree:any):any[]=>Array.isArray(tree)?tree.flatMap(nodes):tree&&typeof tree==='object'?[tree,...nodes(tree.props?.children)]:[];
  const render=()=>{cursor=0;const tree=context.component({state,run,saving:false});effects.splice(0).forEach(fn=>fn());return tree;};
  const button=(tree:any,label:string)=>nodes(tree).find(n=>n.type==='button'&&n.props.label===label);
  const text=(tree:any):string=>Array.isArray(tree)?tree.map(text).join(' '):tree&&typeof tree==='object'?text(tree.props?.children):String(tree??'');
  const expand=()=>{let tree=render();button(tree,locale==='fr'?'Réglages de mise à jour':'Update settings').props.onClick();return render();};
  return {state,calls,timers,nodes,render,button,text,expand,hold:(value:Promise<unknown>)=>hold=value,
    unmount:()=>cleanups.forEach(fn=>fn?.())};
}

for(const locale of ['en','fr']){
  test(`download and explicit two-step install stay outside advanced disclosure (${locale})`,async()=>{
    const h=harness(locale);Object.assign(h.state,{phase:'available',available:true,available_version:'0.1.0-alpha.16'});
    let tree=h.render();const download=locale==='fr'?'Télécharger la mise à jour':'Download update';
    assert(h.button(tree,download));h.button(tree,download).props.onClick();await Promise.resolve();assert.deepEqual(h.calls,['update_prepare']);
    Object.assign(h.state,{phase:'ready',confirmation:'a'.repeat(32)});tree=h.render();
    h.button(tree,locale==='fr'?'Installer la mise à jour':'Install update').props.onClick();tree=h.render();
    assert(!h.calls.includes('update_install'));
    h.button(tree,locale==='fr'?'Confirmer la mise à jour · Decky redémarrera':'Confirm update · Decky will restart').props.onClick();await Promise.resolve();
    assert.equal(h.calls.filter(c=>c==='update_install').length,1);h.unmount();
  });
  test(`public settings use daily checks without authentication or automatic installation (${locale})`,async()=>{
    const h=harness(locale);const tree=h.expand();
    const dropdown=h.nodes(tree).find(n=>n.type==='dropdown');
    assert.deepEqual(Array.from(dropdown.props.rgOptions,(o:any)=>o.data),['stable','beta']);
    const toggles=h.nodes(tree).filter(n=>n.type==='toggle');assert.equal(toggles.length,1);
    assert.match(toggles[0].props.description,/24/);assert.equal(h.timers.size,0);
    assert.equal(h.calls.length,0,'rendering never checks, downloads or installs');
    const check=h.button(tree,locale==='fr'?'Rechercher une mise à jour':'Check for updates now');
    check.props.onClick();await Promise.resolve();assert.deepEqual(h.calls,['update_check']);
    assert(!h.text(tree).includes('GitHub'));h.unmount();
  });
  test(`network errors stay visible and checking blocks duplicate actions (${locale})`,()=>{
    const h=harness(locale);h.state.error='update_network';h.state.phase='error';
    let tree=h.render();assert(h.nodes(tree).some(n=>n.props.role==='alert'));
    h.state.phase='checking';tree=h.render();
    assert(h.button(tree,locale==='fr'?'Rechercher une mise à jour':'Check for updates now').props.disabled);h.unmount();
  });
}
