import {SettingsRow as PanelSectionRow,SettingsSection as PanelSection} from './settings_ui';
import {useRef,useState,useEffect} from 'react';
import {Field,DialogButton,Focusable,TextField,Router} from '@decky/ui';
import {ButtonItem,DropdownItem,SliderField,ToggleField} from './settings_controls';
import type {StudioState,StudioClient,StudioOptions} from './types';
import {jsauxVisible,jsauxBusy,jsauxPreparationBusy,jsauxPreviewURL} from './types';
import {busy,shouldPoll} from './model';
import {tr,language,setLanguage,stageText} from './i18n';
import {openSteamGridDBPage} from './steamgriddb_browser';
import {RecoveryCard} from './RecoveryCard';
import {FaceplatePreparationStatus} from './FaceplatePreparationStatus';
import {faceplateSummary,faceplateEffectiveMode} from './faceplateUX';
type ConnectionResult='idle'|'checking'|'present'|'unavailable';
const connectionResults=new WeakMap<StudioClient,{context:string;result:ConnectionResult}>();
const connectionContext=(s:StudioState)=>JSON.stringify([s.jsaux?.connection_id,s.jsaux?.detected,s.jsaux?.compatible]);
function jsauxPhase(state:StudioState['jsaux']):string {
  if(!state)return tr('Compatible GabeCubeAura required','GabeCubeAura compatible requis');
  const reasons:Record<string,string>={
    AUTH_DENIED:tr('GabeCubeAura refused the connection. Check that it is enabled and up to date.','Connexion refusée par GabeCubeAura. Vérifiez qu’il est actif et à jour.'),
    VERSION_UNSUPPORTED:tr('Update both plugins','Mettez à jour les deux plugins'),
    FACEPLATE_DISABLED:tr('Disabled in GabeCubeAura','Désactivée dans GabeCubeAura'),
    DISPLAY_OFF:tr('Display switched off','Affichage éteint'),
    SUSPENDED:tr('System suspended','Système en veille'),
    PRIORITY_ACTIVE:tr('Another display has priority','Un autre affichage est prioritaire'),
    DEVICE_ABSENT:tr("Faceplate JSAUX disconnected","Faceplate JSAUX déconnectée"),
    DEVICE_BUSY:tr("Faceplate JSAUX temporarily busy","Faceplate JSAUX temporairement occupée"),
    OWNERSHIP_UNAVAILABLE:tr('Hardware ownership unavailable','Contrôle matériel indisponible'),
    FLASH_DEFERRED:tr('Deferred by memory protection','Différé par la protection mémoire'),
    USB_UNCONFIRMED:tr('Transfer not confirmed','Transfert non confirmé'),
    JSAUX_SYNC_WINDOW:tr('Prepare lots with independent playback','Préparer les lots en lecture indépendante'),
    USB_FAILED:tr('Transfer failed; TV remains available','Échec du transfert ; TV disponible'),
    ALIGNMENT_EXPIRED:tr('TV only for this session','TV seule pour cette session'),
    CLOCK_UNAVAILABLE:tr('Coordinated start unavailable; TV only','Démarrage coordonné indisponible ; TV seule'),
    STEAM_STATE_STALE:tr('Waiting for current Steam state','En attente de l’état Steam actuel'),
    STEAM_INACTIVE:tr('Steam screensaver inactive','Écran de veille Steam inactif'),
    CONTENT_MISSING:tr('Update the collection to prepare missing images','Mettez à jour la collection pour préparer les images manquantes'),
    CONTENT_INVALID:tr("Update the collection to rebuild Faceplate JSAUX images.","Mettez à jour la collection pour refaire les visuels Faceplate JSAUX."),
    PREPARATION_POWER_REQUIRED:tr("Update Faceplate JSAUX images; cached files are kept.","Visuels Faceplate JSAUX à mettre à jour ; cache conservé."),
    JSAUX_RELAY_UNAVAILABLE:tr('Steam connection unavailable. Reconnect or update the collection.','Connexion Steam indisponible. Reconnectez-vous ou mettez à jour la collection.'),
    PREPARATION_FAILED:tr("Faceplate JSAUX preparation failed","Échec de la préparation Faceplate JSAUX"),
    VALIDATION_LIMIT:tr('Prepared GIF validation timed out','La validation du GIF préparé a expiré'),
    BROKER_UNAVAILABLE:tr('GabeCubeAura unavailable. Check that it is enabled and up to date.','GabeCubeAura indisponible. Vérifiez qu’il est actif et à jour.'),
    CONTENT_TOO_LARGE:tr("Prepare Faceplate JSAUX lots. TV files are kept.","Préparez les lots Faceplate JSAUX. Fichiers TV conservés."),
    RATE_LIMITED:tr('Checking collection. Retry shortly.','Vérification en cours. Réessayez dans un instant.'),
    CONTENT_PROFILE_UNSUPPORTED:tr('Incompatible format or orientation. Use normal orientation in GabeCubeAura.','Format ou orientation incompatible. Choisissez l’orientation normale dans GabeCubeAura.'),
    ACTIVATION_CLOSED:tr('TV only until the next Steam screensaver activation.','TV seule jusqu’au prochain lancement de l’écran de veille Steam.'),
  };
  if(state.reason)return reasons[state.reason] || tr('Temporarily unavailable; TV remains available','Temporairement indisponible ; TV disponible');
  if(!state.compatible)return tr('Compatible GabeCubeAura required','GabeCubeAura compatible requis');
  const phases:Record<string,string>={
    queued:tr('Preparation queued','Préparation en attente'),preparing:tr('Preparing images','Préparation des visuels'),
    registering:tr('Registering collection','Enregistrement de la collection'),validating:tr('Checking collection','Vérification de la collection'),
    acquiring:tr('Requesting display','Demande d’affichage'),waiting:tr('Waiting for Steam screensaver','En attente de l’écran de veille Steam'),
    transferring:tr('Transferring via GabeCubeAura','Transfert via GabeCubeAura'),active:tr('Delegated to GabeCubeAura','Délégué à GabeCubeAura'),
    restoring:tr('Returning to the current display','Retour à l’affichage actuel'),releasing:tr('Releasing display','Libération de l’affichage'),
  };
  if(phases[state.phase])return phases[state.phase];
  if(!state.detected)return tr("Faceplate JSAUX disconnected","Faceplate JSAUX déconnectée");
  if(!state.enabled)return tr("Faceplate JSAUX output off","Sortie Faceplate JSAUX désactivée");
  if(faceplateEffectiveMode(state)==='sync'&&state.prepared?.ready&&!state.prepared.sync_admissible)return tr('Collection too slow for synchronised playback','Collection trop lente pour la lecture synchronisée');
  if(!state.prepared?.ready){
    if(state.prepared?.reason==='PREPARATION_STALE')return tr('Update the collection to apply changes.','Mettez à jour la collection pour appliquer les modifications.');
    if(state.prepared?.reason==='REGISTRATION_MISSING')return tr("Update the collection to apply Faceplate JSAUX images.","Mettez à jour la collection pour appliquer les visuels Faceplate JSAUX.");
    if(state.prepared?.reason==='PREPARED_FILE_MISSING')return tr("Prepare Faceplate JSAUX images.","Préparez les visuels Faceplate JSAUX.");
  }
  return state.prepared?.ready?tr("Faceplate JSAUX images prepared","Images Faceplate JSAUX préparées"):tr('Images to prepare with the collection','Images à préparer avec la collection');
}

export function SettingsPanels({state:s,run,saving,section,onCollection,inCollection=false}:{state:StudioState;run:StudioClient;saving:boolean;section:'setup'|'playback'|'jsaux';onCollection:()=>void;inCollection?:boolean}){
const [key,setKey]=useState(''),[notice,setNotice]=useState(''),[jsauxPreview,setJsauxPreview]=useState('');
const [profile,setProfile]=useState(''),[steamKey,setSteamKey]=useState('');
const [keyCheck,setKeyCheck]=useState<'idle'|'checking'|'verified'|'failed'>('idle');
const keyCheckPending=useRef(false),keyCheckTicket=useRef(0);
const [technical,setTechnical]=useState(false);
const [connectionCheck,setConnectionCheck]=useState<ConnectionResult>(()=>{const saved=connectionResults.get(run);return saved?.context===connectionContext(s)?saved.result:'idle';});
const connectionTicket=useRef(0);
const [aligning,setAligning]=useState(false),[alignmentDraft,setAlignmentDraft]=useState(0);
const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
const jsaux=s.jsaux,hasJsaux=jsauxVisible(jsaux),working=busy(s)||jsauxBusy(jsaux),disabled=saving||working;
const panelSummary=faceplateSummary(jsaux,Boolean(s.workspace?.pending_count||s.workspace?.draft_count));
const synced=Boolean(jsaux?.detected&&jsaux.compatible&&jsaux.enabled&&(jsaux.prepared?.ready?faceplateEffectiveMode(jsaux):jsaux.mode)==='sync');
const connectionBlocked=Boolean(jsaux?.reason&&['AUTH_DENIED','BROKER_UNAVAILABLE','VERSION_UNSUPPORTED','PROTOCOL_INVALID','STALE_BOOT'].includes(jsaux.reason));
useEffect(()=>{connectionTicket.current++;const saved=connectionResults.get(run);setConnectionCheck(saved?.context===connectionContext(s)?saved.result:'idle');if(!hasJsaux){setTechnical(false);setJsauxPreview('');setAligning(false);}},[hasJsaux,jsaux?.connection_id,run]);
useEffect(()=>{keyCheckTicket.current++;keyCheckPending.current=false;setKeyCheck('idle');},[s.key_configured,run]);
const testSavedKey=async()=>{
 if(disabled||keyCheckPending.current)return;
 const ticket=++keyCheckTicket.current;keyCheckPending.current=true;setKeyCheck('checking');
 try{
  const result=await run<StudioState>('validate_key');
  if(alive.current&&ticket===keyCheckTicket.current)setKeyCheck(result?.key_configured&&result.connection==='verified'?'verified':'failed');
 }catch{if(alive.current&&ticket===keyCheckTicket.current)setKeyCheck('failed');}
 finally{if(ticket===keyCheckTicket.current)keyCheckPending.current=false;}
};
const retryConnection=async()=>{
 if(connectionCheck==='checking')return;
 const ticket=++connectionTicket.current;setConnectionCheck('checking');
 const result=await run<StudioState>('jsaux_refresh',{force:true});
 if(!alive.current||ticket!==connectionTicket.current)return;
 const outcome=result?.jsaux?.compatible?'present':'unavailable';
 if(result)connectionResults.set(run,{context:connectionContext(result),result:outcome});
 setConnectionCheck(outcome);
};
const recover=(kind:string)=>{if(kind==='library')onCollection();else if(kind==='connection')retryConnection();else if(kind==='tools')void run('tools',{action:'install'});};
  const change=(patch:Partial<StudioOptions>)=>void run('configure',{patch});
  const changeJsaux=(patch:Record<string,unknown>)=>{setJsauxPreview('');void run('jsaux_configure',{patch});};
  const openKeyPage=(page:'login'|'keys')=>{
    try{setNotice(openSteamGridDBPage(page)==='steam'
      ?tr('If copying is blocked in Steam, use Desktop Mode.','Si la copie est bloquée dans Steam, utilisez le mode Bureau.'):'');}
    catch{setNotice(tr('Could not open the browser. Open steamgriddb.com/profile/preferences/api in Desktop Mode.','Impossible d’ouvrir le navigateur. Ouvrez steamgriddb.com/profile/preferences/api en mode Bureau.'));}
  };
  const dropdown=(label:string,key: keyof StudioOptions,values:[string|number,string][])=>s&&<DropdownItem label={label} selectedOption={s.options[key] as string|number} disabled={disabled} rgOptions={values.map(([data,label])=>({data,label}))} onChange={o=>change({[key]:o.data})}/>;
  const toggle=(label:string,key:keyof StudioOptions)=>s&&<ToggleField label={label} checked={Boolean(s.options[key])} disabled={disabled} onChange={v=>change({[key]:v})}/>;

return <div className="collection-settings-form">{notice&&<p role="status">{notice}</p>}
      {(!section||section==='setup')&&<PanelSection title={tr('Setup','Configuration')}>
        <PanelSectionRow><div className={'box tone-'+(s.key_configured?'green':'amber')}><h2>1 · SteamGridDB</h2><p className="status">{s.connection==='verified'?tr('Connection verified','Connexion vérifiée'):s.key_configured?tr('API key detected','Clé API détectée'):tr('API key required','Clé API requise')}</p></div></PanelSectionRow>
        <PanelSectionRow><ButtonItem label={tr('Log in to SteamGridDB','Se connecter à SteamGridDB')} onClick={()=>openKeyPage('login')}>{tr('Log in with Steam','Se connecter avec Steam')}</ButtonItem></PanelSectionRow>
        <PanelSectionRow><ButtonItem label={tr('Open SteamGridDB API keys','Ouvrir les clés API SteamGridDB')} onClick={()=>openKeyPage('keys')}>{tr('Get my API key','Récupérer ma clé API')}</ButtonItem></PanelSectionRow>
        <PanelSectionRow><div data-recovery-target="api"><TextField label={tr('Paste API key','Coller la clé API')} value={key} bIsPassword onChange={e=>{keyCheckTicket.current++;keyCheckPending.current=false;setKeyCheck('idle');setKey(e.target.value);}} description={tr('Stored only on this device.','Enregistrée uniquement sur cet appareil.')}/></div></PanelSectionRow>
        <PanelSectionRow><ButtonItem label={tr('Save and verify key','Enregistrer et vérifier la clé')} disabled={disabled||!key.trim()} onClick={()=>void run('save_key',{key}).then(result=>{if(result){setKey('');void run('validate_key');}})}>{tr('Verify','Vérifier')}</ButtonItem></PanelSectionRow>
        {s.key_configured&&<PanelSectionRow><ButtonItem label={tr('Test saved key','Tester la clé enregistrée')} disabled={disabled||keyCheck==='checking'} onClick={()=>void testSavedKey()}>{keyCheck==='checking'?tr('Testing…','Test en cours…'):tr('Test','Tester')}</ButtonItem></PanelSectionRow>}
        {keyCheck!=='idle'&&<PanelSectionRow><small data-saved-key-result={keyCheck} role={keyCheck==='failed'?'alert':'status'} aria-live="polite" style={{color:keyCheck==='verified'?'#8bd49c':keyCheck==='failed'?'#ffb4a8':undefined}}>{keyCheck==='verified'?tr('✓ Saved key verified.','✓ Clé enregistrée vérifiée.'):keyCheck==='failed'?tr('Key verification failed. Retry or save another key.','La vérification a échoué. Réessayez ou enregistrez une autre clé.'):tr('Testing saved key…','Test de la clé enregistrée…')}</small></PanelSectionRow>}
        <PanelSectionRow><div className={'box tone-'+(s.media_tools.available?'green':'amber')}><h2>2 · {tr('Video tools','Outils vidéo')}</h2><p className="status">{s.media_tools.available?tr('Ready','Prêts'):stageText(s.media_tools.state)}</p>{shouldPoll(s)&&<progress max={100} value={s.media_tools.percent||0}/>}</div></PanelSectionRow>
        <PanelSectionRow><div data-video-tools-details><p>{tr('Downloads ','Télécharge ')}{s.media_tools.version||'FFmpeg'}, ffprobe {tr('and their shared libraries for Linux x86_64 (about 64 MB), to analyse and prepare your images and animations.','et leurs bibliothèques partagées pour Linux x86_64 (environ 64 Mo), pour analyser et préparer vos images et animations.')}</p><p>{tr('Source: BtbN/FFmpeg-Builds on GitHub.','Source : BtbN/FFmpeg-Builds sur GitHub.')}</p><p>{tr('Installation folder:','Dossier d’installation :')}<br/><code style={{overflowWrap:'anywhere'}}>{s.media_tools.installation_path||tr('Animated Screensaver’s Decky settings folder / cinema-tools-v1','Dossier des paramètres Decky d’Animated Screensaver / cinema-tools-v1')}</code></p></div></PanelSectionRow>
        <PanelSectionRow><div data-recovery-target="tools"><ButtonItem label={s.media_tools.installed?tr('Verify downloaded tools','Vérifier les outils téléchargés'):tr('Install video tools · about 64 MB','Installer les outils vidéo · environ 64 Mo')} disabled={disabled||['downloading','extracting','verifying'].includes(s.media_tools.state)} onClick={()=>void run('tools',{action:s.media_tools.installed?'verify':'install'})}>{s.media_tools.installed?tr('Verify','Vérifier'):tr('Download','Télécharger')}</ButtonItem></div></PanelSectionRow>
        {s.media_tools.error&&<RecoveryCard code={s.media_tools.error} operation="tools" disabled={saving} onRecover={kind=>void recover(kind)}/>}
        {['downloading','extracting','verifying'].includes(s.media_tools.state)&&<PanelSectionRow><ButtonItem label={tr('Cancel download','Annuler le téléchargement')} onClick={()=>void run('tools',{action:'cancel'})}>{tr('Cancel','Annuler')}</ButtonItem></PanelSectionRow>}
        <PanelSectionRow><ToggleField label={tr('Allow still images','Autoriser les images fixes')} checked={s.options.static_fallback} disabled={disabled} description={tr('Use a still image when no animation exists.','Utilise une image fixe lorsqu’aucune animation n’existe.')} onChange={v=>change({static_fallback:v})}/></PanelSectionRow>
        <PanelSectionRow><h2>3 · {tr('Steam library import','Import de la bibliothèque Steam')} · <strong style={{color:'#ffd27a'}}>{tr('Optional','Facultatif')}</strong></h2>
          <p>{tr('Import games you own, including games not installed here.','Importe vos jeux possédés, y compris ceux qui ne sont pas installés ici.')} <strong><u>{tr('Skip this if you only use installed games or search for games.','Ignorez cette étape si vous utilisez uniquement les jeux installés ou la recherche de jeux.')}</u></strong> {tr('Your Steam Game details must be public for this import.','Vos détails de jeux Steam doivent être publics pour cet import.')}</p>
          <p>{tr('These fields stay on this device until you select Import. The request then goes directly to Steam over HTTPS. The Web API key is never saved, exported, or sent to SteamGridDB or GitHub; it is cleared after the attempt. Imported games are saved locally.','Ces champs restent sur cet appareil jusqu’à la sélection d’Importer. La requête est alors envoyée directement à Steam en HTTPS. La clé Web API n’est jamais enregistrée, exportée ou envoyée à SteamGridDB ou GitHub ; elle est effacée après la tentative. Les jeux importés sont enregistrés localement.')}</p></PanelSectionRow>
        <PanelSectionRow><TextField label={tr('Steam profile · optional','Profil Steam · facultatif')} description={tr('SteamID64 or https://steamcommunity.com/id/your-profile','SteamID64 ou https://steamcommunity.com/id/votre-profil')} value={profile} onChange={e=>setProfile(e.target.value)}/></PanelSectionRow>
        <PanelSectionRow><TextField label={tr('Steam Web API key · for import only','Clé Web API Steam · pour l’import uniquement')} bIsPassword value={steamKey} onChange={e=>setSteamKey(e.target.value)}/></PanelSectionRow>
        <PanelSectionRow><ButtonItem label={tr('Import owned games','Importer les jeux possédés')} disabled={disabled||!steamKey.trim()||!profile.trim()} onClick={()=>{const secret=steamKey;setSteamKey('');void run('import_owned',{key:secret,profile});}}>{tr('Import','Importer')}</ButtonItem></PanelSectionRow>
      </PanelSection>}
      {(!section||section==='playback')&&<PanelSection title={tr('Playback','Lecture')}>
        <PanelSectionRow>{dropdown(tr('Time per game','Durée par jeu'),'scene_seconds',[[8,'8 s'],[12,'12 s'],[24,'24 s'],[30,'30 s'],[60,'60 s'],[120,'120 s'],[180,'180 s']])}</PanelSectionRow>
        <PanelSectionRow><ToggleField label={tr('Shuffle games','Ordre aléatoire')} checked={synced?false:s.options.shuffle} disabled={disabled||synced} description={synced?tr("Disabled while Faceplate JSAUX is synchronised.","Désactivé lorsque la Faceplate JSAUX est synchronisée."):undefined} onChange={v=>change({shuffle:v})}/></PanelSectionRow>
        <PanelSectionRow>{dropdown(tr('Transition','Transition'),'transition',[['crossfade',tr('Crossfade','Fondu enchaîné')],['fade-black',tr('Fade through black','Fondu au noir')]])}</PanelSectionRow>
        <PanelSectionRow>{dropdown(tr('Framing','Cadrage'),'framing',[['original',tr('Original · no crop','Original · sans coupe')],['16:9','16:9 · TV'],['16:10','16:10 · Steam Deck']])}</PanelSectionRow>
        <PanelSectionRow>{dropdown(tr('Game name','Nom du jeu'),'name_display',[['logo',tr('Logo','Logo')],['title',tr('Title','Titre')],['both',tr('Logo and title','Logo et titre')],['hidden',tr('Hidden','Masqué')]])}</PanelSectionRow>
        <PanelSectionRow>{toggle(tr('Show cover','Afficher la jaquette'),'show_cover')}</PanelSectionRow>
        <PanelSectionRow>{dropdown(tr('Cover position','Position de la jaquette'),'cover_position',[['bottom-left',tr('Bottom left','En bas à gauche')],['bottom-right',tr('Bottom right','En bas à droite')],['top-right',tr('Top right','En haut à droite')],['top-left',tr('Top left','En haut à gauche')]])}</PanelSectionRow>
        <PanelSectionRow>{dropdown(tr('Logo position','Position du logo'),'logo_position',[['bottom-left',tr('Bottom left','En bas à gauche')],['bottom-right',tr('Bottom right','En bas à droite')],['top-left',tr('Top left','En haut à gauche')],['top-right',tr('Top right','En haut à droite')]])}</PanelSectionRow>
        <PanelSectionRow>{toggle(tr('Reduced motion','Réduire les mouvements'),'reduced_motion')}</PanelSectionRow>
        <PanelSectionRow><ButtonItem label={tr('Steam inactivity settings','Réglage de l’inactivité Steam')} onClick={()=>Router.Navigate('/settings/power')}>{tr('Open Steam','Ouvrir Steam')}</ButtonItem></PanelSectionRow>
        <PanelSectionRow><DropdownItem label={tr('Interface language','Langue de l’interface')} selectedOption={language()} rgOptions={[{data:'fr',label:'Français'},{data:'en',label:'English'}]} onChange={o=>setLanguage(o.data)}/></PanelSectionRow>
      </PanelSection>}
      {(!section||section==='jsaux')&&jsauxVisible(jsaux)&&jsaux&&<PanelSection title={tr("Faceplate JSAUX",'Faceplate JSAUX')}>
        <PanelSectionRow><div className={'box das-jsaux tone-'+(panelSummary?.tone==='attention'?'amber':'cyan')} data-jsaux-card>
          <Field childrenContainerWidth="fixed" label={<span role="status">{panelSummary?.text}</span>}>
            <DialogButton aria-label={tr("Faceplate JSAUX details","Détails Faceplate JSAUX")} onClick={()=>setTechnical(!technical)}>{technical?tr('Hide','Masquer'):tr('Details','Détails')}</DialogButton></Field>
          <FaceplatePreparationStatus state={s}/>
          {technical&&<><p>{jsauxPhase(jsaux)}</p>
          {jsaux.prepared?.ready&&jsaux.last_transfer==='not-started'&&<p className="muted">{tr('USB reception not yet confirmed.','Réception USB pas encore confirmée.')}</p>}
          <p className="muted">{tr("Requires GabeCubeAura. TV playback is independent.","Nécessite GabeCubeAura. La lecture TV est indépendante.")}</p>
          {connectionBlocked&&<p className="muted">{tr('Reconnect; no new preparation needed.','Rétablissez la connexion ; aucune nouvelle préparation nécessaire.')}</p>}
          {jsaux.configured&&!connectionBlocked&&<small>{jsaux.installed?tr("Faceplate JSAUX images installed.","Visuels Faceplate JSAUX installés."):tr("Update the collection to apply Faceplate JSAUX changes.","Mettez à jour la collection pour appliquer les réglages Faceplate JSAUX.")}</small>}
          {jsaux.last_transfer==='confirmed'&&<p className="muted">{tr('USB reception confirmed; visual timing unmeasured.','Réception USB confirmée ; calage visuel non mesuré.')}</p>}
          {jsaux.restore_state&&jsaux.restore_state!=='not-needed'&&<small>{({pending:tr('Returning to the current display…','Retour à l’affichage actuel…'),deferred:tr('Return deferred by protection.','Retour différé par la protection.'),confirmed:tr('Return confirmed.','Retour confirmé.'),unconfirmed:tr('Return unconfirmed.','Retour non confirmé.'),blocked:tr('Return blocked by display settings.','Retour bloqué par les réglages d’affichage.')} as Record<string,string>)[jsaux.restore_state]}</small>}
          {Boolean(jsaux.retry_after_ms)&&<small>{jsaux.reason==='FLASH_DEFERRED'?tr('Memory protection: wait ','Protection mémoire : attendre '):tr('Next attempt in ','Nouvel essai dans ')}{Math.ceil((jsaux.retry_after_ms||0)/1000)} s</small>}
          {jsauxPreparationBusy(jsaux)&&typeof jsaux.prepared?.percent==='number'&&<><progress aria-label={tr("Faceplate JSAUX preparation","Préparation Faceplate JSAUX")} max={100} value={Math.max(0,Math.min(100,jsaux.prepared.percent))}/><small>{Math.round(Math.max(0,Math.min(100,jsaux.prepared.percent)))}%</small></>}
          </>}
        </div></PanelSectionRow>
        <PanelSectionRow><div data-recovery-target="faceplate"><ToggleField label={tr("Show collection on Faceplate JSAUX","Afficher la collection sur Faceplate JSAUX")} checked={jsaux.enabled} disabled={saving||jsauxBusy(jsaux)} onChange={enabled=>changeJsaux({enabled})}/></div></PanelSectionRow>
        {jsaux.enabled&&jsaux.detected&&jsaux.compatible&&!connectionBlocked&&<>
          <PanelSectionRow><DropdownItem label={tr("Faceplate JSAUX framing","Cadrage Faceplate JSAUX")} description={tr("Update the collection to apply this framing.","Mettez à jour la collection pour appliquer ce cadrage.")} selectedOption={jsaux.framing||'square'} disabled={disabled} rgOptions={[
            {data:'square',label:tr('Keep square · side borders','Conserver le carré · bandes latérales')},
            {data:'fill',label:tr("Fill Faceplate JSAUX · 64 × 54 crop","Remplir la Faceplate JSAUX · découpe 64 × 54")},
          ]} onChange={o=>changeJsaux({framing:o.data})}/></PanelSectionRow>
          <PanelSectionRow><DropdownItem label={tr('Playback mode','Mode de lecture')} selectedOption={jsaux.mode} disabled={disabled||!jsaux.compatible} rgOptions={[
            {data:'sync',label:tr('Synchronised (experimental)','Synchronisé (expérimental)')},
            {data:'async',label:tr('Independent loop','Boucle indépendante')},
          ]} onChange={o=>changeJsaux({mode:o.data})}/></PanelSectionRow>
          {technical&&<PanelSectionRow><p className="muted">{faceplateEffectiveMode(jsaux)==='sync'
            ?tr('Coordinated start; visual timing unmeasured.','Démarrage coordonné ; calage visuel non mesuré.')
            :tr("Faceplate JSAUX uses its own timing.","La Faceplate JSAUX suit sa propre durée.")}</p></PanelSectionRow>}
          {synced&&technical&&<>
            <PanelSectionRow><ButtonItem label={tr('Visual alignment','Alignement visuel')} description={tr('Saved for this device and collection; no GIF rebuild.','Enregistré pour cet appareil et cette collection ; aucun GIF à refaire.')} disabled={disabled||!jsaux.calibration?.available} onClick={()=>{setAlignmentDraft(jsaux.calibration?.offset_ms??0);setAligning(!aligning);}}>{aligning?tr('Close','Fermer'):tr('Adjust','Ajuster')}</ButtonItem></PanelSectionRow>
            {aligning&&<>
              <PanelSectionRow><p className="muted">{tr('Compare both displays during the Steam screensaver, then exit to adjust.','Comparez les deux écrans pendant la veille Steam, puis quittez-la pour ajuster.')}</p></PanelSectionRow>
              <PanelSectionRow><SliderField label={tr('TV timing correction','Correction du calage TV')+` · ${(alignmentDraft/1000).toFixed(1)} s`} description={tr('Positive: TV changes later. Negative: TV changes earlier.','Positif : la TV change plus tard. Négatif : la TV change plus tôt.')} value={alignmentDraft} min={-10000} max={10000} step={100} disabled={disabled} onChange={setAlignmentDraft}/></PanelSectionRow>
              <Focusable className="collection-player-controls" flow-children="row"><DialogButton style={{width:'auto',minWidth:0,flex:'1 1 0'}} disabled={disabled} onClick={()=>setAlignmentDraft(Math.min(10000,alignmentDraft+500))}>{tr('TV changes too early','La TV change trop tôt')}</DialogButton><DialogButton style={{width:'auto',minWidth:0,flex:'1 1 0'}} disabled={disabled} onClick={()=>setAlignmentDraft(Math.max(-10000,alignmentDraft-500))}>{tr('TV changes too late','La TV change trop tard')}</DialogButton></Focusable>
              <PanelSectionRow><ButtonItem label={tr('Save alignment','Enregistrer le calage')} disabled={disabled} onClick={()=>void run('jsaux_configure',{patch:{alignment_ms:alignmentDraft}}).then(result=>{if(result)setNotice(tr('Saved. Restart the Steam screensaver.','Enregistré. Relancez la veille Steam.'));})}>{tr('Save','Enregistrer')}</ButtonItem></PanelSectionRow>
              <PanelSectionRow><ButtonItem label={tr('Reset alignment only','Réinitialiser uniquement le calage')} disabled={disabled} onClick={()=>{setAlignmentDraft(0);void run('jsaux_configure',{patch:{alignment_ms:0}});}}>{tr('Reset','Réinitialiser')}</ButtonItem></PanelSectionRow>
              <PanelSectionRow><small>{tr('If synchronisation times out, TV playback continues.','Si la synchronisation expire, la lecture TV continue.')}</small></PanelSectionRow>
            </>}
          </>}
          <PanelSectionRow>{synced?<Field label={tr('Time per game','Durée par jeu')} description={tr('Follows TV','Suit la TV')} childrenLayout="inline" childrenContainerWidth="fixed"><span data-jsaux-duration>{s.options.scene_seconds} s</span></Field>
            :<SliderField label={tr("Faceplate JSAUX time per game","Durée par jeu sur la Faceplate JSAUX")+` · ${jsaux.page_seconds} s`} value={jsaux.page_seconds} min={2} max={180} step={1} disabled={disabled||!jsaux.compatible} onChange={page_seconds=>changeJsaux({page_seconds})}/>}</PanelSectionRow>
          <PanelSectionRow><DropdownItem label={tr("Faceplate JSAUX transition","Transition Faceplate JSAUX")} selectedOption={jsaux.transition} disabled={disabled||!jsaux.compatible} rgOptions={[
            {data:'fade',label:tr('Fade','Fondu')},{data:'wipe',label:tr('Wipe','Balayage')},
            {data:'slide',label:tr('Slide','Glissement')},{data:'dissolve',label:tr('Dissolve','Dissolution')},{data:'none',label:tr('None','Aucune')},
          ]} onChange={o=>changeJsaux({transition:o.data})}/></PanelSectionRow>
          {!inCollection&&<PanelSectionRow><ButtonItem label={tr('My collection','Ma collection')} disabled={saving} onClick={onCollection}>{tr('Back to preparation','Retour à la préparation')}</ButtonItem></PanelSectionRow>}
          {technical&&jsaux.prepared?.ready&&<PanelSectionRow>
            <small>{jsaux.prepared.pages} {tr('games','jeux')} · {jsaux.prepared.frames} frames</small>
            {Boolean(jsaux.prepared.power_limited_frames)&&<p className="muted">{tr("Bright images adapted; brightness setting unchanged.","Images claires adaptées ; réglage de luminosité inchangé.")}</p>}
            {jsaux.prepared.transition_optimized&&<p className="muted">{tr('Lighter transitions; games and durations unchanged.','Transitions allégées ; jeux et durées conservés.')}</p>}
            {faceplateEffectiveMode(jsaux)==='sync'&&<p className={jsaux.prepared.sync_admissible?'muted':'error'}>{jsaux.prepared.sync_admissible
              ?tr('Estimated transfer: '+Math.ceil((jsaux.prepared.estimate_ms||0)/1000)+' s · start limit: '+Math.round((jsaux.prepared.sync_wait_ms||2500)/1000)+' s.','Transfert estimé : '+Math.ceil((jsaux.prepared.estimate_ms||0)/1000)+' s · délai maximal : '+Math.round((jsaux.prepared.sync_wait_ms||2500)/1000)+' s.')
              :tr('The next preparation will use lots with independent playback.','La prochaine préparation utilisera des lots en lecture indépendante.')}</p>}
          </PanelSectionRow>}

          {jsaux.prepared?.ready&&<PanelSectionRow><ButtonItem label={jsauxPreview?tr("Hide Faceplate JSAUX preview","Masquer l’aperçu Faceplate JSAUX"):tr("Preview Faceplate JSAUX","Aperçu Faceplate JSAUX")} description={tr("Preview only; no USB transfer.","Aperçu uniquement ; aucun transfert USB.")} disabled={saving} onClick={()=>{
            if(jsauxPreview){setJsauxPreview('');return;}
            void run<{data_url:string;width:number;height:number;bytes:number}>('jsaux_preview').then(result=>{
              const url=jsauxPreviewURL(result?.data_url);
              if(alive.current&&url&&result?.width===64&&result.height===54&&result.bytes<=196608)setJsauxPreview(url);
            });
          }}>{jsauxPreview?tr('Hide','Masquer'):tr('Watch','Voir')}</ButtonItem></PanelSectionRow>}
          {jsauxPreview&&<PanelSectionRow><figure className="das-jsaux-preview"><img src={jsauxPreview} width={256} height={216} alt={tr("Prepared Faceplate JSAUX GIF, 64 by 54","GIF Faceplate JSAUX préparé, 64 sur 54")}/><figcaption>{tr('64 × 54 · software preview','64 × 54 · aperçu logiciel')}</figcaption></figure></PanelSectionRow>}
        </>}
      </PanelSection>}
      {hasJsaux&&<div data-gca-connection-check><ButtonItem label={connectionCheck==='checking'?tr('Checking GabeCubeAura…','Vérification de GabeCubeAura…'):tr('Check GabeCubeAura','Vérifier GabeCubeAura')} disabled={saving||connectionCheck==='checking'} onClick={()=>void retryConnection()}>{connectionCheck==='checking'?tr('Checking…','Vérification…'):tr('Check','Vérifier')}</ButtonItem>
        {connectionCheck!=='idle'&&<p className="gca-check-feedback" data-state={connectionCheck} role="status" aria-live="polite">{connectionCheck==='present'?tr('✓ GabeCubeAura available.','✓ GabeCubeAura disponible.'):connectionCheck==='unavailable'?tr('GabeCubeAura is not responding. Enable it in Decky, then retry.','GabeCubeAura ne répond pas. Activez-le dans Decky, puis réessayez.'):tr('Checking…','Vérification en cours…')}</p>}
      </div>}</div>;
}
