import assert from 'node:assert/strict';
import path from 'node:path';

export async function recovery57(page,out,captures,geometry){
 for(const width of [800,1280])for(const classic of [true,false])for(const lang of ['fr','en']){
  await page.setViewportSize({width,height:width===1280?720:800});
  await page.evaluate(({classic,lang})=>{
   window.__classic=classic;(document.getElementById('surface')||document.getElementById('QuickAccess-Menu')).id='surface';document.getElementById('root').removeAttribute('data-qam');
   window.__collection.mount(lang,{activity:true,task:{state:'partial',stage:'faceplate',tv_state:'prepared',faceplate_state:'repair_required',error:'JSAUX_SYNC_WINDOW'},jsaux:true,jsauxState:{reason:'',preparation_error:'JSAUX_SYNC_WINDOW',prepared:{ready:false}}});
  },{classic,lang});
  await page.locator('[data-collection-focus=independent-choice]').waitFor();await page.waitForTimeout(200);
  for(const state of ['capacity','confirmation']){
   if(state==='confirmation'){await page.locator('[data-collection-focus=independent-choice]').click();await page.locator('[data-collection-focus=confirm]').waitFor();}
   const selector=state==='capacity'?'.collection-faceplate-recovery .collection-actions':'.collection-confirm .collection-actions';
   const rects=await page.locator(selector+' button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom,textOverflow:n.scrollWidth>n.clientWidth+2};}));
   assert.equal(rects.length,2);assert(Math.abs(rects[0].y-rects[1].y)<1&&Math.abs(rects[0].h-rects[1].h)<1,'Actions share a symmetric native row');
   assert(rects[0].right<=rects[1].x+1&&rects.every(r=>r.w>=100&&r.h>=40&&!r.textOverflow),'Actions remain separate, readable and bounded');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   const calls=await page.evaluate(()=>window.__collection.calls());assert(!calls.some(c=>['workspace_prepare','workspace_install','jsaux_configure'].includes(c[0])));
   const tag=`${state}-${lang}-${width}-${classic?'classic':'current'}`;geometry.push({tag,passed:true,rects});
   if(state==='capacity'){
    const orange=await page.locator('.collection-faceplate-recovery>p').evaluate(n=>getComputedStyle(n).color.match(/\d+/g).map(Number));
    assert(orange[0]>orange[1]&&orange[1]>orange[2],'Problem wording is orange under native Steam styles');
   }
   await page.screenshot({path:path.join(out,tag+'.png')});captures.push(tag+'.png');
  }
  await page.evaluate(lang=>window.__collection.mount(lang,{jsauxState:{detected:true,compatible:true,enabled:true,mode:'async',reason:'',installed:true,prepared:{ready:true,sync_admissible:true,bytes:4096}}}),lang);
  await page.locator('.faceplate-preparation-title.is-ready').waitFor();
  const green=await page.locator('.faceplate-preparation-title').evaluate(n=>getComputedStyle(n).color.match(/\d+/g).map(Number));
  assert(green[1]>green[0]&&green[1]>green[2],'Prepared wording is green under native Steam styles');
  const tag=`ready-${lang}-${width}-${classic?'classic':'current'}`;geometry.push({tag,passed:true,green});await page.screenshot({path:path.join(out,tag+'.png')});captures.push(tag+'.png');
 }
}
