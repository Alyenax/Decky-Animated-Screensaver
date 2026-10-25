import {useState,useEffect,useRef} from 'react';
import {DialogButton} from '@decky/ui';
import {DropdownItem,ToggleField} from './settings_controls';
import {jsauxVisible,type StudioClient,type StudioState} from './types';
import {tr} from './i18n';
export function AssistancePanel({state:s,run,saving}:{state:StudioState;run:StudioClient;saving:boolean}){
 const [confirm,setConfirm]=useState(''),[message,setMessage]=useState(''),[report,setReport]=useState(''),[advanced,setAdvanced]=useState(false),[showReport,setShowReport]=useState(false);
 useEffect(()=>{diagnosticTicket.current++;setReport('');setShowReport(false);setConfirm('');setMessage('');},[s.jsaux?.detected,s.jsaux?.compatible]);
 const diagnosticTicket=useRef(0);useEffect(()=>()=>{diagnosticTicket.current++;},[]);
 const action=(name:string,label:string,payload:Record<string,unknown>={})=><DialogButton className="collection-action" disabled={saving||s.workspace?.task.worker_active} onClick={()=>{if(confirm!==name){setConfirm(name);return;}setConfirm('');void run(name,{...payload,confirm:true}).then(v=>{if(v)setMessage(tr('Done','Terminé'));});}}>{confirm===name?tr('Confirm: ','Confirmer : ')+label:label}</DialogButton>;
 return <div className="collection-settings-form"><h2>{tr('Storage and assistance','Stockage et assistance')}</h2>{message&&<p role="status">{message}</p>}
 {jsauxVisible(s.jsaux)&&<DialogButton className="collection-action" disabled={saving} onClick={()=>void run('jsaux_refresh',{force:true})}>{tr('Reconnect GabeCubeAura','Reconnecter GabeCubeAura')}</DialogButton>}
 <DialogButton className="collection-action" disabled={saving} onClick={()=>{const ticket=++diagnosticTicket.current;void run<{report:unknown;path:string}>('diagnostic').then(v=>{if(v&&ticket===diagnosticTicket.current){setReport(JSON.stringify(v.report,null,2));setMessage(tr('Full diagnostic saved locally: ','Diagnostic complet enregistré localement : ')+v.path);}});}}>{tr('Save local diagnostic','Enregistrer un diagnostic local')}</DialogButton>
 {report&&<><DialogButton className="collection-action" onClick={()=>setShowReport(!showReport)}>{tr('Diagnostic details','Détails du diagnostic')}</DialogButton>{showReport&&<pre>{report}</pre>}</>}
 <DialogButton className="collection-action" aria-expanded={advanced} onClick={()=>{setAdvanced(!advanced);setConfirm('');}}>{tr('Storage and imports','Stockage et imports')}</DialogButton>
 {advanced&&<div>
 <DropdownItem label={tr('Storage budget','Budget de stockage')} selectedOption={s.options.storage_mib} rgOptions={[512,1024,2048,4096,8192,10240,12288,15360,0].map(data=>({data,label:!data?tr('Unlimited','Illimité'):data>=1024?`${data/1024} ${tr('GB','Go')}`:`${data} ${tr('MB','Mo')}`}))} onChange={o=>void run('configure',{patch:{storage_mib:o.data}})}/>
 <ToggleField label={tr('Smooth prepared animations','Fluidifier les animations préparées')} checked={s.options.smoothing} onChange={smoothing=>void run('configure',{patch:{smoothing}})}/>
 <DropdownItem label={tr('Smoothing quality','Qualité de la fluidification')} selectedOption={s.options.smoothing_mode} rgOptions={[{data:'fast',label:tr('Fast','Rapide')},{data:'quality',label:tr('High quality','Haute qualité')},{data:'blend',label:tr('Frame blend','Mélange d’images')}]} onChange={o=>void run('configure',{patch:{smoothing_mode:o.data}})}/>
 <DropdownItem label={tr('Smoothing frame rate','Cadence de fluidification')} selectedOption={s.options.smoothing_fps} rgOptions={[24,30].map(data=>({data,label:data+' FPS'}))} onChange={o=>void run('configure',{patch:{smoothing_fps:o.data}})}/>
 <DropdownItem label={tr('Maximum size per visual','Taille maximale par visuel')} selectedOption={s.options.max_video_mib} rgOptions={[64,128,256,512,0].map(data=>({data,label:data?`${data} ${tr('MB','Mo')}`:tr('Unlimited','Illimité')}))} onChange={o=>void run('configure',{patch:{max_video_mib:o.data}})}/>
 <ToggleField label={tr('Use still images without animations','Utiliser une image fixe sans animation')} checked={s.options.static_fallback} onChange={static_fallback=>void run('configure',{patch:{static_fallback}})}/>
 {(['artwork_credit','cover_credit','logo_credit'] as const).map((field,index)=><ToggleField key={field} label={[tr('Artwork credits','Crédit du fond'),tr('Cover credits','Crédit de la jaquette'),tr('Logo credits','Crédit du logo')][index]} checked={s.options[field]} onChange={value=>void run('configure',{patch:{[field]:value}})}/>)}
 <DialogButton className="collection-action" onClick={()=>void run('verify')}>{tr('Verify library','Vérifier la bibliothèque')}</DialogButton>
 <DialogButton className="collection-action" onClick={()=>void run('inspect_installation')}>{tr('Verify Steam files','Vérifier les fichiers Steam')}</DialogButton>
 {action('unused',tr('Clear unused cache','Nettoyer le cache inutilisé'))}{action('uninstall',tr('Remove screensaver files','Retirer les fichiers de l’écran de veille'))}{action('purge',tr('Delete prepared media and export','Supprimer les médias préparés et l’export'))}
 {action('save_key',tr('Forget SteamGridDB key','Oublier la clé SteamGridDB'),{key:''})}
 {action('import_gca',tr('Import previous GCA library','Importer l’ancienne bibliothèque GCA'))}
 </div>}</div>;
}
