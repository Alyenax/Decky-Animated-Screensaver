import test from 'node:test';
import assert from 'node:assert/strict';
import {getUpdateNotice,publishUpdate,visibleUpdate} from '../../src/update_notice';
import {startUpdateNotifications} from '../../src/update_notifications';
import {focusUpdatePrimary} from '../../src/focus';
import type {UpdateState} from '../../src/types';
import {readFileSync} from 'node:fs';

const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function harness(){
  const state:UpdateState={channel:'stable',auto_check:true,interval_minutes:360,phase:'available',error:'',auth:{state:'connected',user_code:'',verification_uri:'',expires_at:0},
    repository:'Alyenax/Decky-Animated-Screensaver',repository_state:'ready',installed_version:'0.1.0-alpha.15',available_version:'0.1.0-alpha.16',available:true,checked_at:1,percent:0,confirmation:'private-confirmation'};
  publishUpdate({...state,available:false});
  const calls:string[]=[],toasts:any[]=[],storage=new Map<string,string>(),timers=new Set<()=>void>();
  let playing=false,resolve:((value:UpdateState)=>void)|undefined,fail=false;
  const start=()=>startUpdateNotifications({read:async()=>{calls.push('update_status');if(resolve===undefined)return state;return new Promise<UpdateState>(done=>{resolve=done;});},
    playing:()=>playing,notify:toast=>{if(fail)throw Error('native toast missing');toasts.push(toast);},open:()=>calls.push('open'),
    storage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>{storage.set(key,value);}},
    schedule:(fn,ms)=>{assert.equal(ms,30000);timers.add(fn);return fn;},clear:fn=>{timers.delete(fn as ()=>void);}});
  return {state,calls,toasts,storage,timers,start,playing:(value:boolean)=>playing=value,fail:(value:boolean)=>fail=value,
    hold:()=>{resolve=()=>{};},resolve:()=>resolve?.(state)};
}
test('one clickable Steam notice per version/channel, persistent across frontend reload',async()=>{
  const h=harness();const a=h.start();await flush();assert.equal(h.toasts.length,1);
  assert(h.toasts[0].playSound&&h.toasts[0].showToast);h.toasts[0].onClick();assert(h.calls.includes('open'));
  await a.check();publishUpdate(h.state);assert.equal(h.toasts.length,1);a.stop();assert.equal(h.timers.size,0);
  const b=h.start();await flush();assert.equal(h.toasts.length,1);
  h.state.available_version='0.1.0-alpha.17';await b.check();assert.equal(h.toasts.length,2);b.stop();
});
test('gaming delays the toast, but not the saved panel notice; leaving the game notifies once',async()=>{
  const h=harness();h.playing(true);const monitor=h.start();await flush();
  assert.equal(h.toasts.length,0);assert(visibleUpdate(getUpdateNotice()));
  h.playing(false);await monitor.check();assert.equal(h.toasts.length,1);monitor.stop();
});
test('overlapping cached reads coalesce and a stopped monitor ignores late responses/clicks',async()=>{
  const h=harness();h.hold();const monitor=h.start();void monitor.check();void monitor.check();
  assert.equal(h.calls.length,1);monitor.stop();h.resolve();await flush();assert.equal(h.toasts.length,0);assert.equal(h.timers.size,0);
});
test('native notification failure is retriable and no notification downloads or installs',async()=>{
  const h=harness();h.fail(true);const monitor=h.start();await flush();assert.equal(h.toasts.length,0);assert.equal(h.storage.size,0);
  h.fail(false);await monitor.check();assert.equal(h.toasts.length,1);assert(h.calls.every(c=>c==='update_status'));monitor.stop();
});
test('late background status cannot replace a newer installed/current foreground result',async()=>{
  const h=harness();h.hold();const monitor=h.start();
  publishUpdate({...h.state,available:false,phase:'updated'});h.resolve();await flush();
  assert.equal(h.toasts.length,0);assert.equal(getUpdateNotice()?.phase,'updated');monitor.stop();
});
test('notice has no credentials, disappears when current, rejects malformed versions',()=>{
  const h=harness();publishUpdate(h.state);assert(visibleUpdate(getUpdateNotice()));
  assert(!JSON.stringify(getUpdateNotice()).includes('private-confirmation'));
  for(const patch of [{available:false},{phase:'installing'},{available_version:'<unexpected>'},{available_version:h.state.installed_version}]){
    publishUpdate({...h.state,...patch});assert.equal(visibleUpdate(getUpdateNotice()),false);
  }
});
test('update deep link focuses only the enabled primary action without scrolling external ancestors',()=>{
  let scroll=0,focus=0,native=0;
  const button={closest:()=>null,scrollIntoView:()=>scroll++,focus:()=>focus++} as unknown as HTMLElement;
  const root={querySelector:(selector:string)=>{assert(selector.includes(':not(:disabled)'));return button;}} as unknown as HTMLElement;
  assert(focusUpdatePrimary(root,[{Root:{Element:button,BTakeFocus:()=>{native++;return true;}}}]));
  assert.equal(scroll,0);assert.equal(native,1);assert.equal(focus,0);
  assert(focusUpdatePrimary(root,[]));assert.equal(focus,1);
  assert.equal(focusUpdatePrimary({querySelector:()=>null} as any,[]),false);
});
test('three native sections and separate Updates replace the old sidebar',()=>{
  const layout=readFileSync(new URL('../../src/CollectionStudio.tsx',import.meta.url),'utf8');
  assert(layout.includes("['collection','add','settings']"));
  assert(layout.includes('<UpdatesPanel'));
  const theme=readFileSync(new URL('../../src/theme.ts',import.meta.url),'utf8');
  assert(!theme.includes('das-nav-last'));assert(!theme.includes('margin-top:auto'));
  const entry=readFileSync(new URL('../../src/index.tsx',import.meta.url),'utf8');
  assert(entry.includes('startUpdateNotifications'));assert(entry.includes('updates?.stop()'));
  assert(entry.includes('routerHook.addRoute(UPDATES_ROUTE'));assert(entry.includes('openUpdates={openUpdates}'));
});

test('public notices need no GitHub authorization',async()=>{
  const h=harness();const monitor=h.start();await flush();assert.equal(h.toasts.length,1);monitor.stop();
});
