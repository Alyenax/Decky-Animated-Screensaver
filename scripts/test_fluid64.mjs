import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
export async function fluid64({page,mount,button,check,captureDir="out/ui/fluid64"}){
 await fs.mkdir(captureDir,{recursive:true});
 for(const width of [800,1280])for(const lang of ['fr','en']){
  await page.setViewportSize({width,height:800});await mount(lang,{jsaux:true,candidateSquare:true,jsauxState:{framing:'fill',reason:'',prepared:{ready:true}}});
  await page.locator('.collection-card').first().click();await button('pick-panel').waitFor();
  assert.equal(await page.locator('[data-faceplate-crop]').count(),0);
  const gaps=await page.locator('[data-detail-column=settings]').evaluate(n=>{
   const r=[...n.children].filter(x=>x.getBoundingClientRect().height>0).map(x=>x.getBoundingClientRect());return r.slice(1).map((x,i)=>x.top-r[i].bottom);
  });
  assert(gaps.length>=4&&gaps.every(n=>n>=12),'Every native control has visible spacing: '+JSON.stringify(gaps));
  await page.screenshot({path:`${captureDir}/sheet-${lang}-${width}.png`});
  await button('pick-panel').click();await button('asset-400').click();await page.locator('[data-panel-editor]').waitFor();
  const crop=page.getByLabel(lang==='fr'?'Cadrage vertical':'Vertical framing',{exact:true});
  for(let n=0;n<20;n++)await crop.press('ArrowRight');const y=await crop.evaluate(n=>Number(n instanceof HTMLInputElement?n.value:n.getAttribute('aria-valuenow')));assert.equal(y,70);
  const position=await page.locator('.collection-panel-preview').evaluate(n=>getComputedStyle(n).getPropertyValue('--panel-crop-y').trim());assert.equal(position,'70%');
  assert.equal(await button('centre-panel').count(),0);assert.equal(await page.locator('.collection-unsaved').count(),0);
  await page.screenshot({path:`${captureDir}/picker-${lang}-${width}.png`});
  await button('use-panel').click();assert.equal(await page.locator('[data-faceplate-crop]').count(),0);await button('save').click();
  const calls=await page.evaluate(()=>window.__collection.calls());const saved=calls.find(c=>c[0]==='workspace_draft')[1].patch;
  assert.deepEqual(saved.faceplate_crop,{x:50,y:70});assert.equal(saved.choices.panel,400);assert.deepEqual(saved.crop,{mode:'inherit',x:50,y:50});
  assert(!calls.some(c=>['workspace_prepare','workspace_install','jsaux_prepare'].includes(c[0])));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  check(`Faceplate crop beside selection / native gaps / exact saved draft / no preparation ${lang}/${width}`);
 }
}
