import {preparedFileSize} from './faceplatePreparation';
import {faceplatePreparationFailed} from './faceplateUX';
import {tr} from './i18n';
import {jsauxVisible,jsauxPreparationBusy,type StudioState} from './types';

/** Prepared-file evidence, separate from USB reception and live display state. */
export function FaceplatePreparationStatus({state:s}:{state:StudioState}){
 const j=s.jsaux;if(!jsauxVisible(j)||!j?.enabled)return null;
 const prepared=j.prepared;
 const active=Boolean(jsauxPreparationBusy(j)||s.workspace?.task.worker_active&&s.workspace.task.stage==='faceplate');
 const pending=Boolean(s.workspace?.pending_count||s.workspace?.draft_count||prepared?.reason==='PREPARATION_STALE'||prepared?.identity_matches===false);
 const failed=faceplatePreparationFailed(s);
 const current=Boolean(prepared?.ready&&!active&&!pending&&!failed);
 const status=failed?'failed':active?'working':pending?'pending':current?'ready':'missing';
 const batches=prepared?.batch_count||1;
 const independentLots=batches>1||Boolean(prepared?.automatic_independent);
 const bytes=independentLots?prepared?.total_bytes??prepared?.bytes:prepared?.bytes;
 const size=preparedFileSize(bytes),validBytes=size!==undefined;
 const title=failed?tr('Faceplate JSAUX artwork preparation needs correction','Préparation des visuels Faceplate JSAUX à corriger'):active?tr('Faceplate JSAUX artwork preparation in progress','Préparation des visuels Faceplate JSAUX en cours'):pending?tr('Faceplate JSAUX artwork needs updating','Visuels Faceplate JSAUX à mettre à jour'):current?tr('Faceplate JSAUX artwork prepared','Visuels Faceplate JSAUX préparés'):tr('Faceplate JSAUX artwork not prepared','Visuels Faceplate JSAUX non préparés');
 return <div className="faceplate-preparation-status" data-ui-part="faceplate-preparation-status" data-status={status} data-bytes={prepared?.ready&&validBytes?bytes:undefined}>
   <p className={'faceplate-preparation-title'+(current?' is-ready':failed?' has-issue':'')} role="status">{current&&<span aria-hidden="true">✓ </span>}{title}</p>
   {prepared?.ready?<p className="faceplate-preparation-size" title={validBytes?tr(`${bytes} bytes`,`${bytes} octets`):undefined}>{size?(independentLots?tr(`${batches} lot${batches===1?'':'s'} · ${size} · independent playback`,`${batches} lot${batches===1?'':'s'} · ${size} · lecture indépendante`):current?tr(`Collection GIF: ${size}`,`GIF de la collection : ${size}`):tr(`Last prepared GIF: ${size}`,`Dernier GIF préparé : ${size}`)):tr('GIF size unavailable','Taille du GIF indisponible')}</p>:!active&&<p className="faceplate-preparation-size">{tr('No current prepared GIF','Aucun GIF préparé pour la sélection actuelle')}</p>}
 </div>;
}
