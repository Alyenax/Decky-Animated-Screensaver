import test from 'node:test';
import assert from 'node:assert/strict';
import {faceplateIssue,faceplateNeedsCorrection,faceplatePreparationFailed,faceplateTaskResolved,faceplateSummary} from '../../src/faceplateUX';
import {collectionActivity} from '../../src/collectionModel';
import type {StudioState} from '../../src/types';

const state=()=>({job:{state:'complete',worker_active:false},installation:{installed:true,needs_update:false,needs_repair:false},workspace:{included_count:11,pending_count:0,draft_count:0,issues_count:0,task:{state:'partial',faceplate_state:'repair_required',error:'JSAUX_SYNC_WINDOW',worker_active:false}},jsaux:{enabled:true,detected:true,compatible:true,mode:'sync',phase:'idle',worker_active:false,reason:'',installed:true,prepared:{ready:true,sync_admissible:true}}} as StudioState);

test('Recovered current GIF and installed output retire only the historical Faceplate failure',()=>{
 const s=state();assert.equal(faceplateNeedsCorrection(s),false);assert.equal(faceplatePreparationFailed(s),false);
 assert.equal(faceplateTaskResolved(s),true);assert.equal(collectionActivity(s),'installed');
 s.workspace!.issues_count=1;assert.equal(faceplateTaskResolved(s),false);assert.equal(collectionActivity(s),'partial');
});
test('Current compile failure stays actionable with an older valid GIF; connection refresh cannot hide it',()=>{
 const s=state();s.jsaux!.preparation_error='JSAUX_SYNC_WINDOW';
 assert.equal(faceplateIssue(s)?.kind,'sync-capacity');assert.equal(faceplatePreparationFailed(s),false);
 s.jsaux!.reason='';assert.equal(faceplateNeedsCorrection(s),true);assert.equal(faceplateTaskResolved(s),false);
});
test('Connection and USB transfer faults never demand GIF encoding',()=>{
 for(const code of ['AUTH_DENIED','BROKER_UNAVAILABLE','PROTOCOL_INVALID']){
  const s=state();s.jsaux!.controller_status_error=code;s.jsaux!.prepared!.sync_admissible=false;assert.equal(faceplateIssue(s)?.kind,'connection');assert.equal(faceplatePreparationFailed(s),false);
 }
 for(const code of ['USB_FAILED','USB_UNCONFIRMED']){
  const s=state();s.jsaux!.reason=code;assert.equal(faceplateIssue(s)?.kind,'transfer');assert.equal(faceplatePreparationFailed(s),false);
 }
});
test('Independent mode does not offer an obsolete synchronised fallback; capacity failure never implies silent removal',()=>{
 const s=state();s.jsaux!.mode='async';s.jsaux!.prepared!.ready=false;s.jsaux!.prepared!.sync_admissible=false;
 assert.equal(faceplateIssue(s),null);s.jsaux!.reason='JSAUX_SYNC_WINDOW';assert.equal(faceplateIssue(s),null);
 s.jsaux!.preparation_error='CONTENT_TOO_LARGE';assert.equal(faceplateIssue(s)?.kind,'capacity');assert.equal(s.workspace!.included_count,11);
});
test('A real missing GIF remains a preparation issue; absent or disabled hardware never shows commands',()=>{
 const s=state();s.jsaux!.prepared!.ready=false;s.workspace!.task.error='PREPARED_FILE_MISSING';assert.equal(faceplateIssue(s)?.kind,'preparation');
 s.workspace!.task.state='preparing';s.workspace!.task.error='';assert.equal(faceplateIssue(s),null,'Initial preparation is normal work, not a repair failure');
 s.workspace!.task.state='cancelled';assert.equal(faceplateIssue(s),null,'User cancellation does not fabricate a preparation failure');
 s.workspace!.task.state='partial';s.workspace!.task.error='PREPARED_FILE_MISSING';
 s.jsaux!.detected=false;assert.equal(faceplateIssue(s),null);s.jsaux!.detected=true;s.jsaux!.enabled=false;assert.equal(faceplateIssue(s),null);
});

 test('Automatic lots keep the sync preference without a false repair state',()=>{
 const s=state();s.jsaux!.prepared!={ready:true,effective_mode:'async',batch_count:7,sync_admissible:false,automatic_independent:true,bytes:70000};
 assert.equal(s.jsaux!.mode,'sync');assert.equal(faceplateIssue(s),null);
 assert.equal(faceplateTaskResolved(s),true);assert.equal(collectionActivity(s),'installed');
 assert.equal(faceplateSummary(s.jsaux)?.kind,'ready');
 });
