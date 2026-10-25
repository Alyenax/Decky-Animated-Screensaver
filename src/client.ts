import {callable} from '@decky/api';
import {Router} from '@decky/ui';
import type {StudioState,StudioClient} from './types';
import {getJsauxRelayDiagnostic} from './jsauxDiagnostic';
import {discoveryResponse} from './discoveryResponse';
import {artworkDiagnostic} from './artworkDiagnostic';
const request=callable<[string,Record<string,unknown>],unknown>('studio');
export const client:StudioClient=async<T=StudioState>(action:string,payload:Record<string,unknown>={})=>{
  // Seed the live session again before admitting CPU work, including after a
  // frontend reload. Lifetime notifications keep it updated with no idle poll.
  if(['prepare','workspace_prepare','workspace_install','resume','retry','jsaux_prepare'].includes(action)){
    const router=Router as any;
    const rows=Array.isArray(router.RunningApps)?router.RunningApps:[router.MainRunningApp];
    const ids=[...new Set<number>(rows.map((r:any)=>Number(r?.appid??r?.appID??r?.unAppID)).filter((n:number)=>Number.isInteger(n)&&n>0&&n<=0xffffffff))];
    await request('session',{ids});
  }
  const diagnostic=action==='diagnostic';
  return discoveryResponse(action,await request(action,diagnostic?{...payload,relay:getJsauxRelayDiagnostic(),artwork:artworkDiagnostic()}:payload)) as T;
};
