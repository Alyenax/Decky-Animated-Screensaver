import {useEffect,useRef,type ReactNode} from 'react';
import {Focusable,GamepadButton,NavEntryPositionPreferences,getGamepadNavigationTrees,type GamepadEvent} from '@decky/ui';
import {takeNativeFocus,takeContentNativeFocus,isTopNavigationRow,scrollContentToTop,revealContentTop} from './focus';
import {CSS} from './theme';

/** One bounded native scroll owner, below Steam's header and above its footer. */
export function StudioRoute({children,focusUpdates=false}:{children:ReactNode;focusUpdates?:boolean}){
  const root=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(focusUpdates)return; // UpdatesPanel owns the explicit action focus.
    const frame=requestAnimationFrame(()=>{
      const region=root.current;if(!region)return;
      const selected=region.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
      try{
        const nav=selected?.closest<HTMLElement>('[role="tablist"]');
        if(selected&&nav&&takeContentNativeFocus(selected,nav,getGamepadNavigationTrees() || []))return;
        takeNativeFocus(region,getGamepadNavigationTrees() || []);
        selected?.focus({preventScroll:true});
      }catch{selected?.focus({preventScroll:true});}
    });
    return()=>cancelAnimationFrame(frame);
  },[focusUpdates]);
  const showPageTop=()=>{
    const panel=root.current?.querySelector<HTMLElement>('[role="tabpanel"],.collection-nested-scroll');
    if(panel)scrollContentToTop(panel);
  };
  const revealHeading=(element:Element|null)=>{
    const panel=root.current?.querySelector<HTMLElement>('[role="tabpanel"],.collection-nested-scroll');
    if(!panel||![panel,...Array.from(panel.querySelectorAll<HTMLElement>('div'))].some(node=>node.scrollTop>1))return false;
    return revealContentTop(panel,element);
  };
  const keepUpInPage=(event:GamepadEvent)=>{
    if(event.detail?.button!==GamepadButton.DIR_UP || !root.current)return;
    const region=root.current;
    const active=document.activeElement;
    const focused=active && active!==region && region.contains(active) ? active
      : Array.from(region.querySelectorAll('.gpfocus')).pop() || active;
    if(!isTopNavigationRow(region,focused)&&!revealHeading(focused))return;
    event.preventDefault();event.stopPropagation();
    showPageTop();
  };
  return <Focusable ref={root} className="das-route" preferredFocus flow-children="column"
    navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD}
    onGamepadDirection={keepUpInPage} onKeyDown={event=>{
      if(event.key==='ArrowUp' && !event.altKey && !event.ctrlKey && !event.metaKey
        && root.current && (isTopNavigationRow(root.current,event.target as Element)||revealHeading(event.target as Element))){
        event.preventDefault();event.stopPropagation();
        showPageTop();
      }
    }}>
    <style>{CSS}</style>{children}
  </Focusable>;
}
