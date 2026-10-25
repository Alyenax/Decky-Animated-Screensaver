/** Scoped native focus; no global Steam input or search-bar patch. */
export type FocusNode={Element?:Element;BTakeFocus?:()=>boolean;m_rgChildren?:FocusNode[]};
export function takeNativeFocus(element:HTMLElement,trees:{Root?:FocusNode}[]):boolean{
  const seen=new Set<FocusNode>();
  for(const tree of trees){
    const pending=tree.Root?[tree.Root]:[];
    while(pending.length && seen.size<5000){
      const node=pending.pop()!;if(seen.has(node))continue;seen.add(node);
      if(node.Element===element && typeof node.BTakeFocus==='function')return Boolean(node.BTakeFocus());
      if(Array.isArray(node.m_rgChildren))pending.push(...node.m_rgChildren);
    }
  }
  return false;
}

export function focusUpdatePrimary(root:HTMLElement,trees:{Root?:FocusNode}[]):boolean{
  const button=root.querySelector<HTMLElement>('[data-update-primary] button:not(:disabled),[data-update-primary] [role="button"]:not([aria-disabled="true"])');
  if(!button)return false;
  revealInContent(button);
  if(!takeNativeFocus(button,trees))button.focus({preventScroll:true});
  return true;
}

const CONTROLS='button,input,select,textarea,[role="button"],[role="slider"],[role="combobox"],[tabindex]:not([tabindex="-1"])';
export function visibleControls(root:HTMLElement):HTMLElement[]{
  return Array.from(root.querySelectorAll<HTMLElement>(CONTROLS)).filter(element=>
    !element.closest('[disabled],[aria-disabled="true"],[hidden],[inert],[aria-hidden="true"]')&&element.getClientRects().length>0);
}

/** Reveal inside the one content scroller, never scroll Steam or the tab/header. */
export function revealInContent(target:HTMLElement):void{
  const region=target.closest<HTMLElement>('.collection-scroll-owner');if(!region)return;
  for(let node=target.parentElement;node&&region.contains(node);node=node.parentElement){
    if(node.scrollHeight>node.clientHeight&&['auto','scroll'].includes(getComputedStyle(node).overflowY)){
      const panel=node.getBoundingClientRect(),box=target.getBoundingClientRect();
      if(box.top<panel.top+12)node.scrollTop-=panel.top+12-box.top;
      else if(box.bottom>panel.bottom-12)node.scrollTop+=box.bottom-panel.bottom+12;
      return;
    }
  }
}

/** Only bridge the two sheet columns. Native editors/rows retain their arrows. */
export function crossDetailColumn(region:HTMLElement,element:Element|null,direction:-1|1,trees:{Root?:FocusNode}[]):boolean{
  if(!element||!region.contains(element)||element.closest('input,select,textarea,[contenteditable="true"],[role="slider"],[aria-expanded="true"]'))return false;
  const columns=Array.from(region.querySelectorAll<HTMLElement>('[data-detail-column]'));
  if(columns.length!==2)return false;
  const index=columns.findIndex(column=>column.contains(element));
  if(index<0||index+direction<0||index+direction>1)return false;
  const left=columns[0].getBoundingClientRect(),right=columns[1].getBoundingClientRect();
  if(right.left<left.right-2)return false; // Single-column responsive layout.
  const targets=visibleControls(columns[index+direction]).filter(control=>!control.hasAttribute('data-detail-column'));
  const leaves=targets.filter(control=>!targets.some(other=>other!==control&&control.contains(other)));
  const from=element.getBoundingClientRect(),middle=(from.top+from.bottom)/2;
  if(visibleControls(columns[index]).some(other=>{
    if(other===element||other.contains(element)||element.contains(other))return false;
    const box=other.getBoundingClientRect();
    return Math.min(box.bottom,from.bottom)-Math.max(box.top,from.top)>4&&(direction===1?box.left>=from.right-2:box.right<=from.left+2);
  }))return false;
  const target=leaves.sort((a,b)=>Math.abs((a.getBoundingClientRect().top+a.getBoundingClientRect().bottom)/2-middle)-Math.abs((b.getBoundingClientRect().top+b.getBoundingClientRect().bottom)/2-middle))[0];
  if(!target)return false;
  const taken=takeContentNativeFocus(target,region,trees);
  if(!taken&&trees.length)return false;
  if(!taken)target.focus({preventScroll:true});
  revealInContent(target);return true;
}

/** Native ScrollPanel can add more than one wrapper. Only walk this content's
 * ancestors; never scroll Steam, a code field or an unrelated nested editor. */
export function scrollContentToTop(region:HTMLElement):void{
  const page=region.querySelector<HTMLElement>('.collection-content,.das-page');
  for(let node=page?.parentElement;node&&region.contains(node);node=node.parentElement){
    node.scrollTop=0;
    if(node===region)break;
  }
}

/** Up on the first actionable row must also reveal its non-focusable heading.
 * Do not hijack editing, later rows or native scrolling elsewhere. */
export function revealContentTop(region:HTMLElement,element:Element|null):boolean{
  if(!element||element===region||!region.contains(element))return false;
  if(element.closest('input,select,textarea,[contenteditable="true"],[role="slider"],[role="combobox"],[role="textbox"],iframe'))return false;
  const controls=visibleControls(region);
  const target=controls.find(control=>control===element||control.contains(element)||element.contains(control));
  if(!target||!controls.length)return false;
  const top=Math.min(...controls.map(control=>control.getBoundingClientRect().top));
  if(target.getBoundingClientRect().top>top+2)return false;
  scrollContentToTop(region);return true;
}

/** Steam sometimes registers the native Field wrapper, not its inner button. */
export function takeContentNativeFocus(element:HTMLElement,region:HTMLElement,trees:{Root?:FocusNode}[]):boolean{
  if(!region.contains(element))return false;
  const ancestors=new Map<Element,number>();let distance=0;
  for(let parent:HTMLElement|null=element;parent&&(parent!==region||parent===element);parent=parent.parentElement){
    if(!region.contains(parent))break;ancestors.set(parent,distance++);
  }
  const seen=new Set<FocusNode>(),candidates:{node:FocusNode;distance:number}[]=[];
  for(const tree of trees){
    const pending=tree.Root?[tree.Root]:[];
    while(pending.length&&seen.size<5000){
      const node=pending.pop()!;if(seen.has(node))continue;seen.add(node);
      if(node.Element&&ancestors.has(node.Element)&&typeof node.BTakeFocus==='function')candidates.push({node,distance:ancestors.get(node.Element)!});
      if(Array.isArray(node.m_rgChildren))pending.push(...node.m_rgChildren);
    }
  }
  for(const {node} of candidates.sort((a,b)=>a.distance-b.distance)){try{if(node.BTakeFocus!())return true;}catch{}}
  return false;
}

/** Contiguous sidebar order, independent of Steam's geometric neighbour search.
 * Do not consume an event if a present native tree cannot take the target. */
export function stepSidebarFocus(nav:HTMLElement,element:Element|null,delta:-1|1,trees:{Root?:FocusNode}[]):boolean{
  if(!element||!nav.contains(element))return false;
  const buttons=Array.from(nav.querySelectorAll<HTMLElement>('[data-das-tab]')).filter(button=>
    !button.closest('[disabled],[aria-disabled="true"],[hidden],[inert],[aria-hidden="true"]')&&button.getClientRects().length>0);
  const index=buttons.findIndex(button=>button===element||button.contains(element)||element.contains(button));
  if(index<0)return false;
  const next=Math.max(0,Math.min(buttons.length-1,index+delta)),target=buttons[next];
  if(next!==index){
    const taken=takeContentNativeFocus(target,nav,trees);
    if(!taken&&trees.length)return false;
    if(!taken)target.focus({preventScroll:true});
  }
  target.scrollIntoView({block:'nearest'});return true;
}

/** Leave editing and horizontal rows/grids to Steam; only cross the left edge. */
export function canReturnToSidebar(region:HTMLElement,element:Element|null):boolean{
  if(!element||!region.contains(element))return false;
  const editors='input,select,textarea,[contenteditable="true"],[role="slider"],[role="combobox"],[role="textbox"],iframe';
  if(element.closest(editors)||element!==region&&element.querySelector(editors))return false;
  const controls=visibleControls(region),target=controls.find(control=>control===element||control.contains(element));
  if(!target)return element===region;
  const rect=target.getBoundingClientRect();
  return !controls.some(other=>{
    if(other===target||other.contains(target)||target.contains(other))return false;
    const box=other.getBoundingClientRect();
    return box.right<=rect.left+2&&Math.min(box.bottom,rect.bottom)-Math.max(box.top,rect.top)>2;
  });
}

/** Only consume Up at the top navigation row. Inputs and other directions stay native. */
export function isTopNavigationRow(root:HTMLElement,element:Element|null):boolean{
  const nav=root.querySelector('[role="tablist"],.das .nav');
  if(!nav || !element || !nav.contains(element))return false;
  const buttons=Array.from(nav.querySelectorAll<HTMLElement>('[role="tab"],[data-das-tab],button:not(:disabled),[role="button"]'));
  const target=buttons.find(button=>button===element || button.contains(element) || element.contains(button));
  if(!target || !buttons.length)return false;
  return target.getBoundingClientRect().top<=Math.min(...buttons.map(button=>button.getBoundingClientRect().top))+2;
}
