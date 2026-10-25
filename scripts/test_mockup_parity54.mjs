import assert from 'node:assert/strict';
// Actual production React + RPC fixture. Native event adapters do not prove a
// physical controller or optical display; backend behavior has separate tests.
export async function mockupParity54({page,mount,button,check}){
 const calls=()=>page.evaluate(()=>window.__collection.calls());
 for(const lang of ['fr','en'])for(const layout of ['comfort','compact','list']){
  await page.setViewportSize({width:800,height:800});await mount(lang,{add:true});
  await page.locator('.collection-view-picker select').selectOption(layout);await page.waitForTimeout(350);
  const cards=page.locator('.collection-select-main');assert.equal(await cards.count(),layout==='list'?10:layout==='compact'?10:8);
  const first=cards.first(),selected=await first.getAttribute('aria-checked')==='true',before=await page.evaluate(()=>window.__collection.state().workspace.included_count);
  await first.click();await page.waitForTimeout(250);
  assert.equal(await first.getAttribute('aria-checked'),String(!selected));
  assert.equal(await page.evaluate(()=>window.__collection.state().workspace.included_count),before+(selected?-1:1));
  assert.equal((await calls()).filter(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])).length,0);
  const id=await first.getAttribute('data-collection-focus');
  await first.evaluate(node=>node.dispatchEvent(new CustomEvent('das-test-secondary',{bubbles:true,cancelable:true})));
  await page.locator('.collection-detail').waitFor();
  assert.equal(await page.locator('[data-collection-focus=screensaver-inclusion]').count(),1);
  await page.locator('.collection-sheet-preview iframe.player').waitFor();
  await button('back').click();await page.waitForTimeout(150);
  assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('data-collection-focus')),id);
  if(layout==='list'){
   await button('load-more').click();await page.waitForTimeout(350);assert.equal(await cards.count(),12);
   const ids=await cards.evaluateAll(nodes=>nodes.map(n=>n.dataset.collectionFocus));assert.equal(new Set(ids).size,12);
  }
  check('direct selection / native X / editor return / '+layout+' '+lang);
 }
 for(const source of ['top','online']){
  await mount('en',{add:true,discoveryOnly:true,emptyCollection:true});await page.getByLabel('Game source').selectOption(source);if(source==='online')await page.getByLabel('Find a game').fill('Balatro');
  const card=page.locator('.collection-select-main').first();await card.waitFor();await card.click();await page.waitForFunction(()=>window.__collection.state().workspace.included_count===1);
  assert((await calls()).some(c=>c[0]==='browse_open'));assert.equal((await calls()).filter(c=>c[0]==='workspace_prepare').length,0);check('direct selection opens real discovered game before draft '+source);
 }
 await mount('en',{add:true,emptyCollection:true,selectionDelay:60});
 await page.locator('.collection-select-main').evaluateAll(nodes=>{nodes[0].click();nodes[1].click();nodes[0].click();nodes[2].click();});
 await page.waitForFunction(()=>window.__collection.state().workspace.included_count===2&&window.__collection.calls().filter(c=>c[0]==='workspace_draft').length===4);await page.waitForTimeout(150);
 assert.equal(Object.keys(await page.evaluate(()=>window.__collection.drafts())).length,2);check('serialized rapid multi-game writes and same-game reversal');
 await mount('en',{add:true,emptyCollection:true,selectionFailure:true});const failed=page.locator('.collection-select-main').first();await failed.click();await page.waitForTimeout(250);assert.equal(await failed.getAttribute('aria-checked'),'false');assert.equal(await page.evaluate(()=>window.__collection.state().workspace.included_count),0);
 await failed.click();await page.waitForFunction(()=>window.__collection.state().workspace.included_count===1);check('failed selection rolls back without poisoning next write');
 await mount('fr',{add:true,emptyCollection:true});assert.equal(await button('prepare-selection').isDisabled(),true);
 const first=page.locator('.collection-select-main').first();await first.click();await page.waitForTimeout(250);await first.click();await page.waitForTimeout(250);
 assert.equal(Object.keys(await page.evaluate(()=>window.__collection.drafts())).length,0);assert.equal(await button('prepare-selection').isDisabled(),true);
 await first.click();await page.waitForTimeout(250);await button('prepare-selection').click();
 assert.equal(await page.locator('.collection-confirm-count').innerText(),'1 jeu sélectionné');assert.equal((await calls()).filter(c=>c[0]==='workspace_prepare').length,0);
 await button('back').click();await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>document.activeElement?.dataset.collectionFocus),'prepare-selection');
 await button('prepare-selection').click();await button('confirm').click();await page.locator('[data-activity-state=preparing]').waitFor();assert.equal((await calls()).filter(c=>c[0]==='workspace_prepare').length,1);
 check('empty/reversed selection / one count / explicit preparation / cancel focus');
 for(const lang of ['fr','en']){
  const j={reason:'',detected:true,compatible:true,enabled:true,configured:true,connection_id:'test1',installed:true,prepared:{ready:true,bytes:358400,sync_admissible:true,identity_matches:true}};
  await mount(lang,{jsauxState:j});const result=page.locator('[data-ui-part=faceplate-preparation-status]');
  assert.equal(await result.getAttribute('data-status'),'ready');assert((await result.innerText()).includes(lang==='fr'?'350 ko':'350 KB'));
  assert.equal(await button('jsaux').count(),0);
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();await button('settings-jsaux').click();
  await page.locator('[data-gca-connection-check] button').click();await page.getByRole('status').filter({hasText:lang==='fr'?'GabeCubeAura disponible':'GabeCubeAura available'}).waitFor();
  await button('back').click();await button('settings-jsaux').click();assert((await page.locator('[data-gca-connection-check]').innerText()).includes(lang==='fr'?'disponible':'available'));
  await page.evaluate(()=>window.__collection.patch({jsaux:{...window.__collection.state().jsaux,detected:false,compatible:true,connection_id:'test2'}}));
  await button('settings-playback').waitFor({timeout:7000});assert.equal(await button('settings-jsaux').count(),0);assert.equal(await page.locator('[data-gca-connection-check]').count(),0);
  assert.equal((await calls()).filter(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])).length,0);
  check('prepared GIF exact size / contextual GCA proof / unplug route '+lang);
  await mount(lang,{pending:true,jsauxState:j});assert.equal(await page.locator('[data-ui-part=faceplate-preparation-status]').getAttribute('data-status'),'pending');assert((await page.locator('[data-ui-part=faceplate-preparation-status]').innerText()).includes(lang==='fr'?'Dernier GIF préparé':'Last prepared GIF'));
 }
 await mount('fr',{jsauxState:{detected:true,compatible:true,enabled:true,configured:true,framing:'fill',mode:'async',reason:'',prepared:{ready:true,bytes:1}}});
 await page.locator('[data-collection-focus^=game-]').first().click();await page.locator('.collection-detail').waitFor();await page.getByLabel('Cadrage',{exact:true}).selectOption('16:9');
 await button('pick-panel').click();await button('asset-400').waitFor();
 await page.evaluate(()=>window.__collection.patch({jsaux:{...window.__collection.state().jsaux,detected:false}}));
 await button('pick-animation').waitFor({timeout:7000});assert.equal(await button('pick-panel').count(),0);
 assert.equal(await page.getByLabel('Cadrage',{exact:true}).inputValue(),'16:9');await button('save').click();
 assert.equal((await calls()).find(c=>c[0]==='workspace_draft')[1].patch.crop.mode,'16:9');check('unplug closes Faceplate picker and preserves unsaved TV crop');
 await mount('en',{quick:true,hiddenQuick:true,jsaux:true});await page.waitForTimeout(1300);assert.equal((await calls()).filter(c=>['state','jsaux_refresh'].includes(c[0])).length,0);check('hidden QAM does not probe hardware');
 await mount('fr',{busy:true,jsaux:true});await page.evaluate(()=>window.__collection.patch({jsaux:{...window.__collection.state().jsaux,detected:false}}));
 await page.waitForFunction(()=>!document.querySelector('[data-ui-part=faceplate-preparation-status]'),null,{timeout:7500});assert((await calls()).some(c=>c[0]==='jsaux_refresh'));assert.equal((await calls()).filter(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])).length,0);check('active workflow observes unplug without starting or cancelling a transfer');
 for(const lang of ['fr','en']){
  await mount(lang);await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();await button('settings-updates').click();
  await page.getByRole('button',{name:lang==='fr'?'Réglages de mise à jour':'Update settings',exact:true}).click();
  assert.equal(await page.getByLabel(lang==='fr'?'Télécharger et installer automatiquement':'Download and install automatically').count(),0);
  assert.equal(await page.getByLabel(lang==='fr'?'Vérifier toutes les':'Check every').count(),0);
  await page.getByText(lang==='fr'?'Toutes les 24 heures. Téléchargement et installation manuels.':'Every 24 hours. Download and installation are manual.').waitFor();
  assert.equal((await calls()).filter(c=>['update_prepare','update_install'].includes(c[0])).length,0);
  check('public daily checking with manual downloads and installation '+lang);
 }
}
