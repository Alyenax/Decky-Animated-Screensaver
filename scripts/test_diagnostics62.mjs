import assert from 'node:assert/strict';
export async function diagnostics62({page,mount,button,check}){
 for(const lang of ['fr','en'])for(const present of [false,true]){
  await mount(lang,{activity:true,jsaux:present,task:{state:'paused',worker_active:true,stage:'tv',error:'worker_signal'},jobState:'paused'});
  await button('interruption-diagnostic').waitFor();assert.equal(await page.getByText('worker_signal',{exact:true}).count(),0);
  await button('interruption-diagnostic').click();
  const save=page.getByRole('button',{name:lang==='fr'?'Enregistrer un diagnostic local':'Save local diagnostic',exact:true});await save.waitFor();assert(await save.isEnabled());
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='diagnostic').length,0);
  await save.click();
  const calls=await page.evaluate(()=>window.__collection.calls());assert.equal(calls.filter(c=>c[0]==='diagnostic').length,1);assert.equal(calls.filter(c=>['diagnostic_upload','cancel','resume','workspace_prepare','workspace_install','purge'].includes(c[0])).length,0);
  await page.getByRole('button',{name:lang==='fr'?'Stockage et imports':'Storage and imports',exact:true}).click();
  assert(await page.getByRole('button',{name:lang==='fr'?'Supprimer les médias préparés et l’export':'Delete prepared media and export',exact:true}).isDisabled());
  const state=await page.evaluate(()=>window.__collection.state());assert.equal(state.workspace.task.state,'paused');assert.equal(state.workspace.task.worker_active,true);
  check('paused worker allows complete local diagnostic with no cancellation, while maintenance stays blocked '+lang+'/'+(present?'Faceplate':'TV-only'));
 }
 for(const lang of ['fr','en']){
  await mount(lang,{busy:true});await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings'}).click();await button('settings-assistance').click();
  assert.equal(await page.getByRole('button',{name:lang==='fr'?'Envoyer le diagnostic sur GitHub':'Send diagnostic to GitHub',exact:true}).count(),0);
  await page.getByRole('button',{name:lang==='fr'?'Enregistrer un diagnostic local':'Save local diagnostic',exact:true}).click();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='diagnostic').length,1);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='diagnostic_upload').length,0);
  check('active preparation keeps complete local support accessible without any upload '+lang);
 }
 for(const lang of ['fr','en'])for(const role of ['animation','cover']){
  await mount(lang,{activity:true,skippedVisual:role,task:{state:'done',outcome:'installed',tv_state:'installed'},sceneCount:7});
  assert.equal(await button('review-skipped-visuals').count(),0);
  assert.equal(await button('resume').count(),0);assert.equal(await button('interruption-diagnostic').count(),0);
  await page.getByText(lang==='fr'?'7 jeux installés.':'7 games installed.',{exact:true}).waitFor();
  assert.equal(await page.locator('.collection-activity .collection-attention').count(),0);
  await button('continue').click();await page.locator('.collection-card').first().click();
  assert.equal(await button('replace-skipped-visual').count(),0);assert.equal(await page.locator('.collection-detail .collection-attention').count(),0);
  const pick=role==='cover'?'pick-cover':'pick-animation';
  await button(pick).click();await button('asset-'+(role==='cover'?200:100)).waitFor();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install','resume'].includes(c[0])).length,0);
  check('skipped artwork has no attention banner or repair action; normal image choice remains available '+lang+'/'+role);

 }

 for(const lang of ['fr','en'])for(const code of ['GAME_RUNNING','Game_running']){
  await mount(lang,{first:true,gameRunning:true,gameRunningCode:code});
  await button('primary').click();await button('confirm').click();await page.locator('[data-recovery-card]').waitFor();
  const card=page.locator('[data-recovery-card]');assert.match(await card.innerText(),lang==='fr'?/Fermez le jeu/:/Close the running game/);
  assert.equal(await card.getByRole('button',{name:lang==='fr'?'Afficher':'Show',exact:true}).count(),0);
  assert(!/diagnostic code|code diagnostic|game_running/i.test(await card.innerText()));
  check('running game shows user instructions with no diagnostic-code controls '+lang+'/'+code);
 }

}
