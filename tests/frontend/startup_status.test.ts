import test from 'node:test';
import assert from 'node:assert/strict';
import {discoveryResponse} from '../../src/discoveryResponse';
import {errorText} from '../../src/i18n';

test('lifecycle RPC data becomes a useful local error for all early reads',()=>{
  for(const action of ['state','jsaux_refresh','jsaux_recover','update_status']){
    assert.throws(()=>discoveryResponse(action,{schema:'das-action-error-v1',ok:false,error:'backend_starting'}),/backend_starting/);
  }
});
test('startup and fatal storage errors have translated user messages',()=>{
  for(const code of ['backend_starting','backend_stopping','backend_storage','backend_start_failed']){
    const text=errorText('Error: '+code);
    assert.notEqual(text,code);assert.doesNotMatch(text,/Python Exception|\/root|Traceback/);
  }
});
