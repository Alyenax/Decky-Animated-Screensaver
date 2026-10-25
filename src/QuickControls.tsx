import type {ReactNode} from 'react';
import {ButtonItem,DialogButton,Field,PanelSection,PanelSectionRow} from '@decky/ui';
import {TbSettings} from 'react-icons/tb';
import {tr,useLanguage} from './i18n';

/** Product grouping around native Steam controls; no cross-plugin styling. */
export function QuickZone({zone,children}:{zone:'control'|'collection'|'matrix'|'updates';children:ReactNode}){
  return <section data-das-quick-zone={zone}><PanelSection>{children}</PanelSection></section>;
}
export function QuickStatus({children,tone='good'}:{children:ReactNode;tone?:'good'|'waiting'|'error'}){
  return <PanelSectionRow><Field focusable={false} label={<div data-das-quick-card={tone}>{children}</div>}/></PanelSectionRow>;
}
export function QuickAction({children,onClick,disabled=false}:{children:ReactNode;onClick:()=>void;disabled?:boolean}){
  return <PanelSectionRow><ButtonItem layout="below" disabled={disabled} onClick={onClick}>{children}</ButtonItem></PanelSectionRow>;
}
export function QuickHeader({title,settingsLabel,onOpenSettings,className=''}:{title:string;settingsLabel?:string;onOpenSettings:()=>void;className?:string}){
  useLanguage();
  return <div className={`das-quick-title ${className}`} style={{display:'flex',alignItems:'center',
    justifyContent:'space-between',gap:8,width:'100%',minWidth:0}}><style>{QUICK_CONTROL_CSS}</style><span>{title}</span>
    <DialogButton className="das-quick-gear" aria-label={settingsLabel??tr('Settings','Réglages')} onClick={onOpenSettings}
      style={{width:32,height:32,minWidth:0,minHeight:32,padding:0,flexShrink:0,display:'flex',alignItems:'center',justifyContent:'center'}}>
      <TbSettings size={19} aria-hidden="true" />
    </DialogButton>
  </div>;
}
/** Scope only our layout. Native DialogButton paints all interaction states. */
export const QUICK_CONTROL_CSS=`
.das-quick-title{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;min-width:0}
#das-compact-root{min-width:0}
#das-compact-root [data-das-quick-card]{font-size:14px;line-height:20px;overflow-wrap:anywhere}
#das-compact-root [data-das-quick-card] strong{display:block;font-weight:500}
#das-compact-root [data-das-quick-card] p,#das-compact-root .das-quick-meta{font-size:12px;line-height:16px;color:var(--gpSystemLighterGrey,#b8bcbf);margin:4px 0}
#das-compact-root [data-das-quick-card=error] p{color:#ffc7b5}
#das-compact-root .das-quick-meta>span{display:block}
`;
