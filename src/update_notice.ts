import {useSyncExternalStore} from 'react';
import type {UpdateState} from './types';

export interface UpdateNotice {
  channel:string;version:string;installed:string;phase:string;available:boolean;percent:number;
}
let current:UpdateNotice|null=null;
const listeners=new Set<()=>void>();
export const subscribeUpdates=(fn:()=>void)=>{listeners.add(fn);return()=>{listeners.delete(fn);};};
export const getUpdateNotice=()=>current;
export function publishUpdate(state:UpdateState){
  const value:UpdateNotice={channel:state.channel,version:state.available_version,installed:state.installed_version,
    phase:state.phase,available:state.available,
    percent:Math.max(0,Math.min(100,Number(state.percent)||0))};
  if(JSON.stringify(value)===JSON.stringify(current))return;
  current=value;listeners.forEach(fn=>fn());
}
export const useUpdateNotice=()=>useSyncExternalStore(subscribeUpdates,getUpdateNotice);
export function visibleUpdate(s:UpdateNotice|null):s is UpdateNotice{
  return Boolean(s?.available&&['stable','beta'].includes(s.channel)
    && /^\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$/.test(s.version)
    && s.version!==s.installed&&!['installing','updated','rolled_back'].includes(s.phase));
}
export const UPDATES_ROUTE='/decky-animated-screensaver/updates';
export const OPEN_UPDATES_EVENT='das-open-updates';
