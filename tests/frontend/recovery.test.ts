import test from 'node:test';
import assert from 'node:assert/strict';
import {isGameRunningCode,attentionCount,collectionRecoveryRoute,problemFor,recoveryHelp,safeErrorCode,type RecoveryAction} from '../../src/recovery';
import type {StudioGame,StudioState} from '../../src/types';
import {errorText,setLanguage} from '../../src/i18n';
const localeStorage=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(key:string)=>localeStorage.get(key)||null,setItem:(key:string,value:string)=>localeStorage.set(key,value)}});

test('Readable explanations point each common failure to its actual next action',()=>{
  for(const lang of ['fr','en']){
    setLanguage(lang);
    for(const [code,action] of [['invalid_media','choose'],['decode_failed','choose'],['download_failed','retry'],
      ['key_missing','settings'],['ffprobe_missing','tools'],['probe_failed','tools'],['storage_limit','storage'],
      ['GAME_RUNNING','preparation'],['AUTH_DENIED','connection'],['static_motion_failed','retry'],['arbitrary_unknown','diagnostic']]){
      const help=recoveryHelp(code);assert.equal(help.action,action,code);assert(help.title&&help.body&&help.label);
      assert(!help.title.includes(code),help.title);
    }
    assert.equal(recoveryHelp('download_failed','animation','tools').action,'tools');
  }
  setLanguage('fr');assert(recoveryHelp('invalid_media','cover').title.includes('jaquette'));
  assert(recoveryHelp('invalid_media','logo').title.includes('Le logo'));
  assert.equal(recoveryHelp('invalid_media','logo').label,'Choisir un autre logo');
  setLanguage('en');
});
test('Ready old media and optional asset failures remain discoverable',()=>{
  const game={appid:620,name:'Portal 2',status:'ready',error:'invalid_media'} as StudioGame;
  assert(problemFor(game)?.retained_media);
  assert.equal(problemFor({...game,error:'',cover_error:'download_failed'})?.role,'cover');
  assert.equal(problemFor({...game,excluded:true}),null);
  assert.equal(attentionCount({issues_count:2,failed_count:0} as StudioState),2);
  assert.equal(safeErrorCode('Error: invalid_media'),'invalid_media');
  assert.equal(safeErrorCode('private token /secret'),'unexpected_error');
});
test('Collection recovery routes act on actual actions without implying a second installation step',()=>{
  const s={job:{state:'idle',worker_active:false},workspace:{issues_count:0,task:{state:'idle',worker_active:false}},jsaux:{detected:false,configured:false,phase:'idle'}} as StudioState;
  for(const [action,route] of [['settings','setup'],['tools','setup'],['storage','assistance'],['diagnostic','assistance'],['connection','assistance'],['faceplate','collection'],['preparation','collection'],['library','collection'],['choose','collection'],['retry','collection'],['attention','collection']] as [RecoveryAction,string][])
    assert.equal(collectionRecoveryRoute(action,s),route,action);
  s.workspace!.issues_count=1;for(const action of ['choose','retry','attention'] as RecoveryAction[])assert.equal(collectionRecoveryRoute(action,s),'attention');
  assert.equal(collectionRecoveryRoute('library',s),'collection','adjusting JSAUX selection is not a game error');
  s.workspace!.task.state='paused';assert.equal(collectionRecoveryRoute('preparation',s),'activity');
  s.workspace!.task.state='idle';s.job.state='paused_game';assert.equal(collectionRecoveryRoute('preparation',s),'activity');
  s.jsaux!.configured=true;assert.equal(collectionRecoveryRoute('connection',s),'jsaux');assert.equal(collectionRecoveryRoute('faceplate',s),'collection');
  for(const lang of ['fr','en']){setLanguage(lang);for(const code of ['not_ready','CONTENT_MISSING','JSAUX_PREPARATION_REQUIRED','JSAUX_RELAY_UNAVAILABLE','JSAUX_SYNC_WINDOW']){
    const text=recoveryHelp(code).body+' '+errorText(code);
    assert(!/Open Preparation|Ouvrez Préparation|update Steam|Update in Steam|Mettre à jour dans Steam|mettez Steam à jour|puis mettez à jour Steam/i.test(text),code);
    assert(/collection|independent|indépendante/i.test(text));
  }}
});

test('Running-game states use user instructions across code capitalization',()=>{
 for(const lang of ['fr','en']){setLanguage(lang);for(const code of ['GAME_RUNNING','game_running','Game_running','paused_game']){
  assert(isGameRunningCode(code));assert.equal(recoveryHelp(code).action,'preparation');
  assert(!recoveryHelp(code).body.includes(code));
  assert(!errorText(code).includes(code));
 }}
 assert(!isGameRunningCode('worker_signal'));setLanguage('en');
});
