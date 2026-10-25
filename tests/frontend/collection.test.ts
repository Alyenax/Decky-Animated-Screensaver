import test from 'node:test';
import assert from 'node:assert/strict';
import {collectionStep,collectionActivity,installedSceneCount} from '../../src/collectionModel';
import {shouldPoll} from '../../src/model';
import type {StudioState} from '../../src/types';
function fixture(patch:Record<string,unknown>={}){
  return {ready_count:6,job:{state:'idle',worker_active:false},installation:{installed:true},
    workspace:{member_count:6,included_count:6,draft_count:0,pending_count:0,issues_count:0,task:{state:'idle',worker_active:false}},...patch} as StudioState;
}
test('Collection prioritizes interrupted and remaining work over already ready games',()=>{
  const s=fixture();assert.equal(collectionStep(s),'preview');assert.equal(shouldPoll(s),false);
  s.workspace!.pending_count=2;assert.equal(collectionStep(s),'prepare');
  s.job.state='paused';assert.equal(collectionStep(s),'resume');
  s.workspace!.task.worker_active=true;assert.equal(collectionStep(s),'activity');assert.equal(shouldPoll(s),true);
});
test('Collection distinguishes repair, installation and no displayed games',()=>{
  const s=fixture();s.workspace!.issues_count=1;assert.equal(collectionStep(s),'attention');
  s.workspace!.issues_count=0;s.installation.needs_update=true;assert.equal(collectionStep(s),'install');
  s.workspace!.included_count=0;assert.equal(collectionStep(s),'choose');
});
test('Applying or waiting after TV conversion stays polled until backend completion',()=>{
  const s=fixture();s.workspace!.task={state:'applying',error:'',worker_active:true};
  assert.equal(shouldPoll(s),true);assert.equal(collectionStep(s),'activity');
  s.workspace!.task.worker_active=false;s.workspace!.task.state='done';assert.equal(shouldPoll(s),false);
});
test('Installed count comes from exported scenes, never prepared media',()=>{
  const s=fixture();assert.equal(installedSceneCount(s),undefined);
  s.installation.scene_count=3;assert.equal(installedSceneCount(s),3);
  s.ready_count=100;assert.equal(installedSceneCount(s),3);
  s.installation.installed=false;assert.equal(installedSceneCount(s),undefined);
  s.installation.installed=true;s.installation.scene_count=-1;assert.equal(installedSceneCount(s),undefined);
});
test('Done alone never promises installation, including an all-skipped collection',()=>{
  const s=fixture();s.workspace!.task={state:'done',error:'',worker_active:false};
  assert.equal(collectionActivity(s),'finished');
  s.workspace!.task.outcome='installed';assert.equal(collectionActivity(s),'installed');
  s.workspace!.task.outcome='unchanged';assert.equal(collectionActivity(s),'unchanged');
  s.workspace!.task.outcome='empty';s.ready_count=0;s.workspace!.skipped_count=6;
  assert.equal(collectionActivity(s),'empty');assert.equal(collectionStep(s),'choose');
});
test('Controls distinguish preparing, paused, applying and terminal work',()=>{
  const s=fixture();assert.equal(collectionActivity(s),'idle');
  s.workspace!.task={state:'preparing',error:'',worker_active:true};assert.equal(collectionActivity(s),'preparing');
  s.job.state='paused';assert.equal(collectionActivity(s),'paused');
  s.job.state='paused_game';assert.equal(collectionActivity(s),'waiting_game');
  s.workspace!.task.state='applying';assert.equal(collectionActivity(s),'applying');
  s.job.state='idle';s.workspace!.task={state:'paused',error:'GAME_RUNNING',worker_active:false,operation:'install'};
  assert.equal(collectionActivity(s),'paused');assert.equal(collectionStep(s),'resume');
  s.workspace!.task.state='partial';s.workspace!.task.error='';assert.equal(collectionActivity(s),'partial');
  s.workspace!.task.state='error';s.workspace!.task.error='download_failed';assert.equal(collectionActivity(s),'error');
  s.workspace!.task.state='cancelled';s.workspace!.task.error='';assert.equal(collectionActivity(s),'cancelled');
});
test('Automatic game wait is not turned into manual Resume by a paused workspace',()=>{
  const s=fixture();s.job.state='paused_game';s.workspace!.task={state:'paused',error:'GAME_RUNNING',worker_active:true,operation:'prepare'};
  assert.equal(collectionStep(s),'activity');assert.equal(collectionActivity(s),'waiting_game');
  s.workspace!.task.operation='install';s.workspace!.task.worker_active=false;
  assert.equal(collectionStep(s),'resume');assert.equal(collectionActivity(s),'paused');
});
test('Finished collection cannot turn back into preparation because JSAUX is playing or restoring',()=>{
  const s=fixture();s.job={...s.job,state:'complete',stage:'downloading',completed:33,total:33,percent:100};
  s.workspace!.task={state:'done',error:'',worker_active:false,outcome:'installed'};
  for(const phase of ['active','restoring','waiting']){
    s.jsaux={phase,worker_active:false,enabled:false} as any;
    assert.equal(collectionActivity(s),'installed');assert.equal(collectionStep(s),'preview');
  }
  s.workspace!.task={state:'partial',error:'PREPARATION_BUSY',worker_active:false};
  assert.equal(collectionActivity(s),'partial');
  s.jsaux!.worker_active=true;assert.equal(collectionActivity(s),'preparing');
});
