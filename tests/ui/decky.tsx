// Browser-only control adapters. They are never bundled into the plugin ZIP.
import {createElement,forwardRef,useEffect,useImperativeHandle,useRef} from 'react';
import {createRoot} from 'react-dom/client';
export const Focusable=forwardRef<HTMLDivElement,any>(({children,className,style,onFocusCapture,onBlurCapture,onKeyDown,onGamepadDirection,onCancel,onActivate,onSecondaryButton,onOptionsButton,onOptionsActionDescription,onButtonDown,onSecondaryActionDescription,onGamepadFocus,onGamepadBlur,...props},ref)=>{
  const node=useRef<HTMLDivElement>(null);useImperativeHandle(ref,()=>node.current!);
  useEffect(()=>{
    const element=node.current;if(!element)return;
    const secondary=(e:any)=>onSecondaryButton?.(e);element.addEventListener('das-test-secondary',secondary);
    if(!onGamepadDirection)return()=>element.removeEventListener('das-test-secondary',secondary);
    element.addEventListener('das-test-direction',onGamepadDirection);
    return()=>{element.removeEventListener('das-test-direction',onGamepadDirection);element.removeEventListener('das-test-secondary',secondary);};
  },[onGamepadDirection,onSecondaryButton]);
  useEffect(()=>{const element=node.current;if(!element||!onCancel)return;element.addEventListener('das-test-cancel',onCancel);return()=>element.removeEventListener('das-test-cancel',onCancel);},[onCancel]);
  useEffect(()=>{const element=node.current;if(!element||!onOptionsButton)return;element.addEventListener('das-test-options',onOptionsButton);return()=>element.removeEventListener('das-test-options',onOptionsButton);},[onOptionsButton]);
  useEffect(()=>{const el=node.current;if(!el||!onButtonDown)return;el.addEventListener('das-test-button',onButtonDown);return()=>el.removeEventListener('das-test-button',onButtonDown);},[onButtonDown]);
  return <div ref={node} onFocus={e=>{if(e.target===e.currentTarget)onGamepadFocus?.(e);}} onBlur={e=>{if(e.target===e.currentTarget)onGamepadBlur?.(e);}} data-test-secondary-description={onSecondaryActionDescription} data-test-options-description={onOptionsActionDescription} className={className} style={style} onClick={onActivate?()=>onActivate(new Event('activate')):props.onClick} onFocusCapture={onFocusCapture} onBlurCapture={onBlurCapture} onKeyDown={onKeyDown} {...Object.fromEntries(Object.entries(props).filter(([k])=>k.startsWith('data-')||k.startsWith('aria-')||k==='role'||k==='id'||k==='tabIndex'||k==='onClick'))}>{children}</div>;
});
export const ScrollPanel=({children}:any)=>(window as any).__dasNestedScroll
  ?<div data-native-scroll-wrapper style={{height:'100%',overflow:'hidden'}}><div data-native-scroll-panel style={{height:'100%',overflowY:'auto'}}><div data-native-scroll-inner>{children}</div></div></div>
  :<div data-native-scroll-panel>{children}</div>;
export const GamepadButton={CANCEL:2,DIR_UP:9,DIR_DOWN:10,DIR_LEFT:11,DIR_RIGHT:12};
export const NavEntryPositionPreferences={PREFERRED_CHILD:4,MAINTAIN_X:2,MAINTAIN_Y:3};
export const getGamepadNavigationTrees=()=>((window as any).__dasFocusTrees||[]);
export const PanelSection=({title,children}:any)=><section className="quickaccesscontrols_PanelSection_test">{title&&<h2>{title}</h2>}{children}</section>;
export const PanelSectionRow=({children}:any)=><div className="native-row quickaccesscontrols_PanelSectionRow_test gamepaddialog_ControlsListChild_test"><div className="gamepaddialog_BackgroundAnimation_test"/>{children}</div>;
export const DialogButton=forwardRef<HTMLButtonElement,any>(({children,noFocusRing,onGamepadDirection,...props},ref)=>{
  const node=useRef<HTMLButtonElement>(null);useImperativeHandle(ref,()=>node.current!);
  useEffect(()=>{const element=node.current;if(!element||!onGamepadDirection)return;
    element.addEventListener('das-test-direction',onGamepadDirection);
    return()=>element.removeEventListener('das-test-direction',onGamepadDirection);
  },[onGamepadDirection]);
  const tag=(window as any).__dasDialogTag==='div'?'div':'button';
  return createElement(tag,{ref:node,...(tag==='div'?{role:'button',tabIndex:0}:{}),...props},children);
});
export const ButtonItem=({label,description,children,onClick,disabled}:any)=><div className="native-item gamepaddialog_Field_test"><div className="gamepaddialog_FieldLabel_test"><strong>{label}</strong>{description&&<small>{description}</small>}</div><div className="gamepaddialog_FieldChildren_test"><button aria-label={label} disabled={disabled} onClick={onClick}>{children||label}</button></div></div>;
export const TextField=({label,value,onChange,description,bIsPassword,'aria-label':ariaLabel}:any)=><label className="native-field gamepaddialog_Field_test"><div className="gamepaddialog_FieldLabel_test"><span>{label}</span>{description&&<small>{description}</small>}</div><div className="gamepaddialog_FieldChildren_test"><input aria-label={ariaLabel} type={bIsPassword?'password':'text'} value={value} onChange={onChange}/></div></label>;
export const ToggleField=({label,checked,onChange,disabled}:any)=><label className="native-item gamepaddialog_Field_test"><span>{label}</span><input type="checkbox" disabled={disabled} checked={checked} onChange={e=>onChange(e.target.checked)}/></label>;
export const DropdownItem=({label,selectedOption,rgOptions,onChange,disabled}:any)=><label className="native-item gamepaddialog_Field_test"><span>{label}</span><select aria-label={label} value={selectedOption} disabled={disabled} onChange={e=>onChange({data:rgOptions.find((o:any)=>String(o.data)===e.target.value).data})}>{rgOptions.map((o:any)=><option key={o.data} value={o.data}>{o.label}</option>)}</select></label>;
export const SliderField=({label,value,onChange,...props}:any)=><label className="native-item gamepaddialog_Field_test"><span>{label}</span><input type="range" value={value} onChange={e=>onChange(Number(e.target.value))} {...props}/></label>;
export const Navigation={NavigateBack:()=>{(window as any).__dasBackCount=((window as any).__dasBackCount||0)+1;},NavigateToExternalWeb:(url:string)=>{
  const testWindow=window as typeof window & {__browserFallback?:string[]};
  (testWindow.__browserFallback??=[]).push(url);
}};
export const Tabs=({tabs,activeTab,onShowTab}:any)=>{
 const ref=useRef<HTMLDivElement>(null);useEffect(()=>{const node=ref.current;const handler=(e:any)=>{const delta=e.detail.button===5?-1:1;onShowTab(tabs[(tabs.findIndex((t:any)=>t.id===activeTab)+delta+tabs.length)%tabs.length].id);};node?.addEventListener('das-test-bumper',handler);return()=>node?.removeEventListener('das-test-bumper',handler);},[activeTab,onShowTab,tabs]);
 return <div ref={ref} className="native-tabs" style={{display:'flex',flexDirection:'column',height:'100%',minHeight:0}}><div role="tablist" style={{display:'flex',gap:12,padding:'10px 30px',flexShrink:0}}>{tabs.map((t:any)=><button key={t.id} role="tab" data-collection-focus={'tab-'+t.id} aria-selected={t.id===activeTab} onClick={()=>onShowTab(t.id)}>{t.title}</button>)}</div><div role="tabpanel" data-native-tab-scroll style={{flex:1,minHeight:0,overflowY:"auto",paddingInline:"2.8vw",boxSizing:"border-box"}}>{tabs.find((t:any)=>t.id===activeTab)?.content}</div></div>;
};
export const Router={Navigate:()=>{}};

// Optional class maps for comparing GCA’s real scoped compact stylesheet.
export const gamepadDialogClasses={Field:'gamepaddialog_Field_test'};
export const quickAccessControlsClasses={PanelSection:'quickaccesscontrols_PanelSection_test'};
export const gamepadSliderClasses={};

export const DialogBody=({children,className}:any)=><div className={className}>{children}</div>;
export const DialogControlsSection=({children}:any)=><section>{children}</section>;
export const DialogControlsSectionHeader=({children}:any)=><h2>{children}</h2>;
export const SteamSpinner=()=>null;
export const Field=({label,description,children,className,focusable,...props}:any)=><Focusable tabIndex={focusable?0:undefined} className={`native-item ${className||''}`} {...props}><div><strong>{label}</strong>{description&&<small>{description}</small>}</div><div>{children}</div></Focusable>;
export {ReorderableList} from '../../node_modules/@decky/ui/src/custom-components/ReorderableList';

export const useQuickAccessVisible=()=>(window as any).__dasQamVisible!==false;
export const Dropdown=({selectedOption,rgOptions,onChange,disabled,menuLabel}:any)=><select aria-label={menuLabel||"Presentation"} value={selectedOption} disabled={disabled} onChange={e=>onChange({data:rgOptions.find((o:any)=>String(o.data)===e.target.value).data})}>{rgOptions.map((o:any)=><option key={o.data} value={o.data}>{o.label}</option>)}</select>;

// Menu fixture exercises app choices/cancel only. Native menu focus stays a
// separate Steam runtime/physical gate, never a browser adapter claim.
let closeMenu: (()=>void)|undefined;
export const Menu=({label,children,onCancel}:any)=><div role="menu" aria-label={label} onKeyDown={e=>{if(e.key==='Escape'){closeMenu?.();onCancel?.();}}}>{children}</div>;
export const MenuItem=({children,onSelected,onClick,...props}:any)=><button role="menuitem" {...props} onClick={e=>{closeMenu?.();(onSelected||onClick)?.(e);}}>{children}</button>;
export const showContextMenu=(children:any,parent?:EventTarget)=>{
 closeMenu?.();const host=document.createElement('div');host.dataset.testMenu='';host.style.cssText='position:fixed;inset:80px 10%;z-index:9999;background:#23262e;padding:16px';document.body.append(host);const root=createRoot(host);
 const close=()=>{root.unmount();host.remove();closeMenu=undefined;(parent as HTMLElement)?.focus?.();};closeMenu=close;root.render(children);requestAnimationFrame(()=>host.querySelector<HTMLElement>('[role=menuitem]')?.focus());return {Hide:close,Show(){}};
};
