/** Cross-window Steam transport. Never authoritative for Steam activity or USB.
 * The backend still validates the installed export token, collection and lease;
 * GCA independently observes Steam before admitting any hardware work. */
import {playerMessage,safeReply,type JsauxPlayerMessage} from './jsauxRelay';
import {storageCount,storageReject,storageError,storageRunning} from './jsauxDiagnostic';
export const JSAUX_REQUEST_KEY='decky-animated-screensaver.jsaux.request.v1';
export const JSAUX_REPLY_KEY='decky-animated-screensaver.jsaux.reply.v1';
export interface SteamStorage {GetString(key:string):unknown;SetString(key:string,value:string):unknown}
type Client=(action:string,payload:Record<string,unknown>)=>Promise<unknown>;
export class JsauxStorageRelay {
  private current:JsauxPlayerMessage|null=null;
  private seen=new Set<string>();
  private closed=false;
  private pending=false;
  private began=0;
  private lastSeen=0;
  private timer:ReturnType<typeof setTimeout>|undefined;
  constructor(private client:Client,private storage:SteamStorage){}
  /** A single outstanding native read. A stalled native promise is never retried
   * into a growing pile of promises. The bounded timer ends on dismount. */
  start(){
    storageRunning(true);
    const tick=async()=>{
      if(this.closed||this.pending)return;
      this.pending=true;
      storageCount('probes');
      try {await this.receive(await this.storage.GetString(JSAUX_REQUEST_KEY));}catch(error){storageError('read_errors','READ_FAILED',error);}
      finally {
        this.pending=false;
        if(!this.closed)this.timer=setTimeout(()=>void tick(),this.current&&Date.now()-this.began<5000?10:500);
      }
    };
    void tick();
  }
  async receive(raw:unknown,now=Date.now()):Promise<boolean>{
    // An empty slot is normal and is not an incoming player message.
    if(raw===''||raw==null)return false;
    storageCount('received');
    if(this.closed)return storageReject('DISPOSED');
    if(typeof raw!=='string'||raw.length>4608)return storageReject('INVALID_STORAGE');
    let x:any;try{x=JSON.parse(raw);}catch{return storageReject('INVALID_STORAGE');}
    if(!x||!Number.isSafeInteger(x.at)||Math.abs(now-x.at)>5000)return storageReject('STALE_STORAGE');
    const message=playerMessage(x.payload);if(!message)return storageReject('INVALID_MESSAGE');
    if(this.current){
      if(message.session_id!==this.current.session_id){
        // A crashed player cannot pin the relay forever. GCA owns lease expiry.
        if(now-this.lastSeen<8000||message.event!=='open')return storageReject('STALE_MESSAGE');
      }else if(message.sequence<=this.current.sequence||message.token!==this.current.token||message.mode!==this.current.mode||message.collection_id!==this.current.collection_id)return storageReject('STALE_MESSAGE');
    }else if(message.event!=='open')return storageReject('NO_SESSION');
    if(message.event==='open'){
      if(this.seen.has(message.session_id))return storageReject('STALE_MESSAGE');
      this.seen.add(message.session_id);if(this.seen.size>64)this.seen=new Set([message.session_id]);
      this.began=now;
    }
    this.current=message;this.lastSeen=now;
    storageCount('routed');
    let result:Record<string,unknown>;
    try{result=safeReply(await this.client('jsaux_player',message));}catch(error){storageError('backend_errors','BACKEND_FAILED',error);result={accepted:false};}
    if(this.closed)return false;
    try{await this.storage.SetString(JSAUX_REPLY_KEY,JSON.stringify({session_id:message.session_id,sequence:message.sequence,result}));storageCount('replied');}catch(error){storageError('write_errors','WRITE_FAILED',error);}
    if(message.event==='stop'&&this.current?.session_id===message.session_id)this.current=null;
    return true;
  }
  dispose(){
    storageRunning(false);
    this.closed=true;clearTimeout(this.timer);
    const current=this.current;this.current=null;
    if(current){const {token,collection_id,session_id,mode,sequence}=current;
      void this.client('jsaux_player',{token,collection_id,session_id,mode,event:'stop',sequence:sequence+1,reason:'player-ended'}).catch(()=>{});}
  }
}
