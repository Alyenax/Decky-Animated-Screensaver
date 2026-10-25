import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

// Production React and native control/RPC adapters; backend scope is independently
// exercised through the real installer. This is not physical controller evidence.
export async function selectionRecovery57({page,mount,button,check}){
 const calls=()=>page.evaluate(()=>window.__collection.calls());
 const writes=async()=> (await calls()).filter(c=>['workspace_prepare','workspace_install','jsaux_configure','jsaux_prepare'].includes(c[0]));
 await fs.mkdir('out/ui/recovery57',{recursive:true});
 for(const lang of ['fr','en']){
  await page.setViewportSize({width:800,height:800});
  const failed={activity:true,task:{state:'partial',stage:'faceplate',tv_state:'prepared',faceplate_state:'repair_required',error:'JSAUX_SYNC_WINDOW'},jsaux:true,jsauxState:{reason:'',preparation_error:'JSAUX_SYNC_WINDOW',prepared:{ready:false,percent:0}}};
  await mount(lang,failed);await button('prepare-batches').waitFor();
  assert.equal((await writes()).length,0);
  assert.equal(await page.locator('[data-faceplate-recovery=sync-capacity]').count(),1);
  assert.equal(await page.locator('[data-faceplate-recovery] button').count(),1);
  assert.equal(await page.locator('.collection-activity button').count(),1,'Capacity recovery has one preparation action, with Back outside the section');
  assert.equal(await page.locator('[data-workflow-outputs]').count(),0,'Capacity fallback does not repeat failed-output details');
  assert((await page.locator('[data-faceplate-recovery]').innerText()).includes(lang==='fr'?'lots en lecture indépendante':'lots with independent playback'));
  await button('prepare-batches').click();await button('confirm').waitFor();
  assert.equal((await writes()).length,0);
  await button('back').click();await button('prepare-batches').waitFor();assert.equal((await writes()).length,0);
  await button('prepare-batches').click();await button('confirm').click();
  await page.locator('[data-activity-state=applying]').waitFor();
  const request=(await writes()).find(c=>c[0]==='workspace_install');
  assert.deepEqual(request[1],{confirm:true,language:lang,repair_faceplate:true});
  assert.equal((await writes()).length,1,'Normal preparation applies fallback without separate mode or selection mutations');
  assert.equal(await page.evaluate(()=>window.__collection.state().workspace.included_count),8);
  check('one lots action / read-only until normal confirmation / all games kept '+lang);

  const ready={detected:true,compatible:true,enabled:true,configured:true,mode:'sync',reason:'',installed:true,prepared:{ready:true,sync_admissible:true,bytes:4096}};
  await mount(lang,{activity:true,task:failed.task,jsauxState:ready});
  assert.equal(await page.locator('[data-faceplate-recovery]').count(),0);
  assert.equal(await page.locator('[data-ui-part=faceplate-preparation-status][data-status=ready]').count(),1);
  assert.equal(await page.locator('.collection-activity [role=alert]').count(),0);
  const green=await page.locator('.faceplate-preparation-title').evaluate(n=>getComputedStyle(n).color.match(/\d+/g).map(Number));assert(green[1]>green[0]&&green[1]>green[2],'Prepared text uses green');
  await page.locator('[data-activity-state=installed]').waitFor();
  check('current ready installed output retires stale Fix, failed label and historical alert '+lang);

  await mount(lang,{jsauxState:{...ready,reason:'',controller_status_error:'AUTH_DENIED'}});
  await button('check-gca').click();assert((await calls()).some(c=>c[0]==='jsaux_refresh'&&c[1].force));
  assert.equal((await writes()).length,0);assert.equal(await button('prepare-faceplate').count(),0);
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings'}).click();await button('settings-jsaux').waitFor();
  check('optional player status fault preserves hardware settings and offers connection check only '+lang);

  await mount(lang,{jsauxState:{...ready,mode:'async',preparation_error:'CONTENT_TOO_LARGE',prepared:{ready:false}}});
  assert.equal(await button('independent-choice').count(),0);assert.equal(await button('capacity-selection').count(),0);assert.equal(await button('prepare-batches').count(),1);
  assert.equal(await page.evaluate(()=>window.__collection.state().workspace.included_count),8,'A capacity warning never removes selected games');
  check('independent capacity automatically prepares lots without truncation '+lang);

  await mount(lang,{jsauxState:{...ready,mode:'sync',prepared:{ready:true,effective_mode:'async',sync_admissible:false,batch_count:7,total_bytes:524288,bytes:70000,automatic_independent:true}}});
  await page.screenshot({path:`out/ui/recovery57/prepared-lots-${lang}-800.png`});
  const notice=await page.locator('.faceplate-preparation-size').innerText();
  assert.equal(notice,lang==='fr'?'7 lots · 512 ko · lecture indépendante':'7 lots · 512 KB · independent playback');
  assert.equal(await page.locator('[data-faceplate-recovery]').count(),0);
  check('prepared lots show one concise notice and total size '+lang);
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings'}).click();
  await button('settings-jsaux').click();
  assert.equal(await page.getByLabel(lang==='fr'?'Mode de lecture':'Playback mode').inputValue(),'sync');
  assert.equal(await page.locator('.collection-settings-form .error').count(),0);
  assert.equal((await writes()).length,0,'Viewing automatic independent lots never rewrites the requested setting');
  check('settings retain synchronised preference after independent lots without an error or mutation '+lang);

  await mount(lang,{jsauxState:{...ready,worker_active:true,phase:'preparing',prepared:{ready:false,percent:37}},activity:true,task:{state:'preparing',stage:'faceplate',faceplate_state:'repair_required',worker_active:true}});
  assert.equal(await page.locator('[data-faceplate-recovery]').count(),0,'Initial preparation does not invent a repair error');
  assert.equal(await page.locator('.faceplate-preparation-title.has-issue').count(),0,'Routine preparation has no orange error label');
  await page.evaluate(()=>window.__collection.patch({job:{...window.__collection.state().job,state:'complete',percent:100}}));
  await page.waitForFunction(()=>document.querySelector('.collection-activity progress')?.value===37);
  check('Faceplate progress uses its37percent rather than the completed TV100percent '+lang);

  await mount(lang,failed);await page.screenshot({path:`out/ui/recovery57/capacity-${lang}-800.png`});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await button('prepare-batches').click();await page.screenshot({path:`out/ui/recovery57/confirm-${lang}-800.png`});
 }
}
