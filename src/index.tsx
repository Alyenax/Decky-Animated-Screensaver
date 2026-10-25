import {Component,type ReactNode} from 'react';
import {definePlugin,routerHook,toaster} from '@decky/api';
import {ButtonItem,Navigation,Router,staticClasses} from '@decky/ui';
import {FaFilm} from 'react-icons/fa';
import {StudioShell,QuickShell} from './StudioShell';
import {StudioRoute} from './StudioRoute';
import {client} from './client';
import type {Tab} from './model';
import {tr} from './i18n';
import {installJsauxPlayerRelay} from './jsauxRelay';
import {JsauxStorageRelay} from './jsauxStorage';
import {relayEnabled,storageAvailable,relayRecovery} from './jsauxDiagnostic';
import {QuickHeader} from './QuickControls';
import {startUpdateNotifications} from './update_notifications';
import {UPDATES_ROUTE,OPEN_UPDATES_EVENT} from './update_notice';
import {OPEN_ATTENTION_EVENT} from './recovery';
import type {UpdateState} from './types';

declare const SteamClient:any;
const ROUTE='/decky-animated-screensaver';
let launchTab:Tab='library';
let launchAttention=false;

class Boundary extends Component<{children:ReactNode},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<div style={{padding:24}}><p>{tr('Screensaver interface unavailable.','Interface indisponible.')}</p><ButtonItem label={tr('Retry','Réessayer')} onClick={()=>this.setState({failed:false})}>{tr('Retry','Réessayer')}</ButtonItem></div>:this.props.children;}
}

function Route(){return <Boundary><StudioRoute><StudioShell tab={launchTab} attention={launchAttention}/></StudioRoute></Boundary>;}
function UpdateRoute(){return <Boundary><StudioRoute focusUpdates><StudioShell tab="advanced" updates/></StudioRoute></Boundary>;}

export default definePlugin(()=>{
  const registrations:any[]=[];const ids=new Set<number>();let active=true;
  let updates:ReturnType<typeof startUpdateNotifications>|undefined;
  const snapshot=()=>{
    try{const rows=(Router as any).RunningApps;
      if(Array.isArray(rows)){ids.clear();for(const row of rows){const n=Number(row?.appid??row?.appID??row?.unAppID);if(Number.isInteger(n)&&n>0)ids.add(n);}}
      else{const row=(Router as any).MainRunningApp;const n=Number(row?.appid??row?.appID??row?.unAppID);if(Number.isInteger(n)&&n>0)ids.add(n);}
    }catch{}
  };
  const send=()=>{if(active){void client('session',{ids:[...ids]}).catch(()=>{});if(!ids.size)void updates?.check();}};
  snapshot();send();
  let stopJsauxRelay:(()=>void)|undefined;
  let storageRelay:JsauxStorageRelay|undefined;
  let recoveryTimer:ReturnType<typeof setTimeout>|undefined,recoveryPending=false,recoveryAttempt=0;
  const enableRelay=(enabled:boolean,transport='legacy')=>{
    if(!active)return;
    relayEnabled(enabled);
    if(!enabled||transport==='http-loopback-v1'){stopJsauxRelay?.();stopJsauxRelay=undefined;storageRelay?.dispose();storageRelay=undefined;return;}
    if(!stopJsauxRelay)stopJsauxRelay=installJsauxPlayerRelay({client});
    try{const storage=SteamClient?.Storage;const available=typeof storage?.GetString==='function'&&typeof storage?.SetString==='function';storageAvailable(available);if(!storageRelay&&available){
      storageRelay=new JsauxStorageRelay(client,storage);storageRelay.start();
    }}catch{storageAvailable(false);}
  };
  const availability=(event:Event)=>{const state=(event as CustomEvent).detail;enableRelay(state?.enabled===true,state?.transport);};
  window.addEventListener('das-jsaux-availability',availability);
  const recoverRelay=()=>{
    if(!active||recoveryPending)return;recoveryPending=true;
    relayRecovery();
    void client('jsaux_recover').then(state=>{recoveryAttempt=0;enableRelay(Boolean(state.jsaux?.relay_enabled),state.jsaux?.relay_transport);}).catch(()=>{
      relayRecovery(true);
      const delay=[1000,2000,4000,10000][recoveryAttempt++];
      if(active&&delay)recoveryTimer=setTimeout(recoverRelay,delay);
    }).finally(()=>{recoveryPending=false;});
  };
  void client('state').then(state=>enableRelay(Boolean(state.jsaux?.relay_enabled),state.jsaux?.relay_transport)).catch(()=>{});
  recoverRelay();
  try{const registration=SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications?.((event:any)=>{
    const n=Number(event?.unAppID);if(!Number.isInteger(n)||n<=0)return;
    if(event.bRunning)ids.add(n);else ids.delete(n);send();
  });if(registration)registrations.push(registration);}catch{}
  try{const registration=SteamClient?.System?.RegisterForOnSuspendRequest?.(()=>{void client('suspend').catch(()=>{});});if(registration)registrations.push(registration);}catch{}
  try{const registration=SteamClient?.System?.RegisterForOnResumeFromSuspend?.(()=>{snapshot();send();recoverRelay();});if(registration)registrations.push(registration);}catch{}
  routerHook.addRoute(ROUTE,Route,{exact:true});
  routerHook.addRoute(UPDATES_ROUTE,UpdateRoute,{exact:true});
  const openUpdates=()=>{Navigation.Navigate(UPDATES_ROUTE);Navigation.CloseSideMenus();window.dispatchEvent(new Event(OPEN_UPDATES_EVENT));};
  updates=startUpdateNotifications({read:()=>client<UpdateState>('update_status'),
    notify:data=>toaster.toast({...data,icon:<FaFilm/>}),open:openUpdates,playing:()=>ids.size>0,
    storage:{getItem:key=>window.localStorage.getItem(key),setItem:(key,value)=>window.localStorage.setItem(key,value)}});
  const open=(tab:Tab,attention=false)=>{launchTab=tab;launchAttention=attention;Navigation.Navigate(ROUTE);Navigation.CloseSideMenus();if(attention)window.dispatchEvent(new Event(OPEN_ATTENTION_EVENT));};
  return {name:'Animated Screensaver',titleView:<QuickHeader className={staticClasses?.Title} title="Animated Screensaver" onOpenSettings={()=>open('settings')}/>,
    icon:<FaFilm/>,content:<Boundary><QuickShell open={open} openUpdates={openUpdates}/></Boundary>,
    onDismount(){active=false;updates?.stop();relayEnabled(false);clearTimeout(recoveryTimer);window.removeEventListener('das-jsaux-availability',availability);stopJsauxRelay?.();storageRelay?.dispose();for(const registration of registrations){try{if(typeof registration==='function')registration();else registration.unregister?.();}catch{}}
      routerHook.removeRoute(ROUTE);routerHook.removeRoute(UPDATES_ROUTE);void client('suspend').catch(()=>{});void client('close_preview').catch(()=>{});
    }};
});
