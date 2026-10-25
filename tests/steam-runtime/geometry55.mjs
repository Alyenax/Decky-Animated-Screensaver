import assert from 'node:assert/strict';

export async function listGeometry55(page){
 const rows=await page.locator('.collection-grid.list .collection-card').evaluateAll(cards=>cards.map(card=>{
  const media=card.querySelector('.collection-game-media'),copy=card.querySelector('.collection-game-copy'),action=card.querySelector('.collection-customize');
  const box=node=>{const b=node?.getBoundingClientRect();return b?{x:b.x,y:b.y,w:b.width,h:b.height,right:b.right,bottom:b.bottom}:null;};
  return {media:box(media),copy:box(copy),action:box(action),card:box(card),text:copy?.textContent};
 }));
 assert(rows.length>0,'List rows must render');
 for(const row of rows){
  assert(row.media&&row.copy,'Actual list requires explicit media/text wrappers');
  assert(row.media.w>=80&&row.media.h>=30,'List artwork has a positive bounded box');
  assert(row.copy.w>80&&row.copy.h>20&&row.text.trim(),'List title/status has independent readable space');
  assert(row.media.right<=row.copy.x+1,'List text never overlaps artwork');
  assert(row.media.bottom<=row.card.bottom+2&&row.copy.bottom<=row.card.bottom+2,'Row contains media/text bounds');
  if(row.action)assert(row.copy.right<=row.action.x+1,'Customize never overlaps list text');
 }
 return {rows:rows.length,first:rows[0]};
}

export async function playerGeometry55(page){
 const value=await page.locator('.collection-player-controls').evaluate(controls=>{
  const box=node=>{const b=node.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height,right:b.right,bottom:b.bottom};};
  return {controls:box(controls),buttons:[...controls.querySelectorAll('button')].map(button=>({text:button.textContent,disabled:button.disabled,...box(button)})),stage:box(controls.parentElement.querySelector('iframe'))};
 });
 assert.equal(value.buttons.length,4,'Full Player exposes Previous / Pause / Next / Close');
 for(let i=0;i<4;i++){
  const button=value.buttons[i];assert(!button.disabled&&button.w>=60&&button.h>=32&&button.h<=80,'Each preview action is compact and enabled');
  assert(Math.abs(button.y-value.buttons[0].y)<=1,'All preview actions stay in the same native row');
  assert(button.x>=value.controls.x-1&&button.right<=value.controls.right+1,'Player action is contained');
  if(i)assert(value.buttons[i-1].right<=button.x+1,'Preview actions do not overlap');
 }
 assert(value.stage.h>120&&value.stage.h<600,'Preview stage is bounded');
 return value;
}
