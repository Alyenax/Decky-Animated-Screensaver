import type {StudioState} from './types';
import {busy,jobBusy} from './model';
import {jsauxPreparationBusy} from './types';
import {faceplateRebuildRequired,faceplateTaskResolved,faceplateEffectiveMode} from './faceplateUX';

export type CollectionTab='collection'|'add'|'settings';
// A prepared file is not necessarily in the collection installed in Steam.
export function installedSceneCount(s:StudioState):number|undefined{
  const n=s.installation.scene_count;
  return s.installation.installed&&typeof n==='number'&&Number.isInteger(n)&&n>=0?n:undefined;
}
export function collectionActivity(s:StudioState){
  const task=s.workspace?.task;
  // A live/restoring display is not another preparation. Keep an installed
  // result visible even while its orchestration thread is returning.
  if(!jobBusy(s.job)&&!jsauxPreparationBusy(s.jsaux)){
    if(faceplateTaskResolved(s))return 'installed';
    if(task?.state==='partial')return 'partial';
    if(task?.state==='done')return task.outcome==='installed'?'installed':task.outcome==='unchanged'?'unchanged':task.outcome==='empty'?'empty':'finished';
    if(task?.state==='error'||task?.state==='failed')return 'error';
    if(task?.state==='cancelled')return 'cancelled';
  }
  if(task?.state==='applying')return 'applying';
  if(s.job.state==='paused_game'&&task?.operation!=='install')return 'waiting_game';
  if(task?.state==='paused')return 'paused';
  if(task?.worker_active||busy(s)||jsauxPreparationBusy(s.jsaux))return s.job.state==='paused'?'paused':s.job.state==='paused_game'?'waiting_game':'preparing';
  if(s.job.state==='paused')return 'paused';
  if(task?.state==='partial')return 'partial';
  if(task?.state==='done')return task.outcome==='installed'?'installed':task.outcome==='unchanged'?'unchanged':task.outcome==='empty'?'empty':'finished';
  if(task?.error||task?.state==='error'||task?.state==='failed')return 'error';
  if(task?.state==='cancelled'||s.job.state==='cancelled')return 'cancelled';
  return 'idle';
}
export function collectionStep(s:StudioState){
  const w=s.workspace,t=w?.task;
  if(s.job.state==='paused_game'&&t?.operation!=='install')return 'activity';
  if(t?.state==='paused')return 'resume';
  if(t?.worker_active||busy(s)||jsauxPreparationBusy(s.jsaux))return 'activity';
  if(s.job.state==='paused'||s.job.state==='paused_game')return 'resume';
  if(w?.pending_count)return 'prepare';
  if(!s.ready_count&&w?.skipped_count&&!w.issues_count)return 'choose';
  if(!w?.member_count||!w.included_count)return 'choose';
  if(w?.issues_count)return 'attention';
  const j=s.jsaux;
  if(j?.enabled&&j.detected&&j.compatible&&(faceplateRebuildRequired(j)||faceplateEffectiveMode(j)==='sync'&&j.prepared?.ready&&!j.prepared.sync_admissible))return 'faceplate';
  if(j?.enabled&&j.detected&&j.compatible&&j.prepared?.ready&&!j.installed)return 'install';
  if(w?.draft_count||!s.installation.installed||s.installation.needs_update||s.installation.needs_repair)return 'install';
  return 'preview';
}
