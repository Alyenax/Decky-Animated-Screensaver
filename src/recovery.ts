import {tr,errorText} from './i18n';
import type {StudioGame,StudioProblem,StudioState} from './types';
import {jsauxBusy} from './types';

export const OPEN_ATTENTION_EVENT='das-open-attention';
export type RecoveryAction='choose'|'retry'|'settings'|'tools'|'storage'|'connection'|'diagnostic'|'attention'|'preparation'|'faceplate'|'library';
export interface Failure {code:string;action:string;appid?:number;role?:string}
export const safeErrorCode=(value:unknown)=>{
  const code=String(value??'').replace(/^Error:\s*/,'');
  return /^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(code)?code:'unexpected_error';
};
export const isGameRunningCode=(value:unknown)=>['game_running','paused_game'].includes(safeErrorCode(value).toLowerCase());
export const attentionCount=(state?:StudioState|null)=>state?.workspace?.issues_count??state?.issues_count??state?.failed_count??0;
export type CollectionRecoveryRoute='setup'|'activity'|'collection'|'attention'|'jsaux'|'assistance';
/** Navigation only: retry never starts a download, encode, install or USB write. */
export function collectionRecoveryRoute(action:RecoveryAction,state:StudioState):CollectionRecoveryRoute{
  if(action==='settings'||action==='tools')return 'setup';
  if(action==='storage'||action==='diagnostic')return 'assistance';
  if(action==='faceplate')return 'collection';
  if(action==='connection')return state.jsaux&&(state.jsaux.detected||state.jsaux.configured)?'jsaux':'assistance';
  if(action==='preparation')return state.workspace?.task.worker_active||state.job.worker_active||['paused','paused_game','running'].includes(state.job.state)||state.workspace?.task.state==='paused'||jsauxBusy(state.jsaux)?'activity':'collection';
  if(['attention','choose','retry'].includes(action)&&attentionCount(state)>0)return 'attention';
  return 'collection';
}
export function problemFor(game:StudioGame):StudioProblem|null{
  if(game.problem!==undefined)return game.problem;
  if(game.excluded)return null;
  for(const [field,role] of [['error','animation'],['cover_error','cover'],['logo_error','logo'],['smoothing_error','smoothing'],['motion_error','animation']] as const){
    if(field==='error'&&game[field]==='animation_missing')continue;
    if(game[field])return {appid:game.appid,name:game.name,role,code:safeErrorCode(game[field]),retained_media:game.status==='ready'};
  }
  return game.status==='error'?{appid:game.appid,name:game.name,role:'animation',code:'unexpected_error',retained_media:false}:null;
}
export function recoveryHelp(value:string,role='animation',operation=''):{title:string;body:string;label:string;action:RecoveryAction}{
  const code=safeErrorCode(value),asset=role==='cover'?tr('cover','jaquette'):role==='logo'?tr('logo','logo'):tr('animation','animation');
  const chooseLabel=role==='cover'?tr('Choose another cover','Choisir une autre jaquette'):role==='logo'?tr('Choose another logo','Choisir un autre logo'):tr('Choose another animation','Choisir une autre animation');
  if(code==='visual_size_limit')return {title:tr('Visual too large','Visuel trop volumineux'),body:errorText(code),label:tr('Open storage settings','Ouvrir les réglages de stockage'),action:'storage'};
  if(operation==='skipped-image')return {title:tr('Visual skipped','Visuel ignoré'),body:tr('Other games continue. Choose another visual for this game.','Les autres jeux continuent. Choisissez un autre visuel pour ce jeu.'),label:chooseLabel,action:'choose'};
  if(['key_missing','steamgriddb_unauthorized','steamgriddb_forbidden','steamgriddb_invalid_key'].includes(code))
    return {title:tr('SteamGridDB connection needs checking','Connexion SteamGridDB à vérifier'),body:tr('Save and verify your key before downloading images.','Enregistrez et vérifiez votre clé avant de télécharger les images.'),label:tr('Check my key','Vérifier ma clé'),action:'settings'};
  if(['ffmpeg_missing','ffprobe_missing','tools_missing','decoder_missing','probe_failed'].includes(code)||operation==='tools')
    return {title:tr('Video tools need checking','Outils vidéo à vérifier'),body:tr('Install or repair the video tools.','Installez ou réparez les outils vidéo.'),label:tr('Open video tools','Ouvrir les outils vidéo'),action:'tools'};
  if(['storage_limit','storage_budget','disk_full','storage_full','storage_reserve','space_low'].includes(code))
    return {title:tr('Not enough space for this preparation','Espace insuffisant pour cette préparation'),body:tr('Check storage before retrying. Nothing is deleted automatically.','Vérifiez le stockage avant de réessayer. Aucun fichier n’est supprimé automatiquement.'),label:tr('Open storage','Ouvrir le stockage'),action:'storage'};
  if(code==='BATCHES_REQUIRE_GCA_UPDATE')return {title:tr('GabeCubeAura update needed','GabeCubeAura doit être mis à jour'),body:errorText(code),label:tr('Check GabeCubeAura','Vérifier GabeCubeAura'),action:'connection'};
  if(['AUTH_DENIED','BROKER_UNAVAILABLE','VERSION_UNSUPPORTED','DEVICE_ABSENT','STEAM_STATE_STALE'].includes(code))
    return {title:tr("Faceplate JSAUX connection needs checking","Connexion Faceplate JSAUX à vérifier"),body:tr("Check GabeCubeAura and the Faceplate JSAUX connection.","Vérifiez GabeCubeAura et le branchement de la Faceplate JSAUX."),label:tr('Check GabeCubeAura','Vérifier GabeCubeAura'),action:'connection'};
  if(code==='JSAUX_SYNC_WINDOW'||code==='CONTENT_TOO_LARGE')return {title:tr('Prepare Faceplate JSAUX lots','Préparer les lots Faceplate JSAUX'),body:tr('All games will be kept, with independent playback.','Tous les jeux seront conservés, en lecture indépendante.'),label:tr('Open my collection','Ouvrir ma collection'),action:'library'};
  if(code==='collection_change_failed')return {title:tr('Collection could not be changed','Modification de la collection impossible'),body:errorText(code),label:tr('Check storage','Vérifier le stockage'),action:'storage'};
  if(code==='collection_order_changed')return {title:tr('Collection changed','Collection modifiée'),body:errorText(code),label:tr('Open my collection','Ouvrir ma collection'),action:'library'};
  if(code==='selection_undo_expired')return {title:tr('Selection changed','Sélection modifiée'),body:errorText(code),label:tr('Open my collection','Ouvrir ma collection'),action:'library'};
  if(['not_ready','CONTENT_MISSING','JSAUX_PREPARATION_REQUIRED','JSAUX_RELAY_UNAVAILABLE'].includes(code))return {title:tr('Collection update needs finishing','Mise à jour de la collection à terminer'),body:tr('Finish preparing the collection.','Terminez la préparation de la collection.'),label:tr('See the next step','Voir la prochaine étape'),action:'preparation'};
  if(isGameRunningCode(code))
    return {title:tr('Game running','Jeu en cours'),body:tr('Close the running game to avoid an overload, then try again.','Fermez le jeu en cours pour éviter une surcharge, puis réessayez.'),label:tr('View progress','Voir la progression'),action:'preparation'};
  if(['busy','PREPARATION_BUSY','resource_limit'].includes(code))
    return {title:tr('Preparation is currently paused or busy','Préparation en pause ou déjà en cours'),body:tr('View progress. Close the running game or wait for the current operation before continuing.','Consultez la progression. Quittez le jeu en cours ou attendez l’opération actuelle avant de continuer.'),label:tr('See the next step','Voir la prochaine étape'),action:'preparation'};
  if(code==='steamgriddb_rate_limited')return {title:tr('SteamGridDB is temporarily busy','SteamGridDB est temporairement occupé'),body:tr('Wait a moment, then retry. Your selection is kept.','Patientez un instant, puis réessayez. Votre sélection est conservée.'),label:tr('Retry this game','Réessayer ce jeu'),action:'retry'};
  if(code==='artwork_missing')return {title:tr('No artwork found','Aucun visuel trouvé'),body:tr('No usable image in Steam or SteamGridDB. Choose another image.','Aucune image utilisable dans Steam ou SteamGridDB. Choisissez-en une autre.'),label:tr('Choose an image','Choisir une image'),action:'choose'};
  if(['download_failed','download_timeout','network_error','steamgriddb_network','steamgriddb_timeout','steamgriddb_http'].includes(code))
    return {title:tr('Download did not finish','Le téléchargement n’a pas abouti'),body:tr('Check your Internet connection, then retry.','Vérifiez votre connexion Internet, puis réessayez.'),label:tr('Retry this game','Réessayer ce jeu'),action:'retry'};
  if(['invalid_media','decode_failed','decode_timeout','unsupported_source','unsupported_format','static_selection','animation_missing','source_too_large','download_too_large','invalid_webp'].includes(code))
    return {title:code==='animation_missing'?tr('No animation found','Aucune animation trouvée'):tr('This '+asset+' could not be prepared',role==='cover'?'La jaquette n’a pas pu être préparée':role==='logo'?'Le logo n’a pas pu être préparé':'L’animation n’a pas pu être préparée'),
      body:tr('Choose another image.','Choisissez un autre visuel.'),label:chooseLabel,action:'choose'};
  if(code==='static_motion_failed')return {title:tr('The slow zoom could not be prepared','Le zoom lent n’a pas pu être préparé'),body:tr('The still image is kept. Retry only this game to add movement.','L’image fixe est conservée. Réessayez uniquement ce jeu pour ajouter le mouvement.'),label:tr('Retry this game','Réessayer ce jeu'),action:'retry'};
  if(role==='smoothing')return {title:tr('Smoothing did not finish','La fluidification n’a pas abouti'),body:tr('The original animation is kept. You can retry this game.','L’animation d’origine est conservée. Vous pouvez réessayer ce jeu.'),label:tr('Retry this game','Réessayer ce jeu'),action:'retry'};
  return {title:tr('This operation did not finish','Cette opération n’a pas abouti'),body:tr('Send a diagnostic if the problem persists.','Envoyez un diagnostic si le problème persiste.'),label:tr('Open diagnostic','Ouvrir le diagnostic'),action:'diagnostic'};
}
