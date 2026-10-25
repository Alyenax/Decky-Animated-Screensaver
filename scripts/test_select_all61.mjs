import assert from 'node:assert/strict';
export async function selectAll61({page,mount,button,check}){
 const options=async(repeat=false)=>page.locator('.collection-select-main').first().evaluate((node,repeat)=>node.dispatchEvent(new CustomEvent('das-test-options',{bubbles:true,cancelable:true,detail:{button:4,is_repeat:repeat}})),repeat);
 const count=async(n)=>page.waitForFunction(n=>window.__collection.state().workspace.included_count===n,n);
 for(const lang of ['fr','en']){
  for(const list of [false,true]){
   await mount(lang,{add:true,selectionDelay:180});
   if(list){await page.getByLabel(lang==='fr'?'Présentation':'View',{exact:true}).selectOption('list');await page.waitForTimeout(300);}
   await page.locator('.collection-select-main').first().waitFor();
   assert.equal(await page.locator('.collection-selection-grid').getAttribute('data-test-options-description'),lang==='fr'?'Tout sélectionner':'Select all');
   assert.equal(await page.getByRole('button',{name:/^(Tout sélectionner|Select all)$/}).count(),0);
   assert.equal(await page.locator('.collection-select-main').count(),list?10:8);
   await options();await options(true);await options();await count(12);
   assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').length,1);
   await page.waitForFunction(()=>document.querySelectorAll('.collection-select-main[aria-checked=true]').length===document.querySelectorAll('.collection-select-main').length);
   const calls=await page.evaluate(()=>window.__collection.calls());assert.equal(calls.filter(c=>['workspace_prepare','workspace_install','jsaux_prepare','workspace_draft'].includes(c[0])).length,0);
   check('Y selects all installed results beyond visible page, deduplicates presses, adds no button or preparation '+lang+'/'+(list?'list':'grid'));
  }
  await mount(lang,{add:true});await page.getByLabel(lang==='fr'?'Rechercher un jeu':'Find a game').fill('Noita');await page.waitForTimeout(350);
  await page.locator('.collection-select-main').first().focus();await page.keyboard.press('y');await count(9);
  assert.deepEqual((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').map(c=>c[1]),[{source:'installed',query:'Noita'}]);
  await page.getByLabel(lang==='fr'?'Source des jeux':'Game source').selectOption('top');await page.waitForTimeout(400);await options();await count(12);
  const top=(await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').at(-1);assert.equal(top[1].source,'top');assert.equal(top[1].appids.length,12);
  check('Y respects search, keeps existing selection and selects the complete Top Steam result set '+lang);
  await mount(lang,{add:true});await page.getByLabel(lang==='fr'?'Source des jeux':'Game source').selectOption('online');
  await page.getByLabel(lang==='fr'?'Rechercher un jeu':'Find a game').fill('Noita');await page.waitForTimeout(650);await options();await count(9);
  assert.deepEqual((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').map(c=>c[1]),[{source:'online',appids:[881100]}]);
  await mount(lang,{add:true});await page.getByLabel(lang==='fr'?'Rechercher un jeu':'Find a game').fill('Noita');await options();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').length,0);
  await page.getByLabel(lang==='fr'?'Rechercher un jeu':'Find a game').focus();await page.keyboard.press('y');
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').length,0);
  await mount(lang,{add:true,busy:true});await options();assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').length,0);
  assert.equal(await page.locator('[data-test-options-description]').count(),0);
  check('Y selects only online results and stays inactive for stale queries, typing and active preparation '+lang);
  await mount(lang,{add:true,selectionFailure:true});await options();await page.locator('[data-recovery-card]').waitFor();assert.equal((await page.evaluate(()=>window.__collection.state())).workspace.included_count,8);
  await page.locator('.collection-select-main').first().focus();await page.keyboard.press('y');await count(12);
  await button('customize-game-1245620').click();await button('save').waitFor();await button('save').focus();await page.keyboard.press('y');
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='workspace_select_all').length,2);
  assert.equal(await page.locator('[data-test-options-description]').count(),0);
  check('bulk failure preserves selection, retry works and shortcut is absent in customization '+lang);
 }
}
