import {useEffect,useMemo,useRef,useState,type MutableRefObject} from 'react';
import {ReorderableList,getGamepadNavigationTrees,type ReorderableEntry} from '@decky/ui';
import {takeContentNativeFocus} from './focus';
import {tr,errorText} from './i18n';
import type {StudioClient} from './types';

type Row={appid:number;name:string};
type Snapshot={revision:string;items:Row[]};

/** Decky's own list owns X, arrows, Back and the compression animation. */
export function CollectionOrder({client,save,onPending,leave,random}:{client:StudioClient;save:(ids:number[],revision:string)=>Promise<boolean>;onPending:(busy:boolean)=>void;leave:MutableRefObject<(()=>boolean)|null>;random:boolean}){
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[error,setError]=useState(''),[saved,setSaved]=useState(false),[pending,setPending]=useState(false);
 const region=useRef<HTMLDivElement>(null),alive=useRef(true),saving=useRef(false),entered=useRef(false),base=useRef<number[]>([]),token=useRef(''),failed=useRef(false);
 useEffect(()=>{alive.current=true;let live=true;void client<Snapshot>('workspace_order').then(value=>{
  if(!live)return;base.current=value.items.map(g=>g.appid);token.current=value.revision;setSnapshot(value);
 }).catch(e=>{if(live)setError(errorText(String(e)));});return()=>{live=false;alive.current=false;};},[client]);
 // Stable across status polling and save progress: the native list keeps its draft.
 const entries=useMemo(()=>snapshot?.items.map((g,position)=>({label:<span data-order-id={g.appid}>{g.name}</span>,data:g.appid,position}))||[],[snapshot]);
 useEffect(()=>{if(!snapshot||!region.current||entered.current)return;entered.current=true;const frame=requestAnimationFrame(()=>{
  const label=region.current?.querySelector<HTMLElement>('[data-order-id]');
  if(label&&region.current&&!takeContentNativeFocus(label,region.current,getGamepadNavigationTrees()||[]))label.closest<HTMLElement>('[tabindex]')?.focus({preventScroll:true});
 });return()=>cancelAnimationFrame(frame);},[snapshot]);
 const onSave=async(rows:ReorderableEntry<number>[])=>{
  if(saving.current||!snapshot)return;
  const ids=rows.map(row=>row.data!);if(ids.every((id,index)=>id===base.current[index]))return;
  saving.current=true;failed.current=false;onPending(true);setPending(true);setSaved(false);
  try{if(await save(ids,token.current)){base.current=ids;if(alive.current){setSaved(true);setError('');}
   // Refresh the optimistic token without changing the native list's entries.
   const current=await client<Snapshot>('workspace_order');if(current.items.length!==ids.length||current.items.some((g,i)=>g.appid!==ids[i]))throw Error('collection_order_changed');token.current=current.revision;
  }else failed.current=true;}catch(e){failed.current=true;if(alive.current)setError(errorText(String(e)));}finally{saving.current=false;onPending(false);if(alive.current)setPending(false);}
 };
 leave.current=()=>{if(saving.current)return true;if(failed.current)return false;const ordered=[...entries].sort((a,b)=>a.position-b.position);if(ordered.some((row,i)=>row.data!==base.current[i])){void onSave(ordered);return true;}return false;};
 useEffect(()=>()=>{leave.current=null;},[leave]);
 return <div className="collection-order" data-ui-part="collection-order" ref={region} aria-busy={pending}>
  <div className="collection-order-heading"><h2>{tr('Reorder my collection','Réorganiser ma collection')}</h2><span role="status">{pending?tr('Saving…','Enregistrement…'):saved?tr('Order saved','Ordre enregistré'):!snapshot&&!error?tr('Loading…','Chargement…'):''}</span></div>
  {random&&<p>{tr('Shuffle remains enabled in Settings.','L’ordre aléatoire reste activé dans Réglages.')}</p>}
  {error&&<p role="alert">{error}</p>}
  {snapshot&&<ReorderableList<number> entries={entries} onSave={rows=>void onSave(rows)} disableReordering={pending||entries.length<2} animate/>}
 </div>;
}
