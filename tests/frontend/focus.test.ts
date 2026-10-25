import test from 'node:test';
import assert from 'node:assert/strict';
import {takeNativeFocus,isTopNavigationRow,takeContentNativeFocus,canReturnToSidebar,stepSidebarFocus,crossDetailColumn,revealInContent} from '../../src/focus';
import {readFileSync} from 'node:fs';

test('native focus reaches the exact element, without focusing another Steam tree',()=>{
  const target={} as HTMLElement;let calls=0;
  const root:any={Element:{},m_rgChildren:[]};root.m_rgChildren.push(root,{Element:target,BTakeFocus:()=>{calls++;return true;}});
  assert.equal(takeNativeFocus(target,[{Root:root}]),true);assert.equal(calls,1);
  assert.equal(takeNativeFocus({} as HTMLElement,[{Root:root}]),false);
});
test('Up boundary is limited to the first navigation row, never a form input',()=>{
  const buttons=[0,0,50,50].map(top=>({getBoundingClientRect:()=>({top}),contains:(element:unknown)=>element===null}));
  const nav={contains:(element:unknown)=>buttons.includes(element as any),querySelectorAll:()=>buttons};
  const root={querySelector:()=>nav} as unknown as HTMLElement;
  assert.equal(isTopNavigationRow(root,buttons[0] as any),true);
  assert.equal(isTopNavigationRow(root,buttons[1] as any),true);
  assert.equal(isTopNavigationRow(root,buttons[2] as any),false);
  assert.equal(isTopNavigationRow(root,{} as Element),false);
  assert.equal(isTopNavigationRow(root,null),false);
});
test('route uses a native preferred focus root, scoped boundary and one scroll panel',()=>{
  const route=readFileSync(new URL('../../src/StudioRoute.tsx',import.meta.url),'utf8');
  const entry=readFileSync(new URL('../../src/index.tsx',import.meta.url),'utf8');
  assert(route.includes('preferredFocus'));assert(route.includes('onGamepadDirection={keepUpInPage}'));
  const workspace=readFileSync(new URL('../../src/CollectionStudio.tsx',import.meta.url),'utf8');
  assert.equal((route.match(/<ScrollPanel>/g)||[]).length,0);
  assert.equal((workspace.match(/<ScrollPanel>/g)||[]).length,1);
  assert(entry.includes('<StudioRoute><Studio'));assert(!route.includes('document.addEventListener'));
});
test('content native focus prefers exact control, then its closest wrapper, never another tree',()=>{
  const region:any={contains:(e:any)=>e===target||e===wrapper},wrapper:any={parentElement:region},target:any={parentElement:wrapper};
  let exact=0,wrapped=0,foreign=0;
  const trees=[{Root:{Element:{},BTakeFocus:()=>{foreign++;return true;},m_rgChildren:[
    {Element:wrapper,BTakeFocus:()=>{wrapped++;return true;}},{Element:target,BTakeFocus:()=>{exact++;return true;}}]}}];
  assert(takeContentNativeFocus(target,region,trees));assert.equal(exact,1);assert.equal(wrapped,0);assert.equal(foreign,0);
  trees[0].Root.m_rgChildren.pop();assert(takeContentNativeFocus(target,region,trees));assert.equal(wrapped,1);
  assert.equal(takeContentNativeFocus({} as HTMLElement,region,trees),false);
});
test('left-edge transfer excludes editors and controls with another control to their left',()=>{
  const box=(left:number)=>({left,right:left+50,top:0,bottom:30});
  const first:any={closest:()=>null,querySelector:()=>null,getClientRects:()=>[1],getBoundingClientRect:()=>box(100),contains:()=>false};
  const second:any={...first,getBoundingClientRect:()=>box(160)};
  const region:any={contains:()=>true,querySelectorAll:()=>[first,second]};
  assert(canReturnToSidebar(region,first));assert.equal(canReturnToSidebar(region,second),false);
  assert.equal(canReturnToSidebar(region,{closest:()=>({})} as any),false);
});
test('sidebar Up/Down follows one contiguous list, native controls first, never another Steam node',()=>{
  let selected=-1,dom=0,foreign=0,scroll=0;
  const buttons:any[]=Array.from({length:5},(_,index)=>({closest:()=>null,getClientRects:()=>[1],contains:()=>false,
    focus:()=>{dom++;selected=index;},scrollIntoView:()=>scroll++}));
  const nav:any={contains:(node:any)=>buttons.includes(node),querySelectorAll:()=>buttons};
  buttons.forEach(button=>button.parentElement=nav);
  const trees=[{Root:{Element:{},BTakeFocus:()=>{foreign++;return true;},m_rgChildren:buttons.map((button,index)=>({
    Element:button,BTakeFocus:()=>{selected=index;return true;}}))}}];
  for(let n=0;n<4;n++){assert(stepSidebarFocus(nav,buttons[n],1,trees));assert.equal(selected,n+1);}
  for(let n=4;n>0;n--){assert(stepSidebarFocus(nav,buttons[n],-1,trees));assert.equal(selected,n-1);}
  assert(stepSidebarFocus(nav,buttons[0],-1,trees));assert.equal(selected,0);
  assert(stepSidebarFocus(nav,buttons[4],1,trees));assert.equal(selected,0);
  assert.equal(dom,0);assert.equal(foreign,0);assert.equal(scroll,10);
  assert(stepSidebarFocus(nav,buttons[0],1,[]));assert.equal(dom,1);assert.equal(selected,1);
});
test('sidebar leaves an unavailable native target to Steam and skips disabled/hidden items',()=>{
  let focused=-1;
  const buttons:any[]=Array.from({length:3},(_,index)=>({closest:()=>index===1?{}:null,getClientRects:()=>[1],contains:()=>false,
    focus:()=>{focused=index;},scrollIntoView:()=>{}}));
  const nav:any={contains:(node:any)=>buttons.includes(node),querySelectorAll:()=>buttons};buttons.forEach(button=>button.parentElement=nav);
  assert.equal(stepSidebarFocus(nav,buttons[0],1,[{Root:{Element:{}}}]),false);assert.equal(focused,-1);
  assert.equal(stepSidebarFocus(nav,null,1,[]),false);
  assert(stepSidebarFocus(nav,buttons[0],1,[]));assert.equal(focused,2);
});

function sheet(){
 const box=(x:number)=>({left:x,right:x+80,top:100,bottom:140});
 let selected='',dom=0;
 const left:any={closest:()=>null,hasAttribute:()=>false,getClientRects:()=>[1],getBoundingClientRect:()=>box(20),contains:()=>false,focus:()=>{dom++;}};
 const right:any={...left,getBoundingClientRect:()=>box(300)};
 const a:any={contains:(e:any)=>e===left,querySelectorAll:()=>[left],getBoundingClientRect:()=>({left:0,right:200})};
 const b:any={contains:(e:any)=>e===right,querySelectorAll:()=>[right],getBoundingClientRect:()=>({left:280,right:480})};
 const region:any={contains:(e:any)=>[left,right,a,b,region].includes(e),querySelectorAll:()=>[a,b]};
 left.parentElement=a;right.parentElement=b;a.parentElement=b.parentElement=region;
 const trees=[{Root:{Element:{},m_rgChildren:[{Element:left,BTakeFocus:()=>{selected='left';return true;}},{Element:right,BTakeFocus:()=>{selected='right';return true;}}]}}];
 return {left,right,a,b,region,trees,selected:()=>selected,dom:()=>dom};
}
test('sheet D-pad crosses both columns with actual native focus callbacks only',()=>{
 const s=sheet();assert(crossDetailColumn(s.region,s.left,1,s.trees));assert.equal(s.selected(),'right');
 assert(crossDetailColumn(s.region,s.right,-1,s.trees));assert.equal(s.selected(),'left');assert.equal(s.dom(),0);
 assert.equal(crossDetailColumn(s.region,s.right,1,s.trees),false);
});
test('sheet crossing preserves editors, responsive stacking and unavailable native targets',()=>{
 const s=sheet();s.left.closest=()=>({});assert.equal(crossDetailColumn(s.region,s.left,1,s.trees),false);s.left.closest=()=>null;
 s.b.getBoundingClientRect=()=>({left:0,right:200});assert.equal(crossDetailColumn(s.region,s.left,1,s.trees),false);
 s.b.getBoundingClientRect=()=>({left:280,right:480});assert.equal(crossDetailColumn(s.region,s.left,1,[{Root:{Element:{}}}]),false);assert.equal(s.dom(),0);
});
test('sheet crossing leaves horizontal neighbours in the same action row to Steam',()=>{
 const s=sheet(),other:any={...s.left,getBoundingClientRect:()=>({left:110,right:190,top:100,bottom:140})};
 s.a.querySelectorAll=()=>[s.left,other];assert.equal(crossDetailColumn(s.region,s.left,1,s.trees),false);
});
test('revealing a control scrolls its content panel only, never a Steam/header ancestor',()=>{
 const previous=globalThis.getComputedStyle;(globalThis as any).getComputedStyle=()=>({overflowY:'auto'});
 try{const outer:any={scrollTop:0},owner:any={scrollHeight:1000,clientHeight:300,scrollTop:0,parentElement:outer,getBoundingClientRect:()=>({top:100,bottom:400})};
 const region:any={contains:(e:any)=>e===owner},target:any={closest:()=>region,parentElement:owner,getBoundingClientRect:()=>({top:700,bottom:740})};
 revealInContent(target);assert.equal(owner.scrollTop,352);assert.equal(outer.scrollTop,0);
 }finally{(globalThis as any).getComputedStyle=previous;}
});
