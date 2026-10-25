import assert from 'node:assert/strict';

/** Real production React + slow RPC responses. Tabs is still the documented
 * DOM adapter: these are data/layout stability tests, not native transition or
 * controller evidence. The fixture RPC is restored even when an assertion fails. */
export async function stability56(page,lang='en'){
 await page.evaluate(()=>{
  window.__stabilityBaseRpc=window.__collectionRpc;
  window.__collectionRpc=async(name,payload)=>{
   if(name==='workspace_library'||name==='workspace_draft')await new Promise(resolve=>setTimeout(resolve,350));
   return window.__stabilityBaseRpc(name,payload);
  };
 });
 try{
  await page.evaluate(async lang=>{await window.__collection.mount(lang,{add:true});},lang);
  const balatro=page.locator('.collection-select-main').filter({hasText:'Balatro'});
  await balatro.waitFor();
  const before=await page.evaluate(()=>window.__collection.calls().filter(call=>call[0]==='workspace_library').length);
  await page.evaluate(()=>{
   window.__stabilityGridY=[];window.__stabilitySampling=true;
   const sample=()=>{const grid=document.querySelector('.collection-grid');if(grid)window.__stabilityGridY.push(grid.getBoundingClientRect().y);if(window.__stabilitySampling)requestAnimationFrame(sample);};sample();
  });
  await balatro.click();
  await page.waitForFunction(()=>window.__collection.state().workspace.draft_count===1);
  await page.waitForTimeout(700);
  const selection=await page.evaluate(()=>{window.__stabilitySampling=false;return {ys:window.__stabilityGridY,libraryCalls:window.__collection.calls().filter(call=>call[0]==='workspace_library').length};});
  assert(selection.ys.length>=10,'Selection stability samples multiple real browser frames');
  assert(Math.max(...selection.ys)-Math.min(...selection.ys)<=1,'Selection does not shift the grid while saving or reloading');
  assert.equal(selection.libraryCalls,before,'Membership selection updates local rows without redundant library reload');
  // Fresh Add scope contains Balatro; fresh Collection does not. A delayed
  // response must never leave the Add results painted under Collection.
  await page.evaluate(async lang=>{await window.__collection.mount(lang,{add:true});},lang);
  await page.locator('.collection-select-main').filter({hasText:'Balatro'}).waitFor();
  await page.getByRole('tab',{name:lang==='fr'?'Ma collection':'My collection',exact:true}).click();
  const immediate=await page.evaluate(()=>document.querySelector('.collection-grid')?.textContent||'');
  assert(!immediate.includes('Balatro'),'New Collection scope never displays stale Add-only game while RPC is pending');
  await page.waitForFunction(()=>{const cards=[...document.querySelectorAll('.collection-grid .collection-card')];return cards.length===8&&!cards.some(card=>card.textContent.includes('Balatro'));});
  // The collection's page0 prefix is known, but compact density has no exact
  // cache entry yet. Returning from Appearance must reuse only that same scope.
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();
  await page.locator('[data-collection-focus="settings-appearance"]').click();
  await page.getByRole('combobox',{name:lang==='fr'?'Présentation de la collection':'Collection view',exact:true}).selectOption('compact');
  await page.waitForFunction(()=>window.__collection.state().workspace.layout==='compact');
  await page.locator('[data-collection-focus="back"]').click();
  await page.getByRole('tab',{name:lang==='fr'?'Ma collection':'My collection',exact:true}).click();
  const returned=await page.evaluate(()=>[...document.querySelectorAll('.collection-grid.compact .collection-card')].map(card=>card.textContent));
  assert.equal(returned.length,8,'Changing density in Settings returns immediately to the known Collection prefix');
  assert(!returned.some(text=>text.includes('Balatro')),'Density cache never borrows the Add scope');
  await page.evaluate(()=>{
   window.__stabilityDensityRows=[];window.__stabilitySampling=true;
   const sample=()=>{window.__stabilityDensityRows.push(document.querySelectorAll('.collection-grid.compact .collection-card').length);if(window.__stabilitySampling)requestAnimationFrame(sample);};sample();
  });
  await page.waitForTimeout(650);
  const densityRows=await page.evaluate(()=>{window.__stabilitySampling=false;return window.__stabilityDensityRows;});
  assert(densityRows.length>=10&&densityRows.every(count=>count===8),'Known Collection prefix stays visible through compact-density refresh');
  return {lang,selectionSamples:selection.ys.length,gridMovement:Math.max(...selection.ys)-Math.min(...selection.ys),redundantLibraryCalls:selection.libraryCalls-before,staleScopeRejected:true,densityCacheImmediateRows:returned.length,densityCacheSamples:densityRows.length,limitations:'Production React/RPC/layout; DOM Tabs adapter, not native transition or physical input proof.'};
 }finally{
  await page.evaluate(()=>{window.__stabilitySampling=false;if(window.__stabilityBaseRpc)window.__collectionRpc=window.__stabilityBaseRpc;delete window.__stabilityBaseRpc;});
 }
}
