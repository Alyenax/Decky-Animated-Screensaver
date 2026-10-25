import {SettingsRow as PanelSectionRow,SettingsSection as PanelSection} from './settings_ui';
import {useEffect,useRef,useState} from 'react';
import {getGamepadNavigationTrees} from '@decky/ui';
import {ButtonItem,DropdownItem,ToggleField} from './settings_controls';
import {errorText,tr} from './i18n';
import type {StudioClient,UpdateState} from './types';
import {focusUpdatePrimary} from './focus';

export function UpdatesPanel({state:s,run,saving,focusRequest=0}:{state:UpdateState;run:StudioClient;saving:boolean;focusRequest?:number}){
  const root=useRef<HTMLDivElement>(null),focused=useRef(0);
  const [confirm,setConfirm]=useState(false);
  const [expanded,setExpanded]=useState(false);
  const busy=s.repository_state==='checking'||['checking','downloading','installing'].includes(s.phase);
  const displayError=s.error || s.repository_error;
  useEffect(()=>{setConfirm(false);},[s.phase,s.confirmation,s.channel]);
  useEffect(()=>{
    if(!focusRequest||focused.current===focusRequest)return;
    const frame=requestAnimationFrame(()=>{
      try{if(root.current&&focusUpdatePrimary(root.current,getGamepadNavigationTrees()||[]))focused.current=focusRequest;}catch{}
    });
    return()=>cancelAnimationFrame(frame);
  },[focusRequest,s.phase,s.available,saving,s.repository_state]);
  const label=({idle:tr('Ready to check','Prêt à vérifier'),checking:tr('Checking releases…','Recherche de versions…'),
    available:tr('Update available','Mise à jour disponible'),current:s.available_version?tr('Up to date','À jour'):tr('No release in this channel','Aucune version dans ce canal'),
    downloading:tr('Downloading and verifying…','Téléchargement et vérification…'),ready:tr('Update verified','Mise à jour vérifiée'),
    installing:tr('Restarting Decky…','Redémarrage de Decky…'),updated:tr('Update installed','Mise à jour installée'),rolled_back:tr('Previous version restored','Version précédente restaurée'),error:tr('Update needs attention','Mise à jour à vérifier')} as Record<string,string>)[s.phase]||s.phase;
  const specificPrimary=s.phase==='ready'||s.phase==='downloading'||s.available&&!['installing','checking'].includes(s.phase);
  return <div ref={root} data-updates-panel><PanelSection title={tr('Updates','Mises à jour')}>
    <PanelSectionRow><div className={'box tone-'+(displayError?'amber':s.available?'green':'cyan')} data-updates>
      <p className="status">{label}</p><small>{tr('Installed','Installée')} · {s.installed_version}{s.available_version?` → ${s.available_version}`:''}</small>
      {displayError&&<p className="error" role="alert">{errorText(displayError)}</p>}
      {s.phase==='downloading'&&<progress max={100} value={s.percent}/>}
    </div></PanelSectionRow>
    {s.available&&!['ready','downloading','installing','checking'].includes(s.phase)&&<div data-update-primary="download"><PanelSectionRow><ButtonItem label={tr('Download update','Télécharger la mise à jour')} disabled={saving||busy} onClick={()=>void run('update_prepare')}>{tr('Download','Télécharger')}</ButtonItem></PanelSectionRow></div>}
    {s.phase==='downloading'&&<div data-update-primary="cancel"><PanelSectionRow><ButtonItem label={tr('Cancel download','Annuler le téléchargement')} onClick={()=>void run('update_cancel')}>{tr('Cancel','Annuler')}</ButtonItem></PanelSectionRow></div>}
    {s.phase==='ready'&&<div data-update-primary="install"><PanelSectionRow><ButtonItem label={confirm?tr('Confirm update · Decky will restart','Confirmer la mise à jour · Decky redémarrera'):tr('Install update','Installer la mise à jour')} description={tr('Close your game. Your library and SteamGridDB key are kept.','Fermez le jeu. Bibliothèque et clé SteamGridDB conservées.')} disabled={saving} onClick={()=>{
      if(!confirm){setConfirm(true);return;}void run('update_install',{confirm:true,confirmation:s.confirmation});
    }}>{confirm?tr('Confirm and restart','Confirmer et redémarrer'):tr('Continue','Continuer')}</ButtonItem></PanelSectionRow></div>}
    <div data-update-primary={specificPrimary?undefined:'check'}><PanelSectionRow><ButtonItem label={tr('Check for updates now','Rechercher une mise à jour')}
      disabled={saving||busy||s.phase==='ready'} onClick={()=>void run('update_check')}>{tr('Check','Vérifier')}</ButtonItem></PanelSectionRow></div>
    <PanelSectionRow><ButtonItem label={expanded?tr('Hide update settings','Masquer les réglages de mise à jour'):tr('Update settings','Réglages de mise à jour')} onClick={()=>setExpanded(!expanded)}>{expanded?tr('Hide','Masquer'):tr('Open','Ouvrir')}</ButtonItem></PanelSectionRow>
    {expanded&&<>
    <PanelSectionRow><DropdownItem label={tr('Update channel','Canal de mise à jour')} selectedOption={s.channel} disabled={saving||busy||s.phase==='ready'} rgOptions={[
      {data:'stable',label:tr('Stable','Stable')},{data:'beta',label:tr('Beta','Bêta')},
    ]} onChange={o=>void run('update_configure',{patch:{channel:o.data}})}/></PanelSectionRow>
    <PanelSectionRow><ToggleField label={tr('Check for updates automatically','Rechercher automatiquement les mises à jour')} description={tr('Every 24 hours. Download and installation are manual.','Toutes les 24 heures. Téléchargement et installation manuels.')} checked={s.auto_check} disabled={saving||busy} onChange={auto_check=>void run('update_configure',{patch:{auto_check}})}/></PanelSectionRow>
    </>}
  </PanelSection></div>;
}
