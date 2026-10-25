import test from 'node:test';
import assert from 'node:assert/strict';
import {nextStep,safeImage,shouldPoll} from '../../src/model';
import {studioPreviewURL,type StudioState} from '../../src/types';
function state(){return {game_count:2,included_count:2,ready_count:0,key_configured:true,media_tools:{available:true,state:'idle'},job:{state:'idle',worker_active:false},installation:{installed:false}} as StudioState;}
test('Next step covers setup to repair, conflicts and partial preparation',()=>{
  const s=state();assert.equal(nextStep(s).kind,'prepare');s.key_configured=false;assert.equal(nextStep(s).action,'settings');
  s.key_configured=true;s.included_count=0;assert.equal(nextStep(s).action,'library');s.included_count=2;
  s.job.worker_active=true;assert.equal(nextStep(s).action,null);s.job.worker_active=false;s.job.state='paused';s.job.queue=[620];assert.equal(nextStep(s).action,'resume');
  s.job.state='complete';s.ready_count=1;assert.equal(nextStep(s).kind,'install');s.installation.installed=true;assert.equal(nextStep(s).kind,'current');
  s.installation.needs_update=true;assert.equal(nextStep(s).kind,'update');s.installation.needs_repair=true;assert.equal(nextStep(s).kind,'repair');
  s.installation.error='installation_conflict';assert.equal(nextStep(s).action,null);
});
test('Only background preparation and tool downloads trigger UI polling',()=>{
  const s=state();assert.equal(shouldPoll(s),false);s.job.worker_active=true;assert.equal(shouldPoll(s),true);s.job.worker_active=false;
  s.media_tools.state='downloading';assert.equal(shouldPoll(s),true);s.media_tools.state='ready';assert.equal(shouldPoll(s),false);
});
test('Actual worker flags override an obsolete saved job phase without hiding real work',()=>{
  const s=state();s.job.state='running';s.job.worker_active=false;
  assert.equal(shouldPoll(s),false);
  s.job.worker_active=true;assert.equal(shouldPoll(s),true);
  s.job.worker_active=false;delete (s.job as any).worker_active;
  assert.equal(shouldPoll(s),true,'legacy backend still uses its running state');
});
test('Public repository verification remains observable without the Updates panel',()=>{
  const s=state();s.updates={auth:{state:'pending'},phase:'idle',repository_state:'unchecked'} as any;
  assert.equal(shouldPoll(s),false,'obsolete authorization data does not start polling');
  s.updates!.repository_state='checking';assert.equal(shouldPoll(s),true);
  s.updates!.repository_state='denied';assert.equal(shouldPoll(s),false);
  s.updates!.repository_state='ready';assert.equal(shouldPoll(s),false);
});
test('Prepared media retain install and repair without a key, tools or a finished queue',()=>{
  const s=state();s.ready_count=1;s.key_configured=false;s.media_tools.available=false;s.job.state='paused';
  assert.equal(nextStep(s).kind,'install');s.installation.installed=true;s.installation.needs_repair=true;
  assert.equal(nextStep(s).kind,'repair');s.installation.needs_repair=false;
  s.jsaux={detected:false,compatible:true,configured:true,enabled:true,prepared:{ready:true,bytes:123},installed:false,phase:'idle'} as any;
  assert.equal(nextStep(s).kind,'current');s.jsaux!.detected=true;
  assert.equal(nextStep(s).kind,'update');s.jsaux!.phase='validating';assert.equal(nextStep(s).kind,'working');
});
test('Prepared preview URLs and remote still thumbnails are constrained',()=>{
  const valid='http://127.0.0.1:1234/'+'a'.repeat(43)+'/'+'b'.repeat(24);
  assert(studioPreviewURL(valid));for(const value of ['javascript:alert(1)','https://evil.test/a',valid.replace('127.0.0.1','evil.test')])assert.equal(studioPreviewURL(value),undefined);
  assert(safeImage('https://cdn.steamgriddb.com/a.jpg'));assert(safeImage('data:image/png;base64,AAAA'));
  assert(safeImage('https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/620/header.jpg'));
  assert(safeImage('https://cdn2.steamgriddb.com/thumb/a.webp'));assert(safeImage('https://cdn2.steamgriddb.com/logo_thumb/a.webp'));
  assert(safeImage('https://cdn2.steamgriddb.com/thumb/a.gif'));assert(safeImage('https://s3.amazonaws.com/steamgriddb/thumb/a.webp'));
  assert(safeImage('https://s3.amazonaws.com/steamgriddb/thumb/a.png'));
  for(const value of ['https://s3.amazonaws.com/other/thumb/a.png','https://s3.amazonaws.com/steamgriddb/grid/a.png','https://cdn2.steamgriddb.com/hero/a.webp','http://cdn2.steamgriddb.com/thumb/a.png'])assert.equal(safeImage(value),undefined);
  for(const value of ['https://evil.test/a.jpg','https://cdn.steamgriddb.com/a.gif','data:image/svg+xml;base64,AAAA'])assert.equal(safeImage(value),undefined);
  for(const value of ['https://shared.akamai.steamstatic.com:444/steam/apps/620/header.jpg','https://shared.akamai.steamstatic.com@evil.test/steam/apps/620/header.jpg','https://shared.akamai.steamstatic.com.evil.test/steam/apps/620/header.jpg','https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/620/header.gif'])assert.equal(safeImage(value),undefined);
});
test('A requested connected faceplate preparation comes before Steam installation or update',()=>{
  const s=state();s.ready_count=2;s.installation.installed=true;
  s.jsaux={enabled:true,detected:true,compatible:true,phase:'idle',prepared:{ready:false,bytes:160000,reason:'PREPARATION_STALE'}} as any;
  assert.equal(nextStep(s).action,'jsaux_prepare');
  s.jsaux!.prepared!.ready=true;assert.equal(nextStep(s).action,'install');
  s.jsaux!.prepared!.ready=false;s.jsaux!.detected=false;assert.equal(nextStep(s).kind,'current');
  s.installation.needs_update=true;assert.equal(nextStep(s).kind,'update');
});
