// Production components + explicit RPC/Menu DOM adapters; not a SteamOS session.
import assert from 'node:assert/strict';
export async function collectionManagement60({page,mount,button,check}){
 for(const lang of ['fr','en'])for(const native of [false,true]){
  await mount(lang,{native});const before=await page.evaluate(()=>window.__collection.state());
  const search=page.getByRole('textbox',{name:lang==='fr'?'Rechercher dans ma collection':'Search my collection'});
  await search.fill('Hades');await page.waitForFunction(()=>document.querySelectorAll('.collection-card').length===1);
  await button('clear-selection').click();await button('undo-selection').waitFor();
  let state=await page.evaluate(()=>window.__collection.state());assert.equal(state.workspace.included_count,0);assert.equal(state.installation.scene_count,before.installation.scene_count);assert(state.installation.installed);assert.deepEqual(state.options,before.options);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install','uninstall','purge'].includes(c[0])).length,0);
  assert.equal(state.workspace.selection_undo.count,8);await button('undo-selection').click();await button('clear-selection').waitFor();state=await page.evaluate(()=>window.__collection.state());assert.equal(state.workspace.included_count,8);assert.equal(await search.inputValue(),'Hades');
  check('global deselection beyond filter and exact Undo preserve installed collection '+lang+'/'+native);
  await button('manage-collection').click();await button('delete-collection').click();await button('cancel-delete').waitFor();assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_delete_collection').length,0);
  await button('cancel-delete').focus();await page.keyboard.press('Escape');await button('manage-collection').waitFor();await page.waitForFunction(()=>document.activeElement?.getAttribute('data-collection-focus')==='manage-collection');
  await button('manage-collection').click();await button('delete-collection').click();await button('confirm-delete').click();await page.getByRole('tab',{name:lang==='fr'?'Ajouter des jeux':'Add games',selected:true}).waitFor();
  await page.locator('.collection-select-main').first().waitFor();state=await page.evaluate(()=>window.__collection.state());assert.equal(state.installation.installed,false);assert.equal(state.workspace.included_count,0);assert.deepEqual(state.options,before.options);assert(state.key_configured);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_delete_collection'&&c[1].confirm===true).length,1);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>['workspace_prepare','workspace_install','purge','uninstall'].includes(c[0])).length,0);
  check('one confirmed deletion opens fresh Add games; Escape cancels and restores focus '+lang+'/'+native);
  await page.locator('.collection-select-main').first().click();await button('clear-selection').waitFor();await button('clear-selection').click();await button('undo-selection').click();await button('clear-selection').waitFor();assert.equal((await page.evaluate(()=>window.__collection.state())).workspace.included_count,1);
  check('fresh selection supports clear and Undo from Add games '+lang+'/'+native);
 }
 for(const lang of ['fr','en']){
  await mount(lang,{managementError:true});await button('manage-collection').click();await button('delete-collection').click();await button('confirm-delete').click();await page.locator('[data-recovery-card]').waitFor();
  assert((await page.evaluate(()=>window.__collection.state())).installation.installed);assert.equal(await button('confirm-delete').count(),1);assert.match(await page.locator('[data-recovery-card]').innerText(),lang==='fr'?/stockage/i:/storage/i);
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_delete_collection').length,1);
  check('failed deletion stays reviewable with installed export and no automatic retry '+lang);
 }
}
