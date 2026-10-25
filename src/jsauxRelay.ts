/** Installed Steam iframe relay. Broker credentials never enter this module. */
import {frameCount,frameReject,frameError,frameInstalled} from './jsauxDiagnostic';
export const JSAUX_PLAYER_MESSAGE='das-jsaux-player-v1';
export const JSAUX_PLAYER_REPLY='das-jsaux-reply-v1';
type Client=(action:string,payload:Record<string,unknown>)=>Promise<unknown>;
type Frame={contentWindow:unknown;src:string;isConnected?:boolean};
type Source={postMessage:(value:unknown,origin:string)=>void};
export type PlayerEvent='open'|'clock'|'ready'|'started'|'heartbeat'|'stop';
export interface JsauxPlayerMessage extends Record<string,unknown>{
  event:PlayerEvent;token:string;collection_id:string;session_id:string;mode:'sync'|'async';sequence:number;
}
const fields:Record<PlayerEvent,string[]>={open:[],clock:[],ready:['ready_mono_ms','deadline_mono_ms','clock_uncertainty_ms'],
  started:['started_mono_ms','outcome','candidate_id'],heartbeat:[],stop:['reason']};
const id=(x:unknown)=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,80}$/.test(x);
const integer=(x:unknown)=>Number.isSafeInteger(x)&&Number(x)>=0;
const SCREEN_HOSTS=['uioverride-decky-animated-screensaver.steamscreensavers.host','decky-animated-screensaver.steamscreensavers.host'];
export function steamRelayOrigin(origin:string):boolean{
  try{const u=new URL(origin);return origin==='https://'+u.hostname&&!u.port&&
    (SCREEN_HOSTS.includes(u.hostname)||/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*steamloopback\.host$/.test(u.hostname));}catch{return false;}
}
export function playerMessage(value:unknown):JsauxPlayerMessage|null{
  if(!value||typeof value!=='object'||Array.isArray(value))return null;
  const x=value as Record<string,unknown>;
  try{if(JSON.stringify(value).length>4096)return null;}catch{return null;}
  if(!Object.prototype.hasOwnProperty.call(fields,String(x.event))||!id(x.token)||!id(x.session_id)||typeof x.collection_id!=='string'||!/^[a-f0-9]{64}$/.test(x.collection_id)
    ||!['sync','async'].includes(String(x.mode))||!integer(x.sequence)||Number(x.sequence)<1)return null;
  const expected=['event','token','collection_id','session_id','mode','sequence',...fields[x.event as PlayerEvent]];
  if(Object.keys(x).some(k=>!expected.includes(k))||expected.some(k=>!Object.prototype.hasOwnProperty.call(x,k)))return null;
  if(x.event==='ready'){
    if(x.mode==='async'){if(x.ready_mono_ms!==null||x.deadline_mono_ms!==null||x.clock_uncertainty_ms!==null)return null;}
    else if(!integer(x.ready_mono_ms)||!integer(x.deadline_mono_ms)||![2500,15000].includes(Number(x.deadline_mono_ms)-Number(x.ready_mono_ms))||!integer(x.clock_uncertainty_ms)||Number(x.clock_uncertainty_ms)>50)return null;
  }
  if(x.event==='started'){
    if(!['software-coordinated','tv-only','independent'].includes(String(x.outcome)))return null;
    if(x.mode==='async'?(x.started_mono_ms!==null||x.outcome!=='independent'):(!integer(x.started_mono_ms)||x.outcome==='independent'))return null;
    if(x.outcome==='software-coordinated'?!id(x.candidate_id):x.candidate_id!==null)return null;
  }
  if(x.event==='stop'&&x.reason!=='player-ended')return null;
  return {...x} as JsauxPlayerMessage;
}
function installedFrame(frame:Frame,origin:string):boolean{
  try{const u=new URL(frame.src);return frame.isConnected!==false&&u.origin===origin&&
    (SCREEN_HOSTS.includes(u.hostname)||u.hostname==='decky-animated-screensaver.steamloopback.host'||/(?:^|\/)decky-animated-screensaver\/(?:index\.html)?$/.test(u.pathname));}catch{return false;}
}
/** Validates source+installed URL here, and export token+collection in backend.
 * The player's lifecycle is NOT authoritative Steam state for GCA admission. */
export class JsauxFrameRelay{
  private active:{message:JsauxPlayerMessage;frame:Frame;source:Source;origin:string}|null=null;
  private disposed=false;
  private inFlight=0;
  constructor(private client:Client){}
  receive(event:Pick<MessageEvent,'origin'|'source'|'data'>,frames:Iterable<Frame>):boolean{
    // Ignore unrelated window messages entirely, including their contents.
    if(event.data?.type!==JSAUX_PLAYER_MESSAGE)return false;
    frameCount('received');
    if(this.disposed)return frameReject('DISPOSED');
    if(this.inFlight>=4)return frameReject('BUSY');
    if(!event.source||!steamRelayOrigin(event.origin))return frameReject('UNTRUSTED_ORIGIN');
    const frame=Array.from(frames).find(f=>f.contentWindow===event.source&&installedFrame(f,event.origin));
    const message=playerMessage(event.data.payload);
    if(!frame)return frameReject('FRAME_NOT_FOUND');
    if(!message)return frameReject('INVALID_MESSAGE');
    if(this.active){
      const same=this.active.source===event.source&&this.active.message.session_id===message.session_id;
      if(!same||this.active.message.collection_id!==message.collection_id||this.active.message.token!==message.token||this.active.message.mode!==message.mode||message.sequence<=this.active.message.sequence)return frameReject('STALE_MESSAGE');
    }else if(message.event!=='open')return frameReject('NO_SESSION');
    this.active={message,frame,source:event.source as unknown as Source,origin:event.origin};
    this.inFlight++;
    frameCount('routed');
    void this.client('jsaux_player',message).then(result=>{
      if(this.disposed||this.active?.message.session_id!==message.session_id||frame.isConnected===false)return;
      // Explicit allowlist: never reflect arbitrary backend state or capabilities.
      const safe=safeReply(result);
      try{(event.source as unknown as Source).postMessage({type:JSAUX_PLAYER_REPLY,session_id:message.session_id,sequence:message.sequence,result:safe},event.origin);frameCount('replied');}catch{frameError('WRITE_FAILED');}
    }).catch(()=>{
      frameError('BACKEND_FAILED');
      try{if(!this.disposed){(event.source as unknown as Source).postMessage({type:JSAUX_PLAYER_REPLY,session_id:message.session_id,sequence:message.sequence,result:{accepted:false}},event.origin);frameCount('replied');}}catch{frameError('WRITE_FAILED');}
    }).finally(()=>{this.inFlight--;if(message.event==='stop'&&this.active?.message.session_id===message.session_id)this.active=null;});
    return true;
  }
  check(){if(this.active?.frame.isConnected===false)this.stop();}
  stop(){const active=this.active;this.active=null;if(active){const {token,collection_id,session_id,mode,sequence}=active.message;
    void this.client('jsaux_player',{event:'stop',token,collection_id,session_id,mode,sequence:sequence+1,reason:'player-ended'}).catch(()=>{});}}
  dispose(){this.stop();this.disposed=true;}
}
export function safeReply(value:unknown):Record<string,unknown>{
  if(!value||typeof value!=='object')return {accepted:false};
  const x=value as Record<string,unknown>,out:Record<string,unknown>={};
  for(const k of ['accepted','tv_only','gate_accepted'])if(typeof x[k]==='boolean')out[k]=x[k];
  for(const k of ['broker_mono_ms','deadline_mono_ms'])if(integer(x[k]))out[k]=x[k];
  if(x.candidate&&typeof x.candidate==='object'){
    const c=x.candidate as Record<string,unknown>;
    if(id(c.candidate_id)&&integer(c.deadline_mono_ms)&&c.phase_basis==='gif-end-ack-assumption'&&c.optical_alignment==='unknown')
      out.candidate={candidate_id:c.candidate_id,deadline_mono_ms:c.deadline_mono_ms,phase_basis:c.phase_basis,optical_alignment:'unknown'};
  }
  if(Number.isInteger(x.alignment_ms)&&Math.abs(Number(x.alignment_ms))<=10000&&Number(x.alignment_ms)%100===0)out.alignment_ms=x.alignment_ms;
  const timing=x.timing as Record<string,unknown>|undefined;
  if(timing&&timing.basis==='broker-confirmation-event'&&integer(timing.reference_mono_ms)&&integer(timing.uncertainty_ms)&&Number(timing.uncertainty_ms)<=26)
    out.timing={reference_mono_ms:timing.reference_mono_ms,uncertainty_ms:timing.uncertainty_ms,basis:timing.basis};
  return out;
}
export function installJsauxPlayerRelay(options:{client:Client;window?:Window;document?:Document}):()=>void{
  const win=options.window??window,doc=options.document??document,relay=new JsauxFrameRelay(options.client);
  const listener=(event:MessageEvent)=>{relay.receive(event,doc.querySelectorAll('iframe'));};
  win.addEventListener('message',listener);
  const observer=new MutationObserver(()=>relay.check());
  observer.observe(doc.documentElement,{childList:true,subtree:true});
  frameInstalled(true);
  return ()=>{frameInstalled(false);win.removeEventListener('message',listener);observer.disconnect();relay.dispose();};
}
