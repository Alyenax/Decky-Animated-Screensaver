import type {UpdateState} from './types';
import {getUpdateNotice,publishUpdate,subscribeUpdates,visibleUpdate} from './update_notice';
import {tr} from './i18n';

type Toast={title:string;body:string;onClick:()=>void;duration:number;showToast:boolean;playSound:boolean};
interface Dependencies {
  read:()=>Promise<UpdateState>;notify:(toast:Toast)=>unknown;open:()=>void;playing:()=>boolean;
  storage?:Pick<Storage,'getItem'|'setItem'>;
  schedule?:(fn:()=>void,ms:number)=>unknown;clear?:(timer:unknown)=>void;
}
/** Cheap cached backend status only. Never checks GitHub, scans media or prepares. */
export function startUpdateNotifications(deps:Dependencies){
  let alive=true,pending=false;
  const seen=new Set<string>();
  const observe=()=>{
    const state=getUpdateNotice();
    if(!alive||!visibleUpdate(state)||!['available','ready'].includes(state.phase)||deps.playing())return;
    const key='das-update-notified-v1:'+state.channel;
    if(seen.has(key+state.version))return;
    try{if(deps.storage?.getItem(key)===state.version)return;}catch{}
    try{
      deps.notify({title:`Animated Screensaver · ${state.version}`,
        body:tr('Update available. Open the update button.','Mise à jour disponible. Ouvrir le bouton de mise à jour.'),
        duration:8000,showToast:true,playSound:true,onClick:()=>{if(alive)deps.open();}});
      seen.add(key+state.version);
      try{deps.storage?.setItem(key,state.version);}catch{}
    }catch{/* A failed native toast must not break the plugin or consume the notice. */}
  };
  const check=async()=>{
    if(!alive||pending)return;
    pending=true;
    const before=getUpdateNotice();
    try{const state=await deps.read();if(alive){if(before===getUpdateNotice())publishUpdate(state);observe();}}catch{}
    finally{pending=false;}
  };
  const unsubscribe=subscribeUpdates(observe);
  const timer=(deps.schedule??((fn,ms)=>setInterval(fn,ms)))(()=>void check(),30000);
  void check();
  return {check,stop(){alive=false;unsubscribe();(deps.clear??(value=>clearInterval(value as ReturnType<typeof setInterval>)))(timer);}};
}
