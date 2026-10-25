import {useState} from 'react';
import {ButtonItem,DialogButton,PanelSectionRow} from '@decky/ui';
import {tr} from './i18n';
import {recoveryHelp,safeErrorCode,isGameRunningCode,type RecoveryAction} from './recovery';
import type {StudioProblem} from './types';

export function RecoveryCard({problem,code,operation='',disabled=false,onRecover}:{problem?:StudioProblem;code?:string;operation?:string;disabled?:boolean;onRecover:(action:RecoveryAction,problem?:StudioProblem)=>void}){
  const [details,setDetails]=useState(false),help=recoveryHelp(problem?.code||code||'unexpected_error',problem?.role,problem?.skipped?'skipped-image':operation);
  const userState=isGameRunningCode(problem?.code||code)||safeErrorCode(problem?.code||code)==='collection_order_changed';
  return <div className="box tone-amber" role="alert" data-recovery-card>
    {problem?.name&&<h3>{problem.name}</h3>}
    <p className="status">{help.title}</p><p>{help.body}</p>
    {problem?.retained_media&&<p className="muted">{problem.role==='animation'?tr('Previous prepared visual kept.','Visuel préparé précédent conservé.'):tr('Prepared TV visual kept.','Visuel TV préparé conservé.')}</p>}
    <PanelSectionRow><DialogButton className="das-recovery-primary" disabled={disabled} onClick={()=>onRecover(help.action,problem)}>{!problem&&['choose','retry'].includes(help.action)?tr('See affected games','Voir les jeux concernés'):help.label}</DialogButton></PanelSectionRow>
    {!userState&&<PanelSectionRow><ButtonItem label={tr('Technical details','Détails techniques')} onClick={()=>setDetails(!details)}>{details?tr('Hide','Masquer'):tr('Show','Afficher')}</ButtonItem></PanelSectionRow>}
    {!userState&&details&&<small>{tr('Diagnostic code','Code diagnostic')} : {safeErrorCode(problem?.code||code)}</small>}
  </div>;
}
