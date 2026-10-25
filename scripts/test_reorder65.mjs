import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
// Exercises the actual installed @decky/ui ReorderableList implementation.
// Field/focus/button events are DOM adapters, not a real Steam controller engine.
export async function reorder65({page,mount,button,check,captureDir='out/ui/reorder65'}){
 await fs.mkdir(captureDir,{recursive:true});
 const region=()=>page.locator('[data-ui-part=collection-order]');
 const ids=()=>region().locator('[data-order-id]').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.orderId)));
 const rows=()=>region().locator('.native-item');
 const secondary=()=>region().locator('[data-test-secondary-description]');
 const x=async()=>{await secondary().evaluate(n=>n.dispatchEvent(new CustomEvent('das-test-secondary',{bubbles:true,cancelable:true})));await page.waitForTimeout(60);};
 const direction=async(index,button)=>{await rows().nth(index).evaluate((n,b)=>n.dispatchEvent(new CustomEvent('das-test-button',{bubbles:true,cancelable:true,detail:{button:b}})),button);};
 const writes=()=>page.evaluate(()=>window.__collection.calls().filter(c=>['workspace_reorder','workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])));
 const open=async()=>{await button('manage-collection').click();assert.equal(await page.getByRole('menuitem').first().getAttribute('data-collection-focus'),'reorder-collection');await button('reorder-collection').click();await region().locator('[data-order-id]').first().waitFor();};
 for(const width of [800,1280])for(const lang of ['fr','en']){
  await page.setViewportSize({width,height:800});await mount(lang,{manyOrder:true});await open();
  const initial=await ids();assert.equal(initial.length,32,'Reorder loads the complete collection beyond lazy pages');
  assert.equal(await secondary().getAttribute('data-test-secondary-description'),'Reorder');assert.equal((await writes()).length,0);
  await rows().first().focus();await x();await page.waitForTimeout(380);
  assert.equal(await secondary().getAttribute('data-test-secondary-description'),'Save Order');
  const style=await rows().evaluateAll(nodes=>nodes.slice(0,2).map(n=>({transform:getComputedStyle(n.parentElement).transform,opacity:getComputedStyle(n.parentElement).opacity})));
  assert.equal(style[0].opacity,'1');assert.equal(style[1].opacity,'0.7');assert.match(style[1].transform,/0\.9/);
  await direction(0,10);await direction(1,10);let changed=await ids();assert.deepEqual(changed.slice(0,3),[initial[1],initial[2],initial[0]]);
  await page.evaluate(()=>window.__collection.patch({workspace:{...window.__collection.state().workspace,pending_count:0}}));await page.waitForTimeout(1500);
  assert.deepEqual(await ids(),changed,'Status polling cannot reset the native draft');assert.equal((await writes()).length,0);
  const topBeforeSave=(await rows().first().boundingBox()).y;await page.screenshot({path:`${captureDir}/moving-${lang}-${width}.png`});await x();
  await page.getByText(lang==='fr'?'Ordre enregistré':'Order saved',{exact:true}).waitFor();
  assert(Math.abs((await rows().first().boundingBox()).y-topBeforeSave)<=1,'Saving status must not shift the list');
  const requests=await writes();assert.equal(requests.length,1);assert.deepEqual(requests[0][1].appids,changed);
  assert.equal(await secondary().getAttribute('data-test-secondary-description'),'Reorder');
  await button('back').click();await page.locator('.collection-grid.list').waitFor();await page.waitForTimeout(350);
  assert.equal(await page.locator('.collection-card').first().getAttribute('data-collection-focus'),'game-'+changed[0]);
  assert.equal(await page.getByRole('combobox',{name:lang==='fr'?'Présentation':'View',exact:true}).inputValue(),'list');
  await open();assert.deepEqual(await ids(),changed);await page.screenshot({path:`${captureDir}/saved-${lang}-${width}.png`});
  check(`native Decky reorder X / exact compression / full collection / stable polling / persisted list ${lang}/${width}`);
 }
 for(const lang of ['fr','en']){
  await mount(lang,{orderFailure:true});await open();const original=await ids();await rows().first().focus();await x();await direction(0,10);await x();
  await page.locator('[data-recovery-card]').waitFor();assert.deepEqual((await ids()).slice(0,2),[original[1],original[0]]);
  await x();await x();await page.getByText(lang==='fr'?'Ordre enregistré':'Order saved',{exact:true}).waitFor();assert.equal((await writes()).length,2);
  check('failed order save retains draft and retries explicitly '+lang);
  await mount(lang);await open();await rows().first().focus();await x();await direction(0,10);await direction(1,2);
  await page.getByText(lang==='fr'?'Ordre enregistré':'Order saved',{exact:true}).waitFor();
  assert.equal(await secondary().getAttribute('data-test-secondary-description'),'Reorder');assert.equal((await writes()).length,1);
  check('native controller B saves and exits reordering '+lang);
  await mount(lang);await open();const stale=await ids();await rows().first().focus();await x();await direction(0,10);
  await page.evaluate(appid=>window.__collectionRpc('workspace_draft',{appid,patch:{collection_member:false,excluded:false}}),stale[0]);await x();
  await page.locator('[data-recovery-card]').waitFor();assert.match(await page.locator('[data-recovery-card]').innerText(),lang==='fr'?/collection a changé/:/collection changed/i);
  await button('back').click();await button('manage-collection').waitFor();assert.equal((await writes()).length,1,'Back can leave a stale order without a failing save loop');
  check('concurrent membership is rejected with a usable exit '+lang);
  await mount(lang,{orderDelay:600});await open();await rows().first().focus();await x();await direction(0,10);
  await button('back').click();assert.equal(await region().count(),1);assert.equal(await region().getAttribute('aria-busy'),'true');
  await button('back').click();assert.equal((await writes()).length,1,'Repeated Back cannot duplicate a pending save');
  await page.getByText(lang==='fr'?'Ordre enregistré':'Order saved',{exact:true}).waitFor();await button('back').click();await page.locator('.collection-grid.list').waitFor();
  assert.equal((await writes()).length,1);check('Back saves native draft once and preserves the page until acknowledgement '+lang);
 }
}
