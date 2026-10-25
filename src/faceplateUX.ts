import {tr} from './i18n';
import {jsauxVisible,jsauxPreparationBusy,type JsauxState,type StudioState} from './types';

// The settings preference can remain sync while a large prepared collection uses lots.
export const faceplateEffectiveMode=(j?:JsauxState)=>j?.prepared?.effective_mode||((j?.prepared?.batch_count||0)>1?'async':j?.mode);

// Historical playback reasons are not failures of the prepared collection.
export const faceplateRebuildRequired=(j?:JsauxState)=>Boolean(j?.enabled&&(
  !j.prepared?.ready||j.prepared.power_upgrade_required||
  ['CONTENT_INVALID','PREPARATION_POWER_REQUIRED','PREPARED_FILE_MISSING'].includes(j.reason||'')));
export function faceplateSummary(j?:JsauxState,pending=false){
  if(!jsauxVisible(j))return null;
  if(!j.enabled)return {kind:'off',tone:'neutral',text:tr("Faceplate JSAUX off","Faceplate JSAUX désactivée")} as const;
  if(jsauxPreparationBusy(j))return {kind:'working',tone:'neutral',text:tr("Preparing Faceplate JSAUX…","Préparation Faceplate JSAUX…")} as const;
  if(['AUTH_DENIED','VERSION_UNSUPPORTED','PROTOCOL_INVALID'].includes(j.reason||''))
    return {kind:'connection',tone:'attention',text:tr("Check Faceplate JSAUX connection","Connexion Faceplate JSAUX à vérifier")} as const;
  if(!j.detected||!j.compatible||['BROKER_UNAVAILABLE','STALE_BOOT','STEAM_STATE_STALE'].includes(j.reason||''))
    return {kind:'waiting',tone:'neutral',text:tr("Waiting for Faceplate JSAUX connection","Connexion Faceplate JSAUX en attente")} as const;
  if(pending||j.prepared?.reason==='PREPARATION_STALE')
    return {kind:'update',tone:'neutral',text:tr("Faceplate JSAUX update pending","Faceplate JSAUX à mettre à jour")} as const;
  if(j.reason==='CONTENT_TOO_LARGE'||j.reason==='JSAUX_SYNC_WINDOW')
    return {kind:'selection',tone:'attention',text:tr("Faceplate JSAUX lots need preparing","Faceplate JSAUX : lots à préparer")} as const;
  if(faceplateRebuildRequired(j))
    return {kind:'update',tone:'neutral',text:tr("Faceplate JSAUX update pending","Faceplate JSAUX à mettre à jour")} as const;
  if(faceplateEffectiveMode(j)==='sync'&&j.prepared?.ready&&j.prepared.sync_admissible===false)
    return {kind:'selection',tone:'attention',text:tr("Faceplate JSAUX lots need preparing","Faceplate JSAUX : lots à préparer")} as const;
  if(!j.installed)return {kind:'update',tone:'neutral',text:tr("Faceplate JSAUX update pending","Faceplate JSAUX à mettre à jour")} as const;
  if(['DEVICE_BUSY','PRIORITY_ACTIVE','FLASH_DEFERRED','DISPLAY_OFF','SUSPENDED','FACEPLATE_DISABLED','OWNERSHIP_UNAVAILABLE'].includes(j.reason||''))
    return {kind:'waiting',tone:'neutral',text:tr("Faceplate JSAUX temporarily unavailable","Faceplate JSAUX temporairement indisponible")} as const;
  if(j.reason==='USB_FAILED')return {kind:'transfer-failed',tone:'neutral',text:tr("Last Faceplate JSAUX transfer failed","Dernier transfert Faceplate JSAUX échoué")} as const;
  if(j.reason==='USB_UNCONFIRMED')
    return {kind:'receipt',tone:'neutral',text:tr("Faceplate JSAUX reception unconfirmed","Réception Faceplate JSAUX non confirmée")} as const;
  return {kind:'ready',tone:'neutral',text:tr("Faceplate JSAUX ready","Faceplate JSAUX prête")} as const;
}

/** Current faults win over a historical workflow result. No mutation here. */
export function faceplateIssue(s:StudioState){
 const j=s.jsaux;if(!jsauxVisible(j)||!j.enabled)return null;
 const task=s.workspace?.task;
 const historic=!j.prepared?.ready&&['partial','error','failed'].includes(task?.state||'')&&task?.faceplate_state==='repair_required'?(task.error||'PREPARATION_FAILED'):'';
 const code=j.controller_status_error||j.preparation_error||j.reason||historic;
 if(['BATCHES_REQUIRE_GCA_UPDATE','AUTH_DENIED','VERSION_UNSUPPORTED','PROTOCOL_INVALID','BROKER_UNAVAILABLE','STALE_BOOT'].includes(code))return {kind:'connection',code} as const;
 if(['USB_FAILED','USB_UNCONFIRMED'].includes(code))return {kind:'transfer',code} as const;
 if(code==='CONTENT_TOO_LARGE')return {kind:'capacity',code} as const;
 if(['PREPARATION_FAILED','CONTENT_INVALID','PREPARED_FILE_MISSING','CONTENT_MISSING','VALIDATION_LIMIT','JSAUX_PREPARATION_REQUIRED'].includes(code))return {kind:'preparation',code} as const;
 if(faceplateEffectiveMode(j)==='sync'&&(code==='JSAUX_SYNC_WINDOW'||j.prepared?.ready&&j.prepared.sync_admissible===false))
  return {kind:'sync-capacity',code:'JSAUX_SYNC_WINDOW'} as const;
 return null;
}
export const faceplateNeedsCorrection=(s:StudioState)=>Boolean(faceplateIssue(s));
export const faceplatePreparationFailed=(s:StudioState)=>faceplateIssue(s)?.kind==='preparation';

export function faceplateTaskResolved(s:StudioState){
 const w=s.workspace;
 return Boolean(w?.task.state==='partial'&&w.task.faceplate_state==='repair_required'&&
  s.jsaux?.prepared?.ready&&s.jsaux.installed&&!faceplateIssue(s)&&
  s.installation.installed&&!s.installation.needs_update&&!s.installation.needs_repair&&
  !w.pending_count&&!w.draft_count&&!w.issues_count);
}
