import test from 'node:test';
import assert from 'node:assert/strict';
import {discoveryResponse} from '../../src/discoveryResponse';
import {errorText,setLanguage} from '../../src/i18n';
import {recoveryHelp} from '../../src/recovery';
const localeStorage=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(key:string)=>localeStorage.get(key)||null,setItem:(key:string,value:string)=>localeStorage.set(key,value)}});
test('Running-game refusal survives Decky serialization and explains the next step in both languages',()=>{
 for(const action of ['workspace_prepare','workspace_install','jsaux_prepare']){
  let failure:unknown;
  try{discoveryResponse(action,JSON.parse(JSON.stringify({schema:'das-action-error-v1',ok:false,error:'GAME_RUNNING'})));}catch(error){failure=error;}
  assert(failure instanceof Error);assert.equal(failure.message,'GAME_RUNNING');
  for(const lang of ['fr','en']){
   setLanguage(lang);const text=errorText(String(failure));const help=recoveryHelp(failure.message);
   assert.match(text,lang==='fr'?/Fermez le jeu.*surcharge/:/Close.*game.*overload/i);
   assert.equal(help.action,'preparation');assert.match(help.body,lang==='fr'?/surcharge/:/overload/i);
  }
 }
 for(const error of ['https://private/?key=secret','x'.repeat(81),null])
  assert.throws(()=>discoveryResponse('workspace_prepare',{schema:'das-action-error-v1',ok:false,error}),/unexpected_error/);
 setLanguage('en');
});
test('Expected Top failures remain useful through the RPC data envelope',()=>{
 assert.throws(()=>discoveryResponse('browse_top',{schema:'das-discovery-error-v1',ok:false,error:'steam_tls_unavailable'}),/steam_tls_unavailable/);
 assert.throws(()=>discoveryResponse('browse_search',{schema:'das-discovery-error-v1',ok:false,error:'https://secret/'}),/unexpected_error/);
 assert.throws(()=>discoveryResponse('browse_candidates',{schema:'das-discovery-error-v1',ok:false,error:'read_busy'}),/read_busy/);
 assert.throws(()=>discoveryResponse('candidate_preview',{schema:'das-discovery-error-v1',ok:false,error:'source_limit'}),/source_limit/);
});
test('Successful pages, candidate arrays and unrelated RPC replies are unchanged',()=>{
 for(const value of [{items:[],total:0},[{id:1}]])assert.equal(discoveryResponse('browse_top',value),value);
 const value={schema:'das-discovery-error-v1',ok:false,error:'example'};
 assert.equal(discoveryResponse('state',value),value);
});
test('Collection management failures cross RPC with translated, actionable remedies',()=>{
 for(const lang of ['fr','en']){
  setLanguage(lang);
  for(const action of ['workspace_select_all','workspace_deselect_all','workspace_undo_selection','workspace_delete_collection']){
   for(const code of ['collection_change_failed','selection_undo_expired','collection_order_changed','confirmation_required','busy']){
    assert.throws(()=>discoveryResponse(action,JSON.parse(JSON.stringify({schema:'das-action-error-v1',ok:false,error:code}))),new RegExp(code));
    assert(!errorText(code).includes(code));
   }
  }
  assert.equal(recoveryHelp('collection_change_failed').action,'storage');
  assert.equal(recoveryHelp('selection_undo_expired').action,'library');
  assert.equal(recoveryHelp('collection_order_changed').action,'library');
 }
 setLanguage('en');
});
