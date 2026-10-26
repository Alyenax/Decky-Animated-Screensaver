import {useSyncExternalStore} from 'react';
let revision=0;
const listeners=new Set<()=>void>();
function selected(){try{return localStorage.getItem('das-language') || 'auto';}catch{return 'auto';}}
export function language(): 'fr'|'en' {return (selected()==='auto' ? typeof navigator!=='undefined' ? navigator.language : 'en' : selected()).startsWith('fr') ? 'fr':'en';}
export function setLanguage(value:string){if(!['auto','en','fr'].includes(value))return;try{localStorage.setItem('das-language',value);}catch{}revision++;listeners.forEach(fn=>fn());}
export function useLanguage(){useSyncExternalStore(fn=>{listeners.add(fn);return()=>{listeners.delete(fn);};},()=>revision);return language();}
export function tr(en:string,fr:string){return language()==='fr'?fr:en;}
export const stepText=(kind:string)=>({
  working:tr('Preparing your collection','Préparation en cours'),setup:tr('Finish setup','Terminer la configuration'),
  choose:tr('Choose games','Choisir des jeux'),resume:tr('Resume preparation','Reprendre la préparation'),prepare:tr('Prepare collection','Préparer la collection'),
  faceplate:tr('Update my collection','Mettre à jour ma collection'),
  install:tr('Create my screensaver','Créer mon écran de veille'),update:tr('Update my collection','Mettre à jour ma collection'),repair:tr('Repair my collection','Réparer ma collection'),
  current:tr('Installed and up to date','Installé et à jour'),conflict:tr('Installation conflict · files preserved','Conflit d’installation · fichiers conservés')
} as Record<string,string>)[kind] || kind;
const errors:Record<string,[string,string]>={
  backend_starting:['Screensaver is starting. Please wait.','L’écran de veille démarre. Patientez un instant.'],
  backend_stopping:['Screensaver is stopping. Reopen the plugin after restart.','L’écran de veille s’arrête. Rouvrez le plugin après son redémarrage.'],
  backend_storage:['Screensaver could not access its settings. Check free space and permissions, then reload the plugin.','L’écran de veille ne peut pas accéder à ses réglages. Vérifiez l’espace libre et les permissions, puis rechargez le plugin.'],
  backend_start_failed:['Screensaver could not start. Check the Decky log, then reload the plugin.','L’écran de veille n’a pas pu démarrer. Consultez le journal Decky, puis rechargez le plugin.'],
  steam_tls_unavailable:['Steam connection could not be verified. Check the SteamOS date and updates.','Connexion Steam non vérifiée. Vérifiez la date et les mises à jour SteamOS.'],
  steam_timeout:['Steam took too long to respond. Retry. Your collection is unchanged.','Steam met trop de temps à répondre. Réessayez. Votre collection est conservée.'],
  steam_network_unavailable:['Steam could not be reached. Check the connection, then retry.','Steam est inaccessible. Vérifiez la connexion, puis réessayez.'],
  steam_http_error:['Steam refused the request. Retry, or send a diagnostic from Storage and assistance.','Steam a refusé la requête. Réessayez ou envoyez un diagnostic depuis Stockage et assistance.'],
  steam_rate_limited:['Steam is receiving too many requests. Wait a moment, then retry.','Steam reçoit trop de requêtes. Patientez un instant puis réessayez.'],
  steam_response_invalid:['Steam returned an unreadable response. Retry, or send a diagnostic.','Steam a renvoyé une réponse illisible. Réessayez ou envoyez un diagnostic.'],
  search_unavailable:['Steam search is unavailable. Check the connection, then change the search to retry.','La recherche Steam est indisponible. Vérifiez la connexion, puis modifiez la recherche pour réessayer.'],
  ranking_unavailable:['Steam ranking is unavailable. Choose another source and return to Top Steam to retry.','Le classement Steam est indisponible. Choisissez une autre source puis revenez sur Top Steam pour réessayer.'],
  read_busy:['Artwork or games are still loading. Wait a moment and try again.','Des visuels ou des jeux sont encore en chargement. Patientez un instant puis réessayez.'],
  workspace_recovered:['Some saved choices could not be restored. The installed collection is unchanged. Check your choices before preparing.','Certains choix enregistrés n’ont pas pu être restaurés. La collection installée est conservée. Vérifiez vos choix avant de préparer.'],
  interrupted:['Preparation was interrupted. Resume when ready; the installed collection is unchanged.','La préparation a été interrompue. Reprenez-la quand vous le souhaitez ; la collection installée est conservée.'],
  AUTH_DENIED:['GabeCubeAura refused the connection. Check that both plugins are running and up to date.','Connexion à GabeCubeAura refusée. Vérifiez que les deux plugins sont actifs et à jour.'],
  BROKER_UNAVAILABLE:['GabeCubeAura unavailable. Check that it is running and up to date.','GabeCubeAura indisponible. Vérifiez qu’il est actif et à jour.'],
  update_storage:['Update storage is unavailable or unsafe. The screensaver remains usable. Check storage and permissions.','Le stockage des mises à jour est inaccessible ou non sûr. L’écran de veille reste utilisable. Vérifiez l’espace et les permissions.'],
  update_repository_access:['Public releases are unavailable. Try again later. No GitHub connection is required.','Les versions publiques sont indisponibles. Réessayez plus tard. Aucune connexion GitHub n’est nécessaire.'],
  update_network:['Could not reach GitHub. Your current version is unchanged.','GitHub est inaccessible. Votre version actuelle est inchangée.'],
  update_checksum:['Update checksum failed. Nothing was installed.','La vérification de l’empreinte a échoué. Rien n’a été installé.'],
  update_manifest:['Update content verification failed. Nothing was installed.','La vérification du contenu a échoué. Rien n’a été installé.'],
  update_game_or_preparation:['Close your game and finish preparation before installing an update.','Fermez votre jeu et terminez la préparation avant la mise à jour.'],
  update_helper_unavailable:['Update installation needs SteamOS system Python and systemd.','L’installation nécessite Python système et systemd sur SteamOS.'],
  update_rolled_back:['The new backend did not start correctly. Your previous version was restored.','Le nouveau backend n’a pas démarré correctement. La version précédente a été restaurée.'],
  update_recovery_failed:['Automatic recovery failed. Reinstall the last working plugin archive through Decky.','La récupération automatique a échoué. Réinstallez l’archive de la dernière version fonctionnelle depuis Decky.'],
  update_cancelled:['Update download cancelled. Your current version is unchanged.','Téléchargement annulé. Votre version actuelle est inchangée.'],
  import_missing:['No previous GabeCubeAura Studio library was found.','Aucune ancienne bibliothèque Studio GabeCubeAura trouvée.'],
  import_unavailable:['Prepare the old library first, or create a new library here.','Préparez d’abord l’ancienne bibliothèque, ou créez-en une nouvelle ici.'],
  import_unverified:['Import stopped: a source file or its checksum changed. Originals are preserved.','Import interrompu : un fichier source ou son empreinte a changé. Les originaux sont conservés.'],
  import_failed:['Import could not finish. Originals are preserved.','L’import n’a pas abouti. Les originaux sont conservés.'],
  collection_order_changed:['Your collection changed. Reopen Reorder my collection.','La collection a changé. Rouvrez Réorganiser ma collection.'],
  selection_undo_expired:['The selection changed. Select your games again.','La sélection a changé. Sélectionnez à nouveau vos jeux.'],
  collection_change_failed:['Could not change the collection. Check storage and try again.','Modification impossible. Vérifiez le stockage et réessayez.'],
  confirmation_required:['Confirm this action first.','Confirmez d’abord cette action.'],
  worker_busy:['Another preparation is active. Pause it before importing.','Une autre préparation est active. Mettez-la en pause avant l’import.'],
  CONTENT_TOO_LARGE:["Prepare Faceplate JSAUX lots with independent playback.","Préparez les lots Faceplate JSAUX en lecture indépendante."],
  PREPARATION_BUSY:['Finish or cancel the current preparation first.','Terminez ou annulez d’abord la préparation en cours.'],
  backup_invalid:['This is not a complete Animated Screensaver settings backup. Current settings were kept.','Ce fichier n’est pas une sauvegarde complète des réglages Animated Screensaver. Les réglages actuels sont conservés.'],
  backup_path:['Choose a regular JSON file in your home folder. Links are not supported.','Choisissez un fichier JSON dans votre dossier personnel. Les liens ne sont pas acceptés.'],
  backup_failed:['The backup could not be saved. Check available storage.','La sauvegarde n’a pas pu être enregistrée. Vérifiez l’espace de stockage.'],
  unexpected_error:['This operation failed.','Cette opération a échoué.'],
  game_running:['Close the running game to avoid an overload, then try again.','Fermez le jeu en cours pour éviter une surcharge, puis réessayez.'],
  paused_game:['Close the running game to continue preparation.','Fermez le jeu en cours pour poursuivre la préparation.'],
  BATCHES_REQUIRE_GCA_UPDATE:['Update GabeCubeAura to play this collection in lots.','Mettez GabeCubeAura à jour pour lire cette collection en lots.'],
  GAME_RUNNING:['Close the running game to avoid an overload, then try again.','Fermez le jeu en cours pour éviter une surcharge, puis réessayez.'],
  CONTENT_MISSING:['Update the collection to prepare missing images.','Mettez à jour la collection pour préparer les images manquantes.'],
  JSAUX_PREPARATION_REQUIRED:["Update the collection to prepare Faceplate JSAUX images.","Mettez à jour la collection pour préparer les images Faceplate JSAUX."],
  JSAUX_RELAY_UNAVAILABLE:['Steam player connection unavailable. Update the collection.','Liaison avec le lecteur Steam indisponible. Mettez à jour la collection.'],
  JSAUX_SYNC_WINDOW:['This collection will use lots with independent playback.','Cette collection utilisera des lots en lecture indépendante.'],
  key_missing:['Add your SteamGridDB key.','Ajoutez votre clé SteamGridDB.'],steamgriddb_unauthorized:['SteamGridDB rejected this key.','SteamGridDB a refusé cette clé.'],
  steamgriddb_rate_limited:['SteamGridDB is busy. Retry later.','SteamGridDB est occupé. Réessayez plus tard.'],
  ffmpeg_missing:['Install or repair the video tools.','Installez ou réparez les outils vidéo.'],ffprobe_missing:['Install the video inspection tools.','Installez les outils d’inspection vidéo.'],
  probe_failed:['Video tools could not start. Check Settings → Setup.','Les outils vidéo ne démarrent pas. Vérifiez Réglages → Configuration.'],
  invalid_media:['The selected artwork could not be prepared. Choose another.','Le visuel choisi n’a pas pu être préparé. Choisissez-en un autre.'],decode_failed:['The selected artwork could not be decoded. Choose another.','Le visuel choisi n’a pas pu être décodé. Choisissez-en un autre.'],
  not_ready:['Finish preparing the collection.','Terminez la préparation de la collection.'],installation_conflict:['Unknown files preserved. Choose another screensaver while investigating.','Fichiers inconnus conservés. Choisissez un autre écran de veille pendant la vérification.'],
  resource_limit:['Preparation paused at its resource limit.','Préparation suspendue à sa limite de ressources.'],storage_limit:['Not enough storage. Increase the budget or clear unused cache.','Stockage insuffisant. Augmentez le budget ou nettoyez le cache inutilisé.'],
  worker_signal:['The media process was interrupted. Prepared visuals are kept.','Le traitement du visuel a été interrompu. Les visuels préparés sont conservés.'],
  runtime_isolation:['The isolated media process stopped. Prepared visuals are kept.','Le traitement isolé du visuel s’est arrêté. Les visuels préparés sont conservés.'],
  busy:['The previous operation is still stopping.','L’opération précédente est encore en cours d’arrêt.'],animation_missing:['No animation available for this game.','Aucune animation disponible pour ce jeu.'],
  artwork_missing:['No artwork found online or in Steam’s local files. Choose another image.','Aucun visuel trouvé en ligne ni dans les fichiers locaux de Steam. Choisissez une autre image.'],
  visual_size_limit:['This visual exceeds the maximum size per visual. Choose a smaller file or increase that setting.','Ce visuel dépasse la taille maximale par visuel. Choisissez un fichier plus léger ou augmentez ce réglage.'],
  source_limit:['A lightweight preview could not be made. The original remains selectable.','L’aperçu allégé n’a pas pu être créé. L’original reste sélectionnable.'],
  preview_cancelled:['Preview closed.','Aperçu fermé.'],
  download_failed:['Download failed. Check the connection and retry.','Échec du téléchargement. Vérifiez la connexion et réessayez.']
};
export function errorText(value:string){const clean=value.replace(/^Error:\s*/,'');const entry=errors[clean]||errors[clean.toLowerCase()];return entry?tr(...entry):clean;}
export function stageText(value:string){return ({idle:tr('Ready','Prêt'),queued:tr('Queued','En attente'),checking:tr('Checking selected game','Vérification du jeu sélectionné'),cache_ready:tr('Verified prepared media reused','Médias préparés vérifiés et réutilisés'),game_complete:tr('Game processed','Jeu traité'),game_error:tr('Game could not be prepared','Échec de préparation du jeu'),downloading:tr('Downloading artwork','Téléchargement'),validating:tr('Checking animation','Vérification de l’animation'),converting:tr('Preparing compatible video','Conversion vidéo'),smoothing:tr('Smoothing animation','Fluidification'),complete:tr('Finished','Terminé'),ready:tr('Ready','Prêt'),pending:tr('To prepare','À préparer'),missing:tr('No animation','Sans animation'),error:tr('Needs attention','À vérifier'),paused_game:tr('Paused during gameplay','Suspendu pendant le jeu'),paused:tr('Paused','En pause'),cancel:tr('Cancelled','Annulé'),interrupted:tr('Interrupted · resume when ready','Interrompu · reprise manuelle')} as Record<string,string>)[value]||value;}
