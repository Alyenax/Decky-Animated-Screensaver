// Production behavior with explicit browser Menu/RPC adapters. Not Steam focus.
import assert from 'node:assert/strict';
export async function correction55({page,mount,button,check}){
 for(const lang of ['fr','en']){
  await mount(lang,{pending:true});
  const before=await page.evaluate(()=>window.__collection.calls().filter(c=>c[0]==='workspace_prepare').length);
  await button('manage-collection').click();await page.getByRole('menu').waitFor();
  assert.equal(await page.getByRole('menuitem').count(),4);
  await page.getByRole('menuitem').first().focus();await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({state:'detached'});
  assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('data-collection-focus')),'manage-collection');
  assert.equal(await page.evaluate(()=>window.__collection.calls().filter(c=>c[0]==='workspace_prepare').length),before);
  check('secondary menu cancel restores trigger without preparation '+lang);
  await mount(lang,{jsaux:true,jsauxState:{reason:'',calibration:{available:true,offset_ms:0}}});
  await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings',exact:true}).click();await button('settings-jsaux').click();
  await page.getByRole('button',{name:lang==='fr'?'Détails Faceplate JSAUX':'Faceplate JSAUX details',exact:true}).click();
  await page.getByRole('button',{name:lang==='fr'?'Alignement visuel':'Visual alignment',exact:true}).click();
  const early=page.getByRole('button',{name:lang==='fr'?'La TV change trop tôt':'TV changes too early',exact:true});
  await early.click();
  assert((await page.locator('.collection-settings-form').innerText()).includes('0.5 s'));
  await page.getByRole('button',{name:lang==='fr'?'Enregistrer le calage':'Save alignment',exact:true}).click();
  assert((await page.evaluate(()=>window.__collection.calls())).some(c=>c[0]==='jsaux_configure'&&c[1].patch.alignment_ms===500));
  check('Faceplate details and alignment commands preserve real configuration '+lang);
 }
}
