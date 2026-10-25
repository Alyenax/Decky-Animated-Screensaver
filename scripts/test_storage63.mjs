import assert from 'node:assert/strict';
export async function storage63({page,mount,button,check}){
 for(const lang of ['fr','en']){
  await mount(lang);await page.getByRole('tab',{name:lang==='fr'?'Réglages':'Settings'}).click();await button('settings-assistance').click();
  await page.getByRole('button',{name:lang==='fr'?'Stockage et imports':'Storage and imports',exact:true}).click();
  const storage=page.getByRole('combobox',{name:lang==='fr'?'Budget de stockage':'Storage budget'});
  const visual=page.getByRole('combobox',{name:lang==='fr'?'Taille maximale par visuel':'Maximum size per visual'});
  assert.equal(await storage.inputValue(),'10240');assert.equal(await storage.locator('option:checked').innerText(),lang==='fr'?'10 Go':'10 GB');
  assert.equal(await visual.inputValue(),'256');assert.equal(await visual.locator('option:checked').innerText(),lang==='fr'?'256 Mo':'256 MB');
  for(const value of [12288,15360,0]){
   await storage.selectOption(String(value));await page.waitForFunction(value=>document.querySelector('select[aria-label="Storage budget"],select[aria-label="Budget de stockage"]')?.value===String(value),value);
   assert.equal(await storage.locator('option:checked').innerText(),value===0?(lang==='fr'?'Illimité':'Unlimited'):`${value/1024} ${lang==='fr'?'Go':'GB'}`);
  }
  await visual.selectOption('0');await page.waitForFunction(()=>document.querySelector('select[aria-label="Maximum size per visual"],select[aria-label="Taille maximale par visuel"]')?.value==='0');
  assert.equal(await visual.locator('option:checked').innerText(),lang==='fr'?'Illimité':'Unlimited');
  const calls=await page.evaluate(()=>window.__collection.calls());
  assert.equal(calls.filter(c=>['workspace_prepare','workspace_install','purge'].includes(c[0])).length,0);
  assert(calls.some(c=>c[0]==='configure'&&c[1].patch.storage_mib===0));
  check('storage defaults, 12/15/unlimited choices and per-visual nomenclature without automatic work '+lang);
 }
}
