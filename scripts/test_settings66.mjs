import assert from 'node:assert/strict';
export async function settings66({page,mount,button,check}){
 for(const lang of ['en','fr']){
  const fr=lang==='fr';await mount(lang);await page.getByRole('tab',{name:fr?'Réglages':'Settings',exact:true}).click();
  assert.equal(await page.locator('.collection-settings [data-collection-focus]').first().getAttribute('data-collection-focus'),'settings-setup');
  await button('settings-setup').click();await page.getByRole('heading',{name:fr?'Import de la bibliothèque Steam · facultatif':'Steam library import · optional',exact:true}).waitFor();
  const profile=page.getByLabel(fr?'Profil Steam · facultatif':'Steam profile · optional',{exact:false});
  const key=page.getByLabel(fr?'Clé Web API Steam · pour l’import uniquement':'Steam Web API key · for import only',{exact:true});
  await profile.fill('76561198000000000');await key.fill('a'.repeat(32));
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='import_owned').length,0);
  await page.getByRole('button',{name:fr?'Importer les jeux possédés':'Import owned games',exact:true}).click();await page.waitForTimeout(250);assert.equal(await key.inputValue(),'');
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='import_owned').length,1);
  await page.screenshot({path:`out/ui/collection/setup66-${lang}.png`});
  check('Setup first, optional direct Steam import and transient key '+lang);
  await button('back').click();await page.getByRole('tab',{name:fr?'Ajouter des jeux':'Add games',exact:true}).click();await button('manage-collection').click();await button('reorder-collection').click();await page.locator('[data-order-id]').first().waitFor();await button('back').click();
  check('Add Games exposes the existing complete collection reorder '+lang);
  await page.getByRole('tab',{name:fr?'Réglages':'Settings',exact:true}).click();await button('settings-advanced').click();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0].startsWith('settings_')).length,0);
  await page.getByRole('button',{name:fr?'Voir tous les réglages enregistrés':'View all saved settings',exact:true}).click();await page.locator('pre').waitFor();assert.match(await page.locator('pre').textContent(),/das-settings-v1/);
  await page.getByRole('button',{name:fr?'Tous les réglages TV':'All TV settings',exact:true}).click();await page.getByLabel(fr?'Budget de stockage · Mio, 0 = illimité':'Storage budget · MiB, 0 = unlimited',{exact:true}).waitFor();
  await page.getByRole('button',{name:fr?'Exporter les réglages en JSON':'Export settings JSON',exact:true}).click();await page.getByRole('status').filter({hasText:'AnimatedScreensaver/settings.json'}).waitFor();
  await page.getByRole('button',{name:fr?'Choisir un JSON à importer':'Choose JSON to import',exact:true}).click();await page.getByRole('button',{name:fr?'Confirmer l’import':'Confirm import',exact:true}).waitFor();
  assert.equal((await page.evaluate(()=>window.__collection.calls())).filter(c=>c[0]==='settings_import').length,0);
  await page.getByRole('button',{name:fr?'Confirmer l’import':'Confirm import',exact:true}).click();await page.getByRole('status').filter({hasText:'previous.json'}).waitFor();
  assert.equal(await page.getByRole('button',{name:fr?'Sauvegarder le JSON sur GitHub privé':'Save JSON to private GitHub',exact:true}).count(),0);
  const calls=await page.evaluate(()=>window.__collection.calls());assert.equal(calls.filter(c=>c[0]==='settings_github').length,0);
  assert.equal(calls.filter(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])).length,0);
  await page.screenshot({path:`out/ui/collection/advanced66-${lang}.png`});
  check('Advanced settings, local JSON roundtrip, no private upload, no media work '+lang);
 }
}
