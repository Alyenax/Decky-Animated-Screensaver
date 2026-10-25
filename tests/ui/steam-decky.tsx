// Browser-only DOM adapters informed by inspected SteamUI components.
// Styles come from the installed client; no Valve stylesheet enters the package.
import {createElement,forwardRef,useEffect,useRef,useState} from 'react';
import {Focusable as BaseFocusable} from './decky';
export * from './decky';
const maps=(window as any).__steamNative.modules;
const c=(kind:string,key:string)=>maps[kind]?.[key]||'';
const cx=(...values:any[])=>values.filter(Boolean).join(' ');
export const gamepadDialogClasses=maps.dialog,gamepadSliderClasses=maps.slider,quickAccessControlsClasses=maps.panel,gamepadTabbedPageClasses=maps.tabs;
export const findClassModule=(predicate:any)=>Object.values(maps).find(predicate);
export const Focusable=forwardRef<any,any>(({onActivate,className='',...props},ref)=><BaseFocusable ref={ref} className={cx(className,'Panel','Focusable')} onClick={onActivate?()=>onActivate(new Event('activate')):props.onClick} {...props}/>);
export const DialogButton=forwardRef<any,any>(({children,className='',disabled,style,...props},ref)=><button ref={ref} disabled={disabled} style={{width:'100%',...style}} className={`DialogButton _DialogLayout Secondary ${c('dialog','Button')} ${className}`} {...props}>{children}</button>);
export const DialogBody=({children,className=''}:any)=><div className={`DialogBody ${className}`}>{children}</div>;
export const DialogControlsSection=forwardRef<any,any>(({children,className='',...props},ref)=><div ref={ref} className={`DialogControlsSection ${className}`} {...props}>{children}</div>);
export const DialogControlsSectionHeader=({children}:any)=><div className="DialogControlsSectionHeader">{children}</div>;
export const DialogHeader=({children}:any)=><div role="heading" className="DialogHeader">{children}</div>;
export const PanelSection=({children,title}:any)=><div className={c('panel','PanelSection')}>{title&&<div className={c('panel','PanelSectionTitle')}><div className={c('panel','Text')}>{title}</div></div>}{children}</div>;
export const PanelSectionRow=({children}:any)=><div className={c('panel','PanelSectionRow')}>{children}</div>;
// Mirrors the actual Field DOM in current sp.js, including the child shell in
// below layout. This remains a DOM adapter, never the navigation engine.
export const Field=forwardRef<any,any>(({label,description,children,disabled,childrenLayout,childrenContainerWidth='min',layout,bottomSeparator='standard',className='',focusable,padding='standard',verticalAlignment='center',inlineWrap='keep-inline',highlightOnFocus=true,spacingBetweenLabelAndChild='standard',...props},ref)=>{
 const below=(childrenLayout||layout||'inline')==='below';
 const childShell=<div className={c('dialog','FieldChildrenWithIcon')}><div className={c('dialog','FieldChildrenInner')}>{children}</div></div>;
 return <Focusable ref={ref} tabIndex={focusable?0:undefined} style={{'--indent-level':0} as any} className={cx('native-item','Panel','Focusable',c('dialog','Field'),padding==='standard'&&c('dialog','StandardPadding'),padding==='compact'&&c('dialog','CompactPadding'),verticalAlignment==='center'&&c('dialog','VerticalAlignCenter'),spacingBetweenLabelAndChild==='standard'&&c('dialog','ExtraPaddingOnChildrenBelow'),highlightOnFocus&&c('dialog','HighlightOnFocus'),c('dialog',(window as any).__classic?'Classic':'Background'),bottomSeparator==='standard'&&c('dialog','WithBottomSeparatorStandard'),bottomSeparator==='thick'&&c('dialog','WithBottomSeparatorThick'),children&&c('dialog',below?'WithChildrenBelow':'WithChildrenInline'),childrenContainerWidth==='fixed'&&c('dialog','ChildrenWidthFixed'),childrenContainerWidth==='max'&&c('dialog','ChildrenWidthGrow'),inlineWrap==='shift-children-below'&&c('dialog','InlineWrapShiftsChildrenBelow'),disabled&&c('dialog','Disabled'),className)} {...props}>
 <div className={c('dialog','FieldLeftColumn')}>{label&&<div className={c('dialog','FieldLabelRow')}><div className={c('dialog','FieldLabel')}>{label}</div></div>}{below&&children&&childShell}{description&&<div className={c('dialog','FieldDescription')}>{description}</div>}</div>
 {!below&&children&&<div className={c('dialog','FieldRightColumn')}>{childShell}</div>}
 </Focusable>;
});
export const ButtonItem=({label,description,children,onClick,disabled,layout='inline',...props}:any)=><Field {...props} label={label} description={description} disabled={disabled} childrenLayout={layout}><DialogButton disabled={disabled} onClick={onClick}>{children||label}</DialogButton></Field>;
export const TextField=({label,value,onChange,description,bIsPassword,disabled,'aria-label':ariaLabel}:any)=><div className="DialogInputLabelGroup _DialogLayout native-field"><label>{label&&<div className="DialogLabel _DialogLayout">{label}</div>}<div className="DialogInput_Wrapper"><input size={1} className={`DialogInput DialogTextInputBase ${c('dialog','BasicTextInput')}`} aria-label={ariaLabel||label} disabled={disabled} type={bIsPassword?'password':'text'} value={value??''} onChange={onChange}/></div>{description&&<div className="DialogLabelExplainer">{description}</div>}</label></div>;
export const ToggleField=({label,checked,onChange,disabled,description,bottomSeparator,layout,...props}:any)=><Field {...props} childrenLayout={layout} label={label} description={description} disabled={disabled} bottomSeparator={bottomSeparator}><div role="checkbox" aria-checked={checked} tabIndex={disabled?-1:0} onClick={()=>!disabled&&onChange(!checked)} className={[c('dialog','Toggle'),checked?c('dialog','On'):'',disabled?c('dialog','Disabled'):''].join(' ')}><div className={c('dialog','ToggleRail')}/><div className={c('dialog','ToggleSwitch')}/></div></Field>;
export const DropdownItem=({label,selectedOption,rgOptions,onChange,disabled,description,layout,...props}:any)=><Field {...props} childrenLayout={layout} label={label} description={description} disabled={disabled}><div className="DialogDropDown" style={{position:"relative"}}><DialogButton className={c('dialog','NoMinWidth')}><div className={c('dialog','DropDownControlButtonContents')}>{rgOptions.find((o:any)=>o.data===selectedOption)?.label}<span aria-hidden="true">▾</span></div></DialogButton><select aria-label={label} style={{position:'absolute',inset:0,opacity:0}} value={selectedOption} disabled={disabled} onChange={e=>onChange({data:rgOptions.find((o:any)=>String(o.data)===e.target.value).data})}>{rgOptions.map((o:any)=><option key={o.data} value={o.data}>{o.label}</option>)}</select></div></Field>;
export const SliderField=({label,description,value,min=0,max=100,step=1,onChange,disabled,valueSuffix='',showValue,layout='below',childrenContainerWidth='fixed',bottomSeparator}:any)=>{
  const s=maps.slider,percent=Math.min(1,Math.max(0,max>min?(value-min)/(max-min):0));
  const fieldLabel=showValue?<><div className={s.LabelText}>{label}</div><div className={s.DescriptionValue}><span className={s.DescriptionValueText}>{value}{valueSuffix}</span></div></>:label;
  return <Field label={fieldLabel} {...{description,layout,childrenContainerWidth,disabled,bottomSeparator}}><div className={cx('Focusable',s.SliderControlPanelGroup,'SliderControlPanelGroup')}><div className={cx('Focusable',s.SliderControlAndNotches,disabled&&s.Disabled)} role="slider" aria-label={label} tabIndex={disabled?-1:0} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} aria-disabled={disabled}
    style={{'--normalized-slider-value':percent,'--normalized-slider-origin':0,'--slider-extra-notch-padding':'0px'} as any} onKeyDown={event=>{if(!disabled&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();onChange(Math.min(max,Math.max(min,value+(event.key==='ArrowRight'?step:-step))));}}}>
    <div className={cx(s.SliderControl,'SliderControl')}><div className={cx(s.SliderTrack,'SliderTrack')}/><div className={cx(s.SliderHandleContainer,'SliderHandleContainer')}><div className={cx(s.SliderHandle,'SliderHandle')}/></div></div>
  </div></div></Field>;
};
export const Tabs=({tabs,activeTab,onShowTab}:any)=>{
 const [scrolled,setScrolled]=useState(false);const ref=useRef<HTMLDivElement>(null);useEffect(()=>{const node=ref.current;const handler=(e:any)=>{const delta=e.detail.button===5?-1:1;onShowTab(tabs[(tabs.findIndex((t:any)=>t.id===activeTab)+delta+tabs.length)%tabs.length].id);};node?.addEventListener('das-test-bumper',handler);return()=>node?.removeEventListener('das-test-bumper',handler);},[activeTab,onShowTab,tabs]);
 return <div ref={ref} className={`${c('tabs','GamepadTabbedPage')} native-tabs`}><div className={cx(c('tabs','TabHeaderRowWrapper'),scrolled&&c('tabs','ScrolledDown'))}><div className={c('tabs','TabRow')}><div className={c('tabs','TabRowTabs')} role="tablist"><div className={c('tabs','TabsRowScroll')}><div className={c('tabs','FixCenterAlignScroll')}>{tabs.map((t:any)=><div role="tab" tabIndex={0} data-collection-focus={'tab-'+t.id} aria-selected={t.id===activeTab} className={`${c('tabs','Tab')} ${t.id===activeTab?c('tabs','Selected'):''}`} onClick={()=>onShowTab(t.id)} key={t.id}><span className={c('tabs','TabTitle')}>{t.title}</span></div>)}</div></div></div></div></div><div className={c('tabs','TabContents')}><div className={c('tabs','TabContentsScroll')} role="tabpanel" onScroll={e=>setScrolled(e.currentTarget.scrollTop>0)} style={{overflowY:'auto'}}>{tabs.find((t:any)=>t.id===activeTab)?.content}</div></div></div>;
};
export const SidebarNavigation=({title,pages,page,onPageRequested,fnSetNavigateToPage}:any)=>{
 const selected=pages.find((p:any)=>p.route===page)||pages[0];useEffect(()=>{fnSetNavigateToPage?.(onPageRequested);},[fnSetNavigateToPage,onPageRequested]);
 return <div className={c('sidebar','PagedSettingsDialog')}><div className={c('sidebar','PagedSettingsDialog_PageListColumn')}><div className={c('sidebar','PagedSettingsDialog_Title')}>{title}</div><div className={c('sidebar','PagedSettingsDialog_PageList')}>{pages.map((p:any)=><div className={`${c('sidebar','PagedSettingsDialog_PageListItem')} ${p===selected?c('sidebar','Active'):''}`} role="button" tabIndex={0} onClick={()=>onPageRequested(p.route)} key={p.route}><div className={c('sidebar','ScaledChildren')}><span className={c('sidebar','PageListItem_Title')}>{p.title}</span></div></div>)}</div></div><div className={`DialogContentTransition ${c('sidebar','PagedSettingDialog_ContentColumn')}`}><div className={`DialogContent ${c('sidebar','PagedSettingsDialog_PageContent')} ${selected.padding==='none'?c('sidebar','NoPadding'):''}`}>{selected.content}</div></div></div>;
};
export const staticClasses={Title:maps.panel.Title||''};
export const showModal=()=>({Close(){}});
export const ConfirmModal=({children}:any)=><>{children}</>;
export const useQuickAccessVisible=()=>true;
export const getFocusNavController=()=>({});
export const useParams=()=>({});

export const Dropdown=({selectedOption,rgOptions,onChange,disabled,menuLabel}:any)=><div className="DialogDropDown" style={{position:'relative'}}><DialogButton disabled={disabled} className={c('dialog','NoMinWidth')}><div className={c('dialog','DropDownControlButtonContents')}>{rgOptions.find((o:any)=>o.data===selectedOption)?.label}<span aria-hidden="true">▾</span></div></DialogButton><select aria-label={menuLabel||"Presentation"} style={{position:'absolute',inset:0,opacity:0}} value={selectedOption} disabled={disabled} onChange={e=>onChange({data:rgOptions.find((o:any)=>String(o.data)===e.target.value).data})}>{rgOptions.map((o:any)=><option key={o.data} value={o.data}>{o.label}</option>)}</select></div>;

export const ColorPicker=()=>null;
export const findModuleExport=()=>null;
export const DialogInput=TextField;
