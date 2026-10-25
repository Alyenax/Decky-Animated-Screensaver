import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import ts from 'typescript';
import {publishUpdate,getUpdateNotice,visibleUpdate} from '../../src/update_notice';
import type {UpdateState} from '../../src/types';

const source=readFileSync(new URL('../../src/PluginUpdateNotice.tsx',import.meta.url),'utf8').replace(/^import .*;\n/gm,'');
const context=vm.createContext({exports:{},React:{createElement},DialogButton:'button',QuickAction:'quick-button',tr:(en:string)=>en,useLanguage:()=>{},useUpdateNotice:getUpdateNotice,visibleUpdate});
vm.runInContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,context);
const update={channel:'stable',phase:'available',installed_version:'0.1.0-alpha.45',available_version:'0.1.0-alpha.46',available:true,auth:{state:'connected'}} as UpdateState;

test('quick and collection views keep a live update action until the update is installed',()=>{
  let clicks=0;
  const render=(quick:boolean)=>(context.exports as any).PluginUpdateNotice({quick,onOpen:()=>clicks++});
  publishUpdate({...update,available:false});assert.equal(render(true),null);assert.equal(render(false),null);
  publishUpdate(update);
  for(const quick of [true,false]){const view=render(quick);assert.equal(view.type,quick?'quick-button':'button');assert.match(view.props.children,/Update available.*0.1.0-alpha.46/);view.props.onClick();}
  assert.equal(clicks,2);
  publishUpdate({...update,phase:'ready'});assert.match(render(true).props.children,/Update ready/);
  publishUpdate({...update,phase:'updated',available:false,installed_version:update.available_version});assert.equal(render(true),null);
  assert.equal(clicks,2,'new detections/rendering never download or install');
});

test('actual QuickShell forwards the explicit update route callback to CollectionQuick',()=>{
  const code=readFileSync(new URL('../../src/StudioShell.tsx',import.meta.url),'utf8').replace(/^import .*;\n/gm,'');
  const shell=vm.createContext({exports:{},React:{createElement},CollectionQuick:'collection-quick',CollectionStudio:'collection-studio'});
  vm.runInContext(ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,shell);
  let updates=0;const view=(shell.exports as any).QuickShell({open:()=>assert.fail('must open Updates, not a generic tab'),openUpdates:()=>updates++});
  assert.equal(view.type,'collection-quick');view.props.onOpenUpdates();assert.equal(updates,1);
});

test('a known update remains visible through GitHub expiry and errors',()=>{
  const render=()=>(context.exports as any).PluginUpdateNotice({quick:true,onOpen:()=>{}});
  for(const state of ['expired','error','disconnected']){
    publishUpdate({...update,phase:'error',auth:{state}} as UpdateState);
    assert.match(render().props.children,/Update available.*0.1.0-alpha.46/);
  }
  publishUpdate({...update,available:false});assert.equal(render(),null);
});
