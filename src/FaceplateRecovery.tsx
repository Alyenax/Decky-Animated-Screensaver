import {DialogButton,Focusable} from '@decky/ui';
import type {StudioState} from './types';
import {faceplateIssue} from './faceplateUX';
import {tr} from './i18n';

/** Rendering stays read-only; normal preparation applies capacity fallback. */
export function FaceplateRecovery({state,disabled,onPrepare,onConnection,onDetails}:{state:StudioState;disabled:boolean;onPrepare:()=>void;onConnection:()=>void;onDetails:()=>void}){
 const issue=faceplateIssue(state);if(!issue)return null;
 const action=(key:string,label:string,run:()=>void)=><DialogButton className="collection-action" data-collection-focus={key} disabled={disabled} onClick={run}>{label}</DialogButton>;
 return <section className="collection-faceplate-recovery" data-faceplate-recovery={issue.kind}>
  <p role="status">{['sync-capacity','capacity'].includes(issue.kind)?tr('This collection will use lots with independent playback.','Cette collection utilisera des lots en lecture indépendante.'):issue.kind==='connection'?(issue.code==='BATCHES_REQUIRE_GCA_UPDATE'?tr('Update GabeCubeAura for playback in lots.','Mettez GabeCubeAura à jour pour la lecture en lots.'):tr('Check GabeCubeAura; no GIF rebuild needed.','Vérifiez GabeCubeAura ; aucun GIF à refaire.')):issue.kind==='transfer'?tr('Faceplate JSAUX reception unconfirmed. Prepared files are kept.','Réception Faceplate JSAUX non confirmée. Fichiers préparés conservés.'):tr('Faceplate JSAUX visuals need updating. TV files are kept.','Visuels Faceplate JSAUX à mettre à jour. Fichiers TV conservés.')}</p>
  <Focusable className="collection-actions" flow-children="row">
   {['sync-capacity','capacity'].includes(issue.kind)&&action('prepare-batches',tr('Prepare lots','Préparer les lots'),onPrepare)}
   {issue.kind==='connection'&&action('check-gca',tr('Check GabeCubeAura','Vérifier GabeCubeAura'),onConnection)}
   {issue.kind==='preparation'&&action('prepare-faceplate',tr('Prepare Faceplate JSAUX','Préparer la Faceplate JSAUX'),onPrepare)}
   {issue.kind==='transfer'&&action('jsaux',tr('Transfer details','Détails du transfert'),onDetails)}
  </Focusable>
 </section>;
}
