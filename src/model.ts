import { jsauxBusy, type StudioState } from './types';
export type Tab='library'|'preview'|'preparation'|'settings'|'advanced';
export const jobBusy=(job?:StudioState['job'])=>typeof job?.worker_active==='boolean'?job.worker_active:['running','paused_game'].includes(job?.state||'');
export const busy=(s?:StudioState|null)=>Boolean(s?.workspace?.task.worker_active || jobBusy(s?.job));
export function nextStep(s:StudioState) {
  if(busy(s)||jsauxBusy(s.jsaux))return {kind:'working',action:null,tone:'cyan'} as const;
  // Installing prepared media does not need the API key or a decoder.
  if(s.installation.error)return {kind:'conflict',action:null,tone:'amber'} as const;
  if(s.ready_count){
    if(s.jsaux?.enabled&&s.jsaux.detected&&s.jsaux.compatible&&!s.jsaux.prepared?.ready){
      if(!s.media_tools.available)return {kind:'setup',action:'settings',tone:'amber'} as const;
      return {kind:'faceplate',action:'jsaux_prepare',tone:'cyan'} as const;
    }
    if(s.installation.needs_repair)return {kind:'repair',action:'repair',tone:'amber'} as const;
    if(!s.installation.installed)return {kind:'install',action:'install',tone:'green'} as const;
    if(s.installation.needs_update || s.jsaux?.detected&&s.jsaux.compatible&&s.jsaux.enabled&&s.jsaux.prepared?.ready&&!s.jsaux.installed)return {kind:'update',action:'install',tone:'green'} as const;
    return {kind:'current',action:null,tone:'green'} as const;
  }
  if(!s.key_configured || !s.media_tools.available)return {kind:'setup',action:'settings',tone:'amber'} as const;
  if(!s.included_count)return {kind:'choose',action:'library',tone:'violet'} as const;
  if(s.job.state==='paused')return {kind:'resume',action:'resume',tone:'amber'} as const;
  if(!s.ready_count)return {kind:'prepare',action:'prepare',tone:'cyan'} as const;
  return {kind:'current',action:null,tone:'green'} as const;
}
export function safeImage(value?:string):string|undefined {
  if(!value)return;
  if(value.length<=350000 && /^data:image\/(?:jpeg|png);base64,[A-Za-z0-9+/]+={0,2}$/.test(value))return value;
  try{const u=new URL(value);const steam=['shared.akamai.steamstatic.com','shared.fastly.steamstatic.com','cdn.akamai.steamstatic.com','cdn.cloudflare.steamstatic.com'].includes(u.hostname)&&/^\/(store_item_assets\/)?steam\/apps\/\d+\//.test(u.pathname);
    const sgdb=u.hostname==='steamgriddb.com'||u.hostname.endsWith('.steamgriddb.com');
    const thumb=/\/(?:thumb|thumbs|grid_thumb|hero_thumb|logo_thumb|icon_thumb)\//.test(u.pathname);
    const legacy=(u.hostname==='s3.amazonaws.com'&&u.pathname.startsWith('/steamgriddb/thumb/'))||(u.hostname==='steamgriddb.s3.amazonaws.com'&&u.pathname.startsWith('/thumb/'));
    const format=/\.(png|jpe?g)$/.test(u.pathname.toLowerCase())||(sgdb||legacy)&&thumb&&/\.(webp|gif)$/i.test(u.pathname);
    if(u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&(steam||sgdb||legacy)&&format)return u.href;}catch{}
  return;
}
export function shouldPoll(s?:StudioState|null) {
  return busy(s) || Boolean(s?.workspace?.task.worker_active) || jsauxBusy(s?.jsaux) || s?.updates?.repository_state==='checking' || ['checking','downloading','installing'].includes(s?.updates?.phase||'') || ['downloading','extracting','verifying','queued'].includes(s?.media_tools?.state || '');
}
