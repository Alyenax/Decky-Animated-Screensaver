import test from 'node:test';
import assert from 'node:assert/strict';
import {faceplateSummary,faceplateRebuildRequired} from '../../src/faceplateUX';
import {collectionStep} from '../../src/collectionModel';
import type {JsauxState,StudioState} from '../../src/types';
const panel=(patch:Partial<JsauxState>={})=>({configured:true,detected:true,compatible:true,enabled:true,
  mode:'sync',phase:'idle',worker_active:false,reason:'',installed:true,prepared:{ready:true,sync_admissible:true},...patch} as JsauxState);
test('Normal lifecycle and unknown connection never become an orange collection failure',()=>{
  for(const reason of ['', 'STEAM_INACTIVE','STEAM_STATE_STALE','ACTIVATION_CLOSED','FLASH_DEFERRED',
    'PRIORITY_ACTIVE','DEVICE_BUSY','BROKER_UNAVAILABLE','STALE_BOOT','USB_UNCONFIRMED','USB_FAILED','ALIGNMENT_EXPIRED']){
    assert.equal(faceplateSummary(panel({reason}))?.tone,'neutral',reason);
  }
  assert.equal(faceplateSummary(panel({detected:false,compatible:false})),null);
  assert.equal(faceplateSummary(panel({enabled:false,reason:'AUTH_DENIED'}))?.kind,'off');
  assert.equal(faceplateSummary(undefined),null);
});
test('Only specific actionable connection and collection limits attract attention',()=>{
  for(const reason of ['AUTH_DENIED','VERSION_UNSUPPORTED','PROTOCOL_INVALID','CONTENT_TOO_LARGE','JSAUX_SYNC_WINDOW'])
    assert.equal(faceplateSummary(panel({reason}))?.tone,'attention',reason);
  assert.equal(faceplateSummary(panel({prepared:{ready:true,sync_admissible:false} as any}))?.kind,'selection');
  assert.equal(faceplateSummary(panel({reason:'CONTENT_TOO_LARGE'}),true)?.kind,'update');
  assert.equal(faceplateSummary(panel({reason:'JSAUX_SYNC_WINDOW',prepared:{ready:false,reason:'PREPARATION_STALE'} as any}))?.tone,'neutral');
  assert.notEqual(faceplateSummary(panel({reason:'USB_FAILED'}))?.kind,faceplateSummary(panel({reason:'USB_UNCONFIRMED'}))?.kind);
});
test('Stale, missing, old-power and rejected images use the ordinary collection action',()=>{
  for(const j of [panel({prepared:{ready:false} as any}),panel({prepared:{ready:true,power_upgrade_required:true} as any}),panel({reason:'CONTENT_INVALID'})]){
    assert(faceplateRebuildRequired(j));assert.equal(faceplateSummary(j)?.kind,'update');
    const s={ready_count:8,job:{state:'idle',worker_active:false},installation:{installed:true},
      workspace:{member_count:8,included_count:8,task:{state:'idle',worker_active:false}},jsaux:j} as StudioState;
    assert.equal(collectionStep(s),'faceplate');
  }
  assert.equal(faceplateRebuildRequired(panel()),false);
});
