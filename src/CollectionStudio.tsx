import {useCallback,useEffect,useRef,useState,type ReactNode,type CSSProperties} from 'react';
import {DialogBody,DialogControlsSection,Field,Dropdown,Menu,MenuItem,showContextMenu,useQuickAccessVisible,DialogButton,DropdownItem,Focusable,ScrollPanel,Tabs,TextField,ToggleField,SliderField,getGamepadNavigationTrees,GamepadButton,NavEntryPositionPreferences,Navigation,type GamepadEvent} from '@decky/ui';
import {client as defaultClient} from './client';
import {Player,useStudio} from './StudioRuntime';
import {SettingsPanels} from './SettingsPanels';
import {AdvancedPanel} from './AdvancedPanel';
import {AssistancePanel} from './AssistancePanel';
import {ArtworkImage,preloadArtwork} from './ArtworkImage';
import {safeImage,type Tab} from './model';
import {collectionStep,collectionActivity,installedSceneCount,type CollectionTab} from './collectionModel';
import {errorText,language,stageText,tr,useLanguage} from './i18n';
import {takeNativeFocus,revealInContent,crossDetailColumn} from './focus';
import {UpdatesPanel} from './UpdatesPanel';
import {PluginUpdateNotice} from './PluginUpdateNotice';
import {useUpdateNotice,visibleUpdate} from './update_notice';
import {QuickAction,QuickStatus,QuickZone,QUICK_CONTROL_CSS} from './QuickControls';
import {RecoveryCard} from './RecoveryCard';
import {OPEN_ATTENTION_EVENT,collectionRecoveryRoute,type RecoveryAction} from './recovery';
import type {StudioAsset,StudioClient,StudioGame,StudioPage,StudioPreview,StudioState} from './types';
import {COLLECTION_CSS} from './collectionTheme';
import {CollectionOrder} from './CollectionOrder';
import {GameArtworkPreview} from './GameArtworkPreview';
import {CandidateArtwork} from './CandidateArtwork';
import {jsauxVisible,jsauxPreparationBusy} from './types';
import {faceplateNeedsCorrection,faceplateIssue,faceplateTaskResolved,faceplateEffectiveMode} from './faceplateUX';
import {FaceplateRecovery} from './FaceplateRecovery';
import {FaceplatePreparationStatus} from './FaceplatePreparationStatus';

const names=()=>({collection:tr('My collection','Ma collection'),add:tr('Add games','Ajouter des jeux'),settings:tr('Settings','Réglages')});
const updateLabel=(s:StudioState)=>s.installation.installed?tr('Update my collection','Mettre à jour ma collection'):tr('Create my screensaver','Créer mon écran de veille');
const labels=(s:StudioState)=>({choose:tr('Add games','Ajouter des jeux'),prepare:updateLabel(s),
  activity:tr('View progress','Voir la progression'),resume:tr('Resume','Reprendre'),attention:tr('See games to fix','Voir les jeux à corriger'),
  faceplate:updateLabel(s),install:updateLabel(s),preview:tr('See the result','Voir le résultat')});
const skippedGame=(g:StudioGame)=>g.status==='skipped'||!g.media?.tv&&(g.status==='missing'||g.error==='animation_missing'||g.problem?.code==='animation_missing');
const skippedCount=(s:StudioState)=>Number((s.workspace as {skipped_count?:number}|undefined)?.skipped_count||0);

export function CollectionQuick({open,onOpenUpdates,client=defaultClient}:{open:(tab:Tab)=>void;onOpenUpdates?:()=>void;client?:StudioClient}){
  useLanguage();const visible=useQuickAccessVisible();const {state,error}=useStudio(client,true,visible);const update=useUpdateNotice();
  const target=state?collectionStep(state):'choose';
  return <div id="das-compact-root" className="das-quick"><style>{QUICK_CONTROL_CSS}</style>{visibleUpdate(update)?<QuickZone zone="updates"><PluginUpdateNotice quick onOpen={onOpenUpdates??(()=>{Navigation.Navigate('/decky-animated-screensaver/updates');Navigation.CloseSideMenus();})}/></QuickZone>:null}<QuickZone zone="control"><QuickStatus tone={error?'error':target==='preview'?'good':'waiting'}>
    <strong>{state?target==='activity'?tr('Collection update in progress','Mise à jour de la collection en cours'):target==='resume'?tr('Preparation paused','Préparation suspendue'):target==='preview'?tr('Collection installed','Collection installée'):state.installation.installed?tr('Collection changes to apply','Modifications de collection à appliquer'):tr('Create your first screensaver','Créez votre premier écran de veille'):tr('Loading…','Chargement…')}</strong>
    {error&&<p>{error}</p>}
    {state&&(jsauxVisible(state.jsaux)||state.updates?.available||skippedCount(state)>0)&&<div className="das-quick-meta">
      {jsauxVisible(state.jsaux)&&<span>Faceplate JSAUX · {state.jsaux.detected?tr('connected','connectée'):tr('disconnected','débranchée')}</span>}
      {skippedCount(state)>0&&<span>{tr(`${skippedCount(state)} without animation`,`${skippedCount(state)} sans animation`)}</span>}
    </div>}
  </QuickStatus><QuickAction disabled={!state} onClick={()=>open(['activity','resume'].includes(target)?'preparation':'library')}>{['activity','resume'].includes(target)?tr('View progress','Voir la progression'):tr('Open my collection','Ouvrir ma collection')}</QuickAction></QuickZone>
    <QuickZone zone="collection"><QuickAction onClick={()=>open('settings')}>{tr('Add games','Ajouter des jeux')}</QuickAction></QuickZone>
  </div>;
}

type Choices=Partial<Record<'animation'|'still_tv'|'cover'|'logo'|'panel',number>>;
type Draft={choices:Choices;crop:{mode:string;x:number;y:number};excluded:boolean;collection_member:boolean;still_mode:string;branding:{mode:string;position:string};cover_position:string;faceplate_crop:{x:number;y:number}};
type Context={query:string;filter:string;page:number;appid:number;scroll:number;source:'installed'|'online'|'top'};
const EMPTY:Context={query:'',filter:'collection',page:0,appid:0,scroll:0,source:'installed'};
const pageScope=(tab:string,ctx:Context,layout:string)=>JSON.stringify([layout,tab,ctx.source,ctx.filter,ctx.query.trim(),layout==='list'?0:ctx.page]);
type DiscoveryPage={items:StudioGame[];total:number;at?:number;stale?:boolean};

export function CollectionStudio({initial='collection',focusUpdates=false,initialAttention=false,client=defaultClient}:{initial?:CollectionTab|'preview'|'activity';focusUpdates?:boolean;initialAttention?:boolean;client?:StudioClient}){
  useLanguage();const {state:s,saving,error,failure,run,clearError,refresh}=useStudio(client);
  const [tab,setTab]=useState<CollectionTab>(()=>{let destination='';try{destination=sessionStorage.getItem('das-collection-launch')||'';sessionStorage.removeItem('das-collection-launch');}catch{}return focusUpdates||initial==='settings'?'settings':initial==='add'||destination==='add'?'add':'collection';});
  const [sub,setSub]=useState(focusUpdates?'updates':initial==='activity'?'activity':'');
  const [updateFocusRequest,setUpdateFocusRequest]=useState(focusUpdates?1:0);
  const [ctx,setCtx]=useState<Context>({...EMPTY,filter:initialAttention?'attention':tab==='add'?'installed':'collection'});
  const [page,setPage]=useState<StudioPage>({items:[],total:0,page:0,page_size:8});
  const libraryPages=useRef(new Map<string,StudioPage>());
  const [game,setGame]=useState<StudioGame|null>(null),[draft,setDraft]=useState<Draft|null>(null),[dirty,setDirty]=useState(false);
  const [assets,setAssets]=useState<StudioAsset[]|null>(null),[role,setRole]=useState<keyof Choices>('animation');
  const [candidateLimit,setCandidateLimit]=useState(8);
  const [activeAsset,setActiveAsset]=useState<number|null>(null);
  const [wideDetail,setWideDetail]=useState(()=>window.matchMedia('(min-width:1101px)').matches);
  useEffect(()=>{const media=window.matchMedia('(min-width:1101px)'),update=()=>setWideDetail(media.matches);update();media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  const [selected,setSelected]=useState<Partial<Record<keyof Choices,StudioAsset>>>({});
  const [preview,setPreview]=useState<StudioPreview|null>(null),[confirm,setConfirm]=useState<'draft'|'prepare'|'install'|'faceplate'|null>(null);
  const [prepareMode,setPrepareMode]=useState<'missing'|'all'>('missing');
  const [savedChange,setSavedChange]=useState(false);
  const [managementConfirm,setManagementConfirm]=useState(false);
  const orderSaving=useRef(false),orderLeave=useRef<(()=>boolean)|null>(null);
  const [selectionOverrides,setSelectionOverrides]=useState<Record<number,boolean>>({}),[selectionBusy,setSelectionBusy]=useState(false);
  const selectionIntents=useRef(new Map<number,{selected:boolean;ticket:number}>()),selectionQueue=useRef<Promise<void>>(Promise.resolve()),selectionTicket=useRef(0),selectionWrites=useRef(0);
  const selectingAll=useRef(false),loadedSelectionScope=useRef(''),discoverySelection=useRef<number[]>([]);
  const [selectionRevision,setSelectionRevision]=useState(0);
  const selectionScope=JSON.stringify([ctx.source,ctx.query.trim()]);
  const [loading,setLoading]=useState(false),[rankAt,setRankAt]=useState(0),[stale,setStale]=useState(false),[artLoading,setArtLoading]=useState(false);
  const candidatesCache=useRef(new Map<string,{at:number;rows:StudioAsset[]}>());
  const candidateRequests=useRef(new Map<string,Promise<StudioAsset[]>>());
  const getCandidates=(appid:number,role:keyof Choices)=>{
    const key=appid+':'+role,cached=candidatesCache.current.get(key),pending=candidateRequests.current.get(key);
    if(cached&&Date.now()-cached.at<300000)return Promise.resolve(cached.rows);if(pending)return pending;
    const request=client<StudioAsset[]>('browse_candidates',{appid,role}).then(rows=>{
      if(alive.current){candidatesCache.current.set(key,{at:Date.now(),rows});while(candidatesCache.current.size>12)candidatesCache.current.delete(candidatesCache.current.keys().next().value!);}return rows;
    }).finally(()=>candidateRequests.current.delete(key));candidateRequests.current.set(key,request);return request;
  };
  const [notice,setNotice]=useState('');
  useEffect(()=>{if(s&&!jsauxVisible(s.jsaux)){if(sub==='jsaux'){setSub('');setTab('settings');focusTarget.current='settings-playback';}if(assets&&role==='panel'){seq.current++;setArtLoading(false);setAssets(null);focusTarget.current='pick-animation';}}},[s?.jsaux?.detected,s?.jsaux?.compatible,sub,assets,role]);
  const root=useRef<HTMLDivElement>(null),body=useRef<HTMLDivElement>(null),seq=useRef(0),loadSerial=useRef(0),alive=useRef(true),scanned=useRef(false),auto=useRef(false);
  const contexts=useRef<Record<CollectionTab,Context>>({collection:{...EMPTY},add:{...EMPTY,filter:'installed'},settings:{...EMPTY}});
  // Add membership is reconciled locally; count changes must not refetch and
  // reflow the same discovery page on every selection.
  const membershipRevision=tab==='add'?'':`${s?.workspace?.draft_count}|${s?.workspace?.pending_count}|${s?.workspace?.skipped_count}`;
  const queryKey=`${ctx.page}|${ctx.query}|${ctx.filter}|${membershipRevision}|${selectionRevision}|${s?.options.static_fallback}|${s?.job.completed}|${s?.job.state}`;
  const listSentinel=useRef<HTMLDivElement>(null),listBusy=useRef(false);
  const focusTarget=useRef(''),entered=useRef(false);
  const nested=!!(game||sub||preview||confirm||assets||managementConfirm);
  const focus=(key:string)=>{focusTarget.current=key;};
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;seq.current++;void client('close_preview').catch(()=>{});};},[client]);
  const load=useCallback(async()=>{
    const id=++loadSerial.current;const q=ctx.query.trim();
    if(q.length>0&&q.length<3){setLoading(false);setNotice('');setPage({items:[],total:0,page:0,page_size:8});return;}
    setLoading(true);
    try{
      let v:StudioPage;
      const list=s?.workspace?.layout==='list';
      const size=list?10:s?.workspace?.layout==='compact'?10:8;
      if(tab==='add'&&ctx.source!=='installed'){
        if(ctx.source==='online'&&q.length<3){setPage({items:[],total:0,page:0,page_size:size});return;}
        const result=await client<DiscoveryPage>(ctx.source==='top'?'browse_top':'browse_search',{query:q});
        if(!alive.current||id!==loadSerial.current)return;
        const rows=result.items.filter(g=>!q||g.name.toLocaleLowerCase().includes(q.toLocaleLowerCase()));
        discoverySelection.current=rows.map(g=>g.appid);
        const p=Math.min(ctx.page,Math.max(0,Math.ceil(rows.length/size)-1));
        v={items:rows.slice(list?0:p*size,(p+1)*size),total:rows.length,page:p,page_size:size};setRankAt(result.at||0);setStale(Boolean(result.stale));
      }else if(list){v=await client<StudioPage>('workspace_library',{page:ctx.page,page_size:10,limit:(ctx.page+1)*10,query:q,filter:tab==='add'?'installed':ctx.filter});
      }else v=await client<StudioPage>('workspace_library',{page:ctx.page,page_size:size,query:q,filter:tab==='add'?'installed':ctx.filter});
      if(alive.current&&id===loadSerial.current){
        if(tab==='add')loadedSelectionScope.current=JSON.stringify([ctx.source,q]);
        libraryPages.current.set(pageScope(tab,ctx,s?.workspace?.layout||'comfort'),v);while(libraryPages.current.size>12)libraryPages.current.delete(libraryPages.current.keys().next().value!);
        setPage(v);setNotice('');
      }
    }catch(e){if(alive.current&&id===loadSerial.current){setPage({items:[],total:0,page:0,page_size:8});setRankAt(0);setNotice(errorText(String(e)));}}
    finally{if(alive.current&&id===loadSerial.current)setLoading(false);}
  },[client,ctx.page,ctx.query,ctx.filter,ctx.source,tab,s?.workspace?.layout]);
  useEffect(()=>{if(tab==='settings')return;loadSerial.current++;const timer=setTimeout(()=>void load(),tab==='add'&&ctx.source==='online'?400:180);return()=>clearTimeout(timer);},[load,queryKey,tab]);
  useEffect(()=>{if(!entered.current&&!nested&&s){entered.current=true;if(!focusTarget.current)focusTarget.current=tab==='settings'?'settings-playback':tab==='add'?'prepare-selection':'primary';}},[Boolean(s),page.items.length,nested]);
  useEffect(()=>{if(s&&!s.game_count&&!scanned.current){scanned.current=true;void run('workspace_scan').then(()=>load());}},[s,run,load]);
  useEffect(()=>{
    const key=focusTarget.current;if(!key||!root.current)return;
    const region=root.current;let frame=0,tries=0;
    const move=()=>{
      const target=key==='first-selection'?region.querySelector<HTMLElement>('[data-collection-focus^=select-game-]'):Array.from(region.querySelectorAll<HTMLElement>('[data-collection-focus]')).find(e=>e.dataset.collectionFocus===key);
      if(!target||!target.getClientRects().length){if(++tries<8)frame=requestAnimationFrame(move);return;}
      try{if(!takeNativeFocus(target,getGamepadNavigationTrees()||[]))target.focus({preventScroll:true});}catch{target.focus({preventScroll:true});}
      revealInContent(target);focusTarget.current='';
    };frame=requestAnimationFrame(move);return()=>cancelAnimationFrame(frame);
  },[game,assets,confirm,managementConfirm,sub,tab,preview,page.items,s?.jsaux?.reason,s?.jsaux?.detected,s?.workspace?.selection_undo?.token]);
  const scrollOwner=()=>body.current?.closest<HTMLElement>('[role="tabpanel"]')??Array.from(body.current?.querySelectorAll<HTMLElement>('div')||[]).find(e=>['auto','scroll'].includes(getComputedStyle(e).overflowY));
  useEffect(()=>{
    if(s?.workspace?.layout!=='list'||nested||loading||page.items.length>=page.total)return;
    const owner=scrollOwner();if(!owner)return;
    const more=()=>{const sentinel=listSentinel.current;if(!sentinel||listBusy.current||owner.scrollTop<8)return;const box=sentinel.getBoundingClientRect(),frame=owner.getBoundingClientRect();if(box.top<=frame.bottom+60&&box.bottom>=frame.top){listBusy.current=true;setCtx(current=>({...current,page:current.page+1}));}};
    listBusy.current=false;owner.addEventListener('scroll',more,{passive:true});return()=>owner.removeEventListener('scroll',more);
  },[s?.workspace?.layout,nested,loading,page.items.length,page.total]);
  const remember=()=>{contexts.current[tab]={...ctx,scroll:scrollOwner()?.scrollTop||0};};
  const previousView=useRef({tab,nested:false});
  useEffect(()=>{
    const previous=previousView.current;previousView.current={tab,nested};
    if(nested)return;
    const returning=previous.nested||previous.tab!==tab;
    if(s?.workspace?.layout==='list'&&ctx.page>0&&!returning)return;
    const frame=requestAnimationFrame(()=>{const owner=scrollOwner();if(owner)owner.scrollTop=previous.nested?contexts.current[tab].scroll:ctx.scroll;});return()=>cancelAnimationFrame(frame);
  },[tab,nested,page.page,s?.workspace?.layout]);
  const closePreview=()=>{seq.current++;setPreview(null);void client('close_preview').catch(()=>{});};
  useEffect(()=>{const show=()=>{setTab('collection');setSub('');setCtx({...EMPTY,filter:'attention'});};window.addEventListener(OPEN_ATTENTION_EVENT,show);return()=>window.removeEventListener(OPEN_ATTENTION_EVENT,show);},[]);
  const cachedPageFor=(next:CollectionTab,context:Context)=>{
    const layout=s?.workspace?.layout||'comfort',size=layout==='list'?10:layout==='compact'?10:8;
    const key=pageScope(next,context,layout),exact=libraryPages.current.get(key);if(exact)return exact;
    // First-page artwork is also valid after a density change. Keep its known
    // prefix visible while fetching the new page size; never reuse another scope.
    if(context.page===0){const scope=JSON.stringify(JSON.parse(key).slice(1,5));
      for(const [other,cached] of libraryPages.current){const parts=JSON.parse(other);if(JSON.stringify(parts.slice(1,5))===scope&&(parts[0]==='list'||cached.page===0))return {...cached,items:cached.items.slice(0,size),page:0,page_size:size};}
    }
    return {items:[],total:0,page:0,page_size:size};
  };
  const navigate=(next:CollectionTab)=>{
    if(next===tab)return;
    if(dirty){setConfirm('draft');return;}
    remember();loadSerial.current++;clearError();closePreview();setGame(null);setAssets(null);setSub('');setTab(next);setCtx({...contexts.current[next]});setPage(cachedPageFor(next,contexts.current[next]));setLoading(next!=='settings');focusTarget.current='';
  };
  const back=()=>{
    if(nested)seq.current++;
    if(sub==='reorder'){if(orderSaving.current||orderLeave.current?.())return true;setSub('');loadSerial.current++;libraryPages.current.clear();void load();focus('manage-collection');return true;}
    if(managementConfirm){setManagementConfirm(false);focus('manage-collection');return true;}
    if(confirm){focus(confirm==='faceplate'?'prepare-faceplate':confirm==='draft'?'save':tab==='add'?'prepare-selection':'primary');setConfirm(null);return true;}
    if(assets){setAssets(null);focus('pick-'+role);return true;}
    if(preview){closePreview();focus(game?'preview':sub==='activity'?'preview-installed':'primary');return true;}
    if(game){if(dirty){setConfirm('draft');return true;}setGame(null);setDraft(null);focus((tab==='add'?'select-game-':'game-')+game.appid);return true;}
    if(sub){setSub('');focus(sub==='jsaux'&&tab==='collection'?(s&&faceplateNeedsCorrection(s)?'jsaux':'primary'):'settings-'+sub);return true;}
    return false;
  };
  const cancel=(event:{preventDefault:()=>void;stopPropagation:()=>void})=>{
    event.preventDefault();event.stopPropagation();
    if(!back())Navigation.NavigateBack();
  };
  const crossColumn=(direction:-1|1,element:Element|null)=>{
    const region=root.current?.querySelector<HTMLElement>('.collection-detail');if(!region)return false;
    const active=element&&region.contains(element)&&element!==region?element:Array.from(region.querySelectorAll('.gpfocus')).pop()||document.activeElement;
    return crossDetailColumn(region,active,direction,getGamepadNavigationTrees()||[]);
  };
  const detailDirection=(event:GamepadEvent)=>{
    const button=event.detail?.button;if(button!==GamepadButton.DIR_LEFT&&button!==GamepadButton.DIR_RIGHT)return;
    if(crossColumn(button===GamepadButton.DIR_LEFT?-1:1,document.activeElement)){event.preventDefault();event.stopPropagation();}
  };
  const openGame=async(g:StudioGame)=>{
    remember();const id=++seq.current;
    const value=await run<StudioGame>(tab==='add'&&ctx.source!=='installed'?'browse_open':'workspace_details',{appid:g.appid});
    if(!value||id!==seq.current||!alive.current)return;
    setGame({...g,...value});setDraft({choices:{},crop:{mode:value.crop?.mode||'inherit',x:value.crop?.x??50,y:value.crop?.y??50},excluded:value.collection_member?Boolean(value.excluded):false,collection_member:true,still_mode:value.still_mode||'inherit',branding:value.branding||{mode:'inherit',position:'inherit'},cover_position:value.cover_position||s?.options.cover_position||'bottom-right',faceplate_crop:value.faceplate_crop||{x:50,y:50}});
    setDirty(false);setSelected({...(value.asset?{[value.asset.animated?'animation':'still_tv']:value.asset}:{}),...(value.cover_asset?{cover:value.cover_asset}:{}),...(value.logo_asset?{logo:value.logo_asset}:{})});focus('screensaver-inclusion');
    if(s?.key_configured)void getCandidates(g.appid,'animation').then(rows=>{if(alive.current&&id===seq.current)preloadArtwork(rows.map(a=>a.thumb),()=>alive.current&&id===seq.current);}).catch(()=>{});
  };
  const toggleSelection=(g:StudioGame)=>{
    if(selectingAll.current)return;
    const selected=!(selectionIntents.current.get(g.appid)?.selected??Boolean(g.collection_member&&!g.excluded));
    const ticket=++selectionTicket.current;selectionIntents.current.set(g.appid,{selected,ticket});
    setSelectionOverrides(current=>({...current,[g.appid]:selected}));selectionWrites.current++;setSelectionBusy(true);loadSerial.current++;setLoading(false);
    selectionQueue.current=selectionQueue.current.then(async()=>{
      if(!alive.current)return;
      try{
        if(!g.installed){const opened=await run('browse_open',{appid:g.appid});if(!opened)return;}
        const result=await run('workspace_draft',{appid:g.appid,patch:{collection_member:selected,excluded:false},reconcile_membership:true});
        if(result&&alive.current){
          const update=(row:StudioGame)=>row.appid===g.appid?{...row,collection_member:selected,excluded:false,workspace_draft:result.workspace?.pending_ids?.includes(g.appid)||false}:row;
          setPage(current=>({...current,items:current.items.map(update)}));
          for(const [key,cached] of libraryPages.current){if(JSON.parse(key)[1]==='collection')libraryPages.current.delete(key);else libraryPages.current.set(key,{...cached,items:cached.items.map(update)});}
        }
      }finally{
        if(selectionIntents.current.get(g.appid)?.ticket===ticket){selectionIntents.current.delete(g.appid);if(alive.current)setSelectionOverrides(current=>{const next={...current};delete next[g.appid];return next;});}
        selectionWrites.current--;if(alive.current)setSelectionBusy(selectionWrites.current>0);
      }
    });
  };
  const save=async()=>{
    if(!game||!draft)return;
    const fromAdd=tab==='add';
    const value=await run('workspace_draft',{appid:game.appid,patch:draft});
    if(value){setDirty(false);setSavedChange(true);setGame(null);setConfirm(null);setDraft(null);setSub('');if(fromAdd){focus('select-game-'+game.appid);await load();}else{setTab('collection');setCtx({...contexts.current.collection,page:0});focus('primary');await load();}}
  };
  const browse=async(next:keyof Choices)=>{
    if(!game)return;const id=++seq.current;setRole(next);setAssets([]);setCandidateLimit(8);setActiveAsset(null);setArtLoading(true);
    try{const v=await getCandidates(game.appid,next);
      if(v&&alive.current&&id===seq.current){setAssets(v);focus('asset-'+(v[0]?.id||'none'));}
    }catch(e){if(alive.current&&id===seq.current)setNotice(errorText(String(e)));}
    finally{if(alive.current&&id===seq.current)setArtLoading(false);}
  };
  const showPreview=async(installed=false)=>{
    if(game&&dirty){setConfirm('draft');return;}
    const id=++seq.current;const v=await run<StudioPreview>(installed?'preview_installed':'preview',game?{appid:game.appid}:{});
    if(v&&alive.current&&id===seq.current){setPreview(v);focus('back');}
    else if(v)void client('close_preview').catch(()=>{});
  };
  useEffect(()=>{if(initial==='preview'&&s?.installation.installed&&!auto.current){auto.current=true;void showPreview(true);}},[initial,s?.installation.installed]);
  const setSection=(id:string)=>{if(dirty){setConfirm('draft');return;}setSub(id);setGame(null);setAssets(null);closePreview();focus(id==='updates'?'':'back');if(id==='updates')setUpdateFocusRequest(value=>value+1);};
  const recover=async(action:RecoveryAction)=>{
    clearError();if(!s)return;
    // Connection discovery is read-only; all other recovery choices navigate.
    const refreshed=action==='connection'?await run<StudioState>('jsaux_refresh',{force:true}):undefined;
    const destination=collectionRecoveryRoute(action,refreshed||s);
    if(destination==='collection'||destination==='attention'){
      if(dirty){setConfirm('draft');return;}
      closePreview();setSub('');setGame(null);setDraft(null);setAssets(null);setTab('collection');setCtx({...EMPTY,filter:destination==='attention'?'attention':'collection'});focus('primary');
    }else setSection(destination);
  };
  const beginPreparation=(mode:'missing'|'all'='missing')=>{
    if(!s||selectionWrites.current)return;if(!s.key_configured||!s.media_tools.available){setSection('setup');return;}
    setPrepareMode(mode);setConfirm('prepare');focus('confirm');
  };
  const primary=()=>{
    if(!s)return;
    const step=collectionStep(s);
    if(step==='choose'){navigate('add');return;}
    if(step==='activity'){setSection('activity');return;}
    if(step==='resume'){void run('resume',{language:language()});setSection('activity');return;}
    if(step==='attention'){if(ctx.filter==='attention'){beginPreparation();return;}setCtx({...ctx,page:0,query:'',filter:'attention'});setTab('collection');return;}
    if(step==='preview'){void showPreview(true);return;}
    if(step==='prepare'){beginPreparation();return;}
    setConfirm('install');focus('confirm');
  };
  const execute=async()=>{
    const kind=confirm;if(!['prepare','install','faceplate'].includes(kind||''))return;
    const preparation=kind==='prepare';
    const value=await run(preparation?'workspace_prepare':'workspace_install',{confirm:true,language:language(),...(preparation?{mode:prepareMode}:{}),...(kind==='faceplate'?{repair_faceplate:true}:{})});
    if(value){setSavedChange(false);setConfirm(null);setSection('activity');}
  };
  const mutate=(patch:Partial<Draft>)=>{if(draft){setDraft({...draft,...patch});setDirty(true);}};
  const choose=(asset:StudioAsset)=>{
    if(!draft)return;const choices={...draft.choices,[role]:asset.id},visual={...selected,[role]:asset};
    if(role==='animation'){delete choices.still_tv;delete visual.still_tv;}
    if(role==='still_tv'){delete choices.animation;delete visual.animation;}
    setDraft({...draft,choices,...(role==='still_tv'?{still_mode:'motion'}:role==='animation'?{still_mode:'inherit'}:{})});
    setSelected(visual);setDirty(true);if(role==='panel'){focus('use-panel');}else{setAssets(null);focus('pick-'+role);}
  };
  const actionButton=(text:string,callback:()=>void,key:string,disabled=false)=><DialogButton className="collection-action" data-collection-focus={key} disabled={disabled} onClick={callback}>{text}</DialogButton>;
  const changeLayout=(value:string)=>{if(value===s?.workspace?.layout)return;loadSerial.current++;setCtx(current=>({...current,page:0,scroll:0}));setPage({items:[],total:0,page:0,page_size:value==='list'?10:8});void run('workspace_preferences',{patch:{layout:value}});};
  const toolbarControl=(label:string,control:ReactNode,extra='')=><div className={'collection-toolbar-field '+extra}><span className="collection-toolbar-label">{label}</span>{control}</div>;
  const viewPicker=()=>s&&toolbarControl(tr('View','Présentation'),<Dropdown menuLabel={tr('View','Présentation')} selectedOption={s.workspace?.layout||'comfort'} disabled={saving}
    rgOptions={[{data:'comfort',label:tr('Comfort · 4 columns','Confort · 4 colonnes')},{data:'compact',label:tr('Compact · 5 columns','Compact · 5 colonnes')},{data:'list',label:tr('List','Liste')}]}
    onChange={option=>{if(!saving)changeLayout(option.data);}}/>, 'collection-view-picker');
  const searchField=(label:string)=>toolbarControl(label,<TextField aria-label={label} value={ctx.query} onChange={e=>{loadSerial.current++;setCtx({...ctx,query:e.target.value,page:0,scroll:0});}}/>);
  const sourcePicker=()=>toolbarControl(tr('Game source','Source des jeux'),<Dropdown menuLabel={tr('Game source','Source des jeux')} selectedOption={ctx.source} rgOptions={[{data:'installed',label:tr('Installed games','Mes jeux installés')},{data:'online',label:tr('Search online','Recherche en ligne')},{data:'top',label:'Top Steam'}]} onChange={o=>{loadSerial.current++;setCtx({...ctx,source:o.data,query:'',page:0,scroll:0});setPage({...page,items:[],total:0});}}/>);
  const filterPicker=()=>toolbarControl(tr('Show','Afficher'),<Dropdown menuLabel={tr('Show','Afficher')} selectedOption={ctx.filter} rgOptions={[['collection',tr('All my games','Tous mes jeux')],['attention',tr('Needs attention','À corriger')],['pending',tr('To prepare','À préparer')],['included',tr('Displayed games','Jeux affichés')]].map(([data,label])=>({data,label}))} onChange={o=>setCtx({...ctx,filter:o.data,page:0})}/>);
  const backButton=()=>actionButton(tr('Back','Retour'),()=>back(),'back');
  const step=s?collectionStep(s):'choose';
  const installedCount=s?installedSceneCount(s):undefined;
  const selectionCount=s?.workspace?.included_count||0;
  const changes=Math.max(s?.workspace?.draft_count||0,s?.workspace?.pending_count||0,savedChange?1:0);
  const activity=s?collectionActivity(s):'idle';
  const interruptedMedia=(s?.job.state==='paused'||s?.workspace?.task.state==='paused')&&['worker_signal','runtime_isolation'].includes(s?.job.error||s?.workspace?.task.error||'');
  const skippedVisualGames=s?.workspace?.skipped_visual_count??s?.job.skipped_count??0;
  const faceplateRepair=Boolean(s&&faceplateIssue(s));
  const batchCapacity=Boolean(s&&['sync-capacity','capacity'].includes(faceplateIssue(s)?.kind||''));
  const recoveredFaceplate=Boolean(s&&faceplateTaskResolved(s));
  const showPanelResult=jsauxVisible(s?.jsaux);
  const tvLabels={prepared:tr('TV: artwork prepared','TV : visuels préparés'),installed:tr('TV: files installed','TV : fichiers installés'),unchanged:tr('TV: installed files unchanged','TV : fichiers installés inchangés'),empty:tr('TV: no files to install','TV : aucun fichier à installer')};
  const panelLabels={disabled:tr("Faceplate JSAUX: output disabled","Faceplate JSAUX : sortie désactivée"),unavailable:tr("Faceplate JSAUX: unavailable","Faceplate JSAUX : indisponible"),prepared:tr("Faceplate JSAUX: images prepared","Faceplate JSAUX : images préparées"),installed:tr("Faceplate JSAUX: included in installed collection","Faceplate JSAUX : incluse dans la collection installée"),repair_required:tr("Faceplate JSAUX: repair needed","Faceplate JSAUX : préparation incomplète")};
  const activityTitles={preparing:tr('Preparing your collection','Préparation de votre collection'),applying:tr('Installing your collection','Installation de votre collection'),paused:tr('Preparation paused','Préparation suspendue'),waiting_game:tr('Waiting for the game to close','En attente de la fermeture du jeu'),installed:tr('Collection installed','Collection installée'),unchanged:tr('Collection already up to date','Collection déjà à jour'),empty:tr('No games to install','Aucun jeu à installer'),finished:tr('Operation finished','Opération terminée'),partial:tr('Preparation incomplete','Préparation incomplète'),error:tr('Update not completed','Mise à jour non terminée'),cancelled:tr('Preparation cancelled','Préparation annulée'),idle:tr('No operation in progress','Aucune opération en cours')};
  async function bulkSelection(restore=false){
    const result=await run(restore?'workspace_undo_selection':'workspace_deselect_all',restore?{token:s?.workspace?.selection_undo?.token}:{});if(!result)return;
    loadSerial.current++;libraryPages.current.clear();setSelectionOverrides({});setCtx(current=>({...current,page:0}));await load();focus(restore?'clear-selection':'undo-selection');
  }
  const canSelectAll=tab==='add'&&!nested&&!loading&&!saving&&!selectionBusy&&page.total>0&&loadedSelectionScope.current===selectionScope
    &&!['activity','resume'].includes(step)&&!s?.workspace?.task.worker_active&&!s?.job.worker_active&&!jsauxPreparationBusy(s?.jsaux)&&s?.updates?.phase!=='installing';
  async function selectAllAvailable(){
    if(!canSelectAll||selectingAll.current||selectionWrites.current)return;
    selectingAll.current=true;setSelectionBusy(true);
    try{
      const result=await run('workspace_select_all',ctx.source==='installed'?{source:'installed',query:ctx.query.trim()}:{source:ctx.source,appids:discoverySelection.current});
      if(result&&alive.current){loadSerial.current++;libraryPages.current.clear();setSelectionOverrides({});setSelectionRevision(value=>value+1);}
    }finally{selectingAll.current=false;if(alive.current)setSelectionBusy(false);}
  }
  const selectAllButton=(event:GamepadEvent)=>{event.preventDefault();event.stopPropagation();if(!event.detail?.is_repeat)void selectAllAvailable();};
  async function deleteCollection(){
    const result=await run('workspace_delete_collection',{confirm:true});if(!result)return;
    setManagementConfirm(false);libraryPages.current.clear();loadSerial.current++;setPage({items:[],total:0,page:0,page_size:8});setSelectionOverrides({});setTab('add');setSub('');setCtx({...EMPTY,filter:'installed'});setNotice('');focus('first-selection');
  }
  function managementControls(){
    if(!s||step==='activity'||step==='resume')return null;
    const blocked=saving||selectionBusy||Boolean(s.workspace?.task.worker_active||s.job.worker_active)||jsauxPreparationBusy(s.jsaux)||s.updates?.phase==='installing';
    const undo=s.workspace?.selection_undo;
    return <div data-ui-part="collection-management">
      <Focusable className="collection-management-actions" flow-children="row">
        {selectionCount>0&&actionButton(tr('Deselect all','Tout désélectionner'),()=>void bulkSelection(),'clear-selection',blocked)}
        {(selectionCount>0||s.installation.installed)&&<DialogButton className="collection-action" data-collection-focus="manage-collection" disabled={blocked} onClick={event=>showContextMenu(
          <Menu label={tr('Manage collection','Gérer la collection')} onCancel={()=>focus('manage-collection')} cancelText={tr('Back','Retour')}>
            {(s.workspace?.member_count||0)>1&&<MenuItem data-collection-focus="reorder-collection" onSelected={()=>{remember();setSub('reorder');void run('workspace_preferences',{patch:{layout:'list'}});focus('back');}}>{tr('Reorder my collection','Réorganiser ma collection')}</MenuItem>}
            {s.installation.installed&&<MenuItem data-collection-focus="preview-installed" onSelected={()=>void showPreview(true)}>{tr('View installed collection','Voir la collection installée')}</MenuItem>}
            {selectionCount>0&&<MenuItem data-collection-focus="rebuild-all" onSelected={()=>beginPreparation('all')}>{tr('Prepare all visuals again…','Repréparer tous les visuels…')}</MenuItem>}
            <MenuItem data-collection-focus="delete-collection" onSelected={()=>{setManagementConfirm(true);focus('cancel-delete');}}>{tr('Delete my collection…','Supprimer ma collection…')}</MenuItem>
          </Menu>,event.currentTarget||undefined)}>{tr('Manage collection','Gérer la collection')}</DialogButton>}
      </Focusable>
      {undo&&<Focusable className="collection-selection-undo" flow-children="row" data-ui-part="selection-undo"><p role="status">{tr(`${undo.count} games deselected.`,`${undo.count} jeux désélectionnés.`)}{s.installation.installed?' '+tr('Installed collection kept.','Collection installée conservée.'):''}</p>{actionButton(tr('Undo','Annuler'),()=>void bulkSelection(true),'undo-selection',blocked)}</Focusable>}
    </div>;
  }
  const hero=s&&<section className="collection-workflow collection-workflow-simple" aria-label={tr('Next step','Prochaine étape')} data-ui-part="collection-summary">
    <Field className="collection-hero" label={tr(`${s.workspace?.included_count||0} games${changes?` · ${changes} pending change${changes===1?'':'s'}`:''}`,`${s.workspace?.included_count||0} jeux${changes?` · ${changes} modification${changes===1?'':'s'} à préparer`:''}`)}
      description={step==='attention'?tr('Check the affected games.','Vérifiez les jeux concernés.'):step==='preview'?tr('Up to date','À jour'):undefined}>
      {actionButton(['prepare','install','faceplate'].includes(step)?tr('Prepare and install','Préparer et installer'):step==='attention'&&ctx.filter==='attention'?tr('Prepare and install','Préparer et installer'):labels(s)[step],primary,'primary',saving)}
    </Field>
    {managementControls()}
  </section>;
  let content;
  if(!s)content=<p>{tr('Loading…','Chargement…')}</p>;
  else if(sub==='reorder')content=<>{backButton()}<CollectionOrder random={Boolean(s.options.shuffle&&!(s.jsaux?.enabled&&s.jsaux.detected&&s.jsaux.compatible&&faceplateEffectiveMode(s.jsaux)==='sync'))} client={client} leave={orderLeave} onPending={value=>{orderSaving.current=value;}} save={async(ids,revision)=>Boolean(await run('workspace_reorder',{appids:ids,revision}))}/></>;
  else if(managementConfirm)content=<section className="collection-management-confirm" data-ui-part="delete-confirmation"><h2>{tr('Delete my collection?','Supprimer ma collection ?')}</h2><p>{tr('Your game selection and installed screensaver will be removed.','La sélection de jeux et l’écran de veille installé seront supprimés.')}</p><p>{tr('Downloaded visuals, settings and connections are kept.','Les visuels téléchargés, les réglages et les connexions sont conservés.')}</p><Focusable className="collection-actions" flow-children="row">{actionButton(tr('Cancel','Annuler'),()=>{setManagementConfirm(false);focus('manage-collection');},'cancel-delete')}{actionButton(tr('Delete collection','Supprimer la collection'),()=>void deleteCollection(),'confirm-delete',saving)}</Focusable></section>;
  else if(confirm)content=<section aria-label={tr('Confirmation','Confirmation')} className="collection-confirm"><h2>{confirm==='draft'?tr('Unsaved choices','Choix non enregistrés'):confirm==='faceplate'?tr('Prepare Faceplate JSAUX?','Préparer la Faceplate JSAUX ?'):prepareMode==='all'&&confirm==='prepare'?tr('Prepare all visuals again?','Repréparer tous les visuels ?'):s.installation.installed?tr('Update my collection?','Mettre à jour ma collection ?'):tr('Create my screensaver?','Créer mon écran de veille ?')}</h2>
    {confirm!=='draft'&&<p>{tr('The installed collection is kept until success.','La collection installée est conservée jusqu’à réussite.')}</p>}
    {['prepare','faceplate'].includes(confirm)&&<p className="collection-confirm-count" data-ui-part="preparation-selection-count">{tr(`${selectionCount} game${selectionCount===1?'':'s'} selected`,`${selectionCount} jeu${selectionCount===1?'':'x'} sélectionné${selectionCount===1?'':'s'}`)}</p>}
    {confirm==='faceplate'&&<p>{tr('Unchanged TV visuals are reused.','Les visuels TV inchangés sont réutilisés.')}</p>}
    {confirm==='prepare'&&<p>{prepareMode==='missing'?tr('Unchanged visuals are reused.','Les visuels inchangés sont réutilisés.'):tr('Every selected game will be processed again.','Tous les jeux sélectionnés seront retraités.')}</p>}
    <Focusable className="collection-actions" flow-children="row">{actionButton(tr('Back','Retour'),()=>{setConfirm(null);focus(confirm==='faceplate'?'prepare-faceplate':tab==='add'?'prepare-selection':'primary');},'back')}{confirm==='draft'?<>{actionButton(tr('Discard edit','Abandonner'),()=>{setDirty(false);setConfirm(null);setGame(null);focus((tab==='add'?'select-game-':'game-')+game?.appid);},'discard')}{actionButton(tr('Save choices','Enregistrer les choix'),()=>void save(),'save',saving)}</>:actionButton(confirm==='faceplate'?tr('Prepare and install','Préparer et installer'):confirm==='prepare'&&prepareMode==='all'?tr('Rebuild and install','Tout reconstruire et installer'):confirm==='prepare'?tr('Prepare and install','Préparer et installer'):updateLabel(s),()=>void execute(),'confirm',saving)}</Focusable></section>;
  else if(preview)content=<>{backButton()}<Player preview={preview} client={client} onClose={()=>{closePreview();focus(game?'preview':sub==='activity'?'preview-installed':'primary');}}/></>;
  else if(game&&draft&&assets)content=<>{backButton()}<h2>{game.name}</h2>{role==='animation'&&<p>{tr('Focus an animation to preview it.','Placez-vous sur une animation pour l’animer.')}</p>}{!artLoading&&!assets.length&&<p>{tr('No matching artwork. Try an image instead.','Aucun visuel correspondant. Essayez une image à la place.')}</p>}
    {role==='panel'&&selected.panel&&<section className="collection-panel-editor" data-panel-editor>
      <h3>Faceplate JSAUX</h3>
      <div className={'collection-panel-preview'+(s.jsaux?.framing==='fill'?' is-fill':'')} role="img" aria-label={tr('Faceplate JSAUX framing preview','Aperçu du cadrage Faceplate JSAUX')} style={{'--panel-crop-y':`${draft.faceplate_crop.y}%`} as CSSProperties}>
        <ArtworkImage src={selected.panel.thumb} alt=""/>
      </div>
      {s.jsaux?.framing==='fill'&&<div data-faceplate-crop><SliderField label={tr('Vertical framing','Cadrage vertical')} value={draft.faceplate_crop.y} min={0} max={100} step={1} onChange={y=>mutate({faceplate_crop:{...draft.faceplate_crop,y}})}/></div>}
      {actionButton(tr('Use this image','Utiliser cette image'),()=>{setAssets(null);focus('pick-panel');},'use-panel',saving)}
    </section>}
    {artLoading&&<p role="status">{tr('Finding artwork…','Recherche des visuels…')}</p>}
    {role==='animation'&&actionButton(tr('Choose an image','Choisir une image'),()=>void browse('still_tv'),'asset-none',saving)}
    <Focusable className="collection-grid" flow-children="grid" onBlurCapture={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setActiveAsset(null);}} onFocusCapture={event=>{const key=(event.target as Element).closest<HTMLElement>('[data-collection-focus^="asset-"]')?.dataset.collectionFocus;setActiveAsset(key?Number(key.slice(6)):null);}}>{assets.slice(0,candidateLimit).map(a=><Focusable role="button" tabIndex={0} className="collection-card collection-candidate" data-collection-focus={'asset-'+a.id} key={a.id} onGamepadFocus={()=>setActiveAsset(a.id)} onGamepadBlur={()=>setActiveAsset(current=>current===a.id?null:current)} onActivate={()=>choose(a)}>
      <CandidateArtwork asset={a} appid={game.appid} role={role} active={activeAsset===a.id} client={client}/><strong>{a.width&&a.height?`${a.width} × ${a.height}`:tr('Artwork','Illustration')}</strong><small>{a.author||'SteamGridDB'}</small></Focusable>)}</Focusable>{assets.length>candidateLimit&&actionButton(tr('More artwork','Autres visuels'),()=>setCandidateLimit(v=>v+8),'more-candidates')}</>;
  else if(game&&draft)content=<>{backButton()}<h2>{game.name}</h2><Focusable className="collection-detail" flow-children={wideDetail?'row':'column'} onGamepadDirection={detailDirection} onKeyDown={event=>{if((event.key==='ArrowLeft'||event.key==='ArrowRight')&&crossColumn(event.key==='ArrowLeft'?-1:1,event.target as Element)){event.preventDefault();event.stopPropagation();}}}><Focusable data-detail-column="preview" flow-children="column" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_Y}><GameArtworkPreview game={game} patch={draft as unknown as Record<string,unknown>} client={client} membershipControl={<Focusable className="collection-inclusion" tabIndex={-1} data-collection-focus="screensaver-inclusion" data-ui-part="game-screensaver-inclusion"><ToggleField label={tr('In screensaver','Dans l’écran de veille')} checked={!draft.excluded} onChange={v=>mutate({excluded:!v})}/></Focusable>}/>
      <Focusable className="collection-actions collection-sheet-save" flow-children="row">{s.jsaux?.detected&&s.jsaux.compatible&&actionButton(tr("Choose Faceplate JSAUX image","Choisir l’image Faceplate JSAUX"),()=>void browse('panel'),'pick-panel',saving||!s.key_configured)}
      {actionButton(game.collection_member?tr('Save choices','Enregistrer les choix'):tr('Add to my collection','Ajouter à ma collection'),()=>void save(),'save',saving)}</Focusable>
      {game.problem&&!game.problem.skipped&&<div className="collection-attention"><p>{game.problem.skipped&&game.problem.code!=='visual_size_limit'?tr('Visual skipped. Choose another manually.','Visuel ignoré. Choisissez-en un autre manuellement.'):errorText(game.problem.code)} {game.problem.retained_media&&tr('Previous version kept.','Ancienne version conservée.')}</p>{game.problem.skipped&&actionButton(game.problem.role==='cover'?tr('Choose another cover','Choisir une autre jaquette'):game.problem.role==='logo'?tr('Choose another logo','Choisir un autre logo'):tr('Choose another visual','Choisir un autre visuel'),()=>void browse(game.problem!.role==='cover'?'cover':game.problem!.role==='logo'?'logo':'animation'),'replace-skipped-visual',saving||!s.key_configured)}</div>}</Focusable><Focusable data-detail-column="settings" flow-children="column" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_Y}>
      {(['animation','cover','logo'] as const).map(r=>{const chosen=r==='animation'?(selected.animation||selected.still_tv):selected[r];return <div className={'collection-field'+(r==='animation'?' collection-background-field':'')} key={r}><div className="collection-label">{r==='animation'?tr('Background','Fond'):r==='cover'?tr('Cover','Jaquette'):tr('Logo','Logo')}{chosen&&<small>{chosen.author||'SteamGridDB'}</small>}</div>{safeImage(chosen?.thumb)&&<ArtworkImage className="collection-chosen-thumb" src={chosen?.thumb}/>}{r==='animation'?<Focusable className="collection-background-actions" flow-children="row">{actionButton(tr('Animations','Animations'),()=>void browse('animation'),'pick-animation',saving||!s.key_configured)}{actionButton(tr('Still images','Images fixes'),()=>void browse('still_tv'),'pick-still_tv',saving||!s.key_configured)}</Focusable>:actionButton(tr('Choose','Choisir'),()=>void browse(r),'pick-'+r,saving||!s.key_configured)}</div>;})}
      {(selected.still_tv||game.animated===false)&&<DropdownItem label={tr('Image movement','Mouvement de l’image')} description={s.options.reduced_motion?tr('Reduce motion is enabled.','Réduction des mouvements activée.'):undefined} selectedOption={draft.still_mode==='fixed'?'fixed':'motion'} rgOptions={[{data:'motion',label:tr('Gentle movement','Mouvement doux')},{data:'fixed',label:tr('Still image','Image fixe')}]} onChange={o=>mutate({still_mode:o.data})}/>}
      <DropdownItem label={tr('Framing','Cadrage')} selectedOption={draft.crop.mode} rgOptions={['inherit','original','16:9','16:10'].map(data=>({data,label:data==='inherit'?tr('General setting','Réglage général'):data==='original'?tr('Full image','Image entière'):data}))} onChange={o=>mutate({crop:{...draft.crop,mode:o.data}})}/>
      {['16:9','16:10'].includes(draft.crop.mode)&&<><SliderField label={tr('Horizontal framing','Cadrage horizontal')} value={draft.crop.x} min={0} max={100} step={1} onChange={x=>mutate({crop:{...draft.crop,x}})}/><SliderField label={tr('Vertical framing','Cadrage vertical')} value={draft.crop.y} min={0} max={100} step={1} onChange={y=>mutate({crop:{...draft.crop,y}})}/></>}
      <DropdownItem label={tr('Game branding','Nom du jeu')} selectedOption={draft.branding.mode} rgOptions={['inherit','logo','title','both','hidden'].map(data=>({data,label:({inherit:tr('General setting','Réglage général'),logo:'Logo',title:tr('Title','Titre'),both:tr('Logo and title','Logo et titre'),hidden:tr('Hidden','Masqué')} as Record<string,string>)[data]}))} onChange={o=>mutate({branding:{...draft.branding,mode:o.data}})}/>
      {['logo','both'].includes(draft.branding.mode==='inherit'?s.options.name_display:draft.branding.mode)&&<DropdownItem label={tr('Logo position','Position du logo')} selectedOption={draft.branding.position} rgOptions={['inherit','bottom-left','bottom-right','top-left','top-right'].map(data=>({data,label:({inherit:tr('General setting','Réglage général'),'bottom-left':tr('Bottom left','En bas à gauche'),'bottom-right':tr('Bottom right','En bas à droite'),'top-left':tr('Top left','En haut à gauche'),'top-right':tr('Top right','En haut à droite')} as Record<string,string>)[data]}))} onChange={o=>mutate({branding:{...draft.branding,position:o.data}})}/>}
      <DropdownItem label={tr('Cover position','Position de la jaquette')} selectedOption={draft.cover_position} rgOptions={['bottom-left','bottom-right','top-left','top-right'].map(data=>({data,label:({'bottom-left':tr('Bottom left','En bas à gauche'),'bottom-right':tr('Bottom right','En bas à droite'),'top-left':tr('Top left','En haut à gauche'),'top-right':tr('Top right','En haut à droite')} as Record<string,string>)[data]}))} onChange={o=>mutate({cover_position:o.data})}/>
      </Focusable></Focusable></>;
  else if(sub==='activity')content=<>{backButton()}<section className="collection-activity" data-activity-state={activity}><h2>{activity==='partial'&&batchCapacity?tr('Prepare Faceplate JSAUX','Préparer la Faceplate JSAUX'):activity==='partial'&&faceplateRepair?tr("TV artwork ready · Faceplate JSAUX to repair","Visuels TV prêts · Faceplate JSAUX à réparer"):activity==='preparing'&&jsauxVisible(s.jsaux)&&s.workspace?.task.stage==='faceplate'?tr("Preparing the Faceplate JSAUX collection","Préparation de la collection Faceplate JSAUX"):activityTitles[activity]}</h2>
    {!batchCapacity&&<FaceplatePreparationStatus state={s}/>}
    {!batchCapacity&&(s.workspace?.task.tv_state||showPanelResult&&s.workspace?.task.faceplate_state)&&<p data-workflow-outputs>{[s.workspace?.task.tv_state&&tvLabels[s.workspace.task.tv_state],showPanelResult&&s.workspace?.task.faceplate_state&&panelLabels[recoveredFaceplate?'installed':s.workspace.task.faceplate_state]].filter(Boolean).join(' · ')}</p>}
    {['preparing','paused','waiting_game','applying'].includes(activity)&&<><p>{activity==='applying'?tr('Installing…','Installation…'):jsauxVisible(s.jsaux)&&s.workspace?.task.stage==='faceplate'?tr("Preparing Faceplate JSAUX…","Préparation de la Faceplate JSAUX…"):stageText(s.job.stage)}</p>{s.job.name&&s.workspace?.task.stage!=='faceplate'&&<p>{s.job.name}</p>}<progress aria-label={tr('Current preparation','Préparation en cours')} value={activity==='applying'?100:jsauxPreparationBusy(s.jsaux)||s.workspace?.task.stage==='faceplate'?s.jsaux?.prepared?.percent||0:s.job.percent||0} max={100}/>{activity!=='applying'&&s.workspace?.task.stage!=='faceplate'&&<p>{s.job.completed} / {s.job.total} · {s.job.percent||0}%</p>}</>}
    {activity==='waiting_game'&&<p>{tr('Close the game to avoid an overload. Preparation resumes automatically.','Fermez le jeu pour éviter une surcharge. La préparation reprendra automatiquement.')}</p>}
    {activity==='paused'&&s.workspace?.task.error==='GAME_RUNNING'&&<p>{tr('Close the game to avoid an overload, then select Resume.','Fermez le jeu pour éviter une surcharge, puis choisissez Reprendre.')}</p>}
    {interruptedMedia&&<Field label={<span role="status">{errorText(s.job.error||s.workspace?.task.error||'worker_signal')}</span>}>{actionButton(tr('Diagnostic','Diagnostic'),()=>setSection('assistance'),'interruption-diagnostic',saving)}</Field>}
    {!interruptedMedia&&!recoveredFaceplate&&!faceplateIssue(s)&&s.workspace?.task.error&&s.workspace.task.error!=='GAME_RUNNING'&&<p role="alert">{errorText(s.workspace.task.error)}</p>}
    {activity==='installed'&&installedCount!==undefined&&<p>{tr(`${installedCount} games installed.`,`${installedCount} jeux installés.`)}</p>}
    {activity==='unchanged'&&<p>{tr('Your previous installed collection has been kept.','Votre ancienne collection installée est conservée.')}{skippedCount(s)>0?' '+tr('Games without an animation were not added. Allow still images to include them.','Les jeux sans animation n’ont pas été ajoutés. Autorisez les images fixes pour les inclure.'):''}</p>}
    {activity==='empty'&&<p>{skippedVisualGames?tr('No readable visual. Choose replacements to prepare these games.','Aucun visuel lisible. Choisissez d’autres visuels pour préparer ces jeux.'):tr('No games matched your choices. Nothing was installed.','Aucun jeu ne correspond à vos choix. Rien n’a été installé.')}</p>}
    {!batchCapacity&&(activity==='partial'||activity==='error'||activity==='cancelled')&&<p>{s.installation.installed?tr('Your previous installed collection has been kept.','Votre ancienne collection installée est conservée.'):tr('No new collection was installed.','Aucune nouvelle collection n’a été installée.')}</p>}
    {faceplateRecovery()}
    {!batchCapacity&&<Focusable className="collection-actions" flow-children="row">
      {activity==='preparing'&&s.job.worker_active&&actionButton(tr('Pause','Suspendre'),()=>void run('pause'),'pause',saving)}
      {activity==='paused'&&actionButton(tr('Resume','Reprendre'),()=>void run('resume',{language:language()}),'resume',saving)}
      {['preparing','paused','waiting_game'].includes(activity)&&actionButton(tr('Cancel','Annuler'),()=>void run('cancel'),'cancel',saving)}
      {activity==='partial'&&(!faceplateRepair||Boolean(s.workspace?.issues_count))&&actionButton(tr('See games to fix','Voir les jeux à corriger'),()=>{setSub('');setTab('collection');setCtx({...EMPTY,filter:'attention'});focus('primary');},'fix-games')}
      {activity==='empty'&&!s.options.static_fallback&&actionButton(tr('Include still images','Inclure les images fixes'),()=>void run('configure',{patch:{static_fallback:true}}),'allow-still-images',saving)}
      {!['preparing','paused','waiting_game','applying'].includes(activity)&&s.installation.installed&&actionButton(tr('See the result','Voir le résultat'),()=>void showPreview(true),'preview-installed',saving)}
      {actionButton(tr('My collection','Ma collection'),()=>{setSub('');setTab('collection');focus('primary');},'continue')}
    </Focusable>}
    {activity==='installed'&&<div className="collection-first-use"><p>{tr('First use: select this screensaver in Steam.','Première utilisation : sélectionnez cet écran de veille dans Steam.')}</p>{actionButton(tr('How to choose in Steam','Comment le choisir dans Steam'),()=>setSection('steam'),'steam-help')}</div>}
    </section></>;
  else if(sub==='steam')content=<>{backButton()}<h2>{tr('Choose in Steam','Choisir dans Steam')}</h2><p>{tr('Steam → Settings → Customization → Screensaver → decky-animated-screensaver','Steam → Paramètres → Personnalisation → Écran de veille → decky-animated-screensaver')}</p><p>{tr('Steam selection cannot be verified here. Preview does not activate the screensaver.','Le choix Steam n’est pas vérifiable ici. L’aperçu n’active pas l’écran de veille.')}</p></>;
  else if(sub==='updates')content=<>{backButton()}{s.updates&&<UpdatesPanel state={s.updates} run={run as StudioClient} saving={saving} focusRequest={updateFocusRequest}/>}</>;
  else if(sub==='appearance')content=<>{backButton()}<h2>{tr('Appearance','Apparence')}</h2><DropdownItem label={tr('Collection view','Présentation de la collection')} selectedOption={s.workspace?.layout||'comfort'} rgOptions={[{data:'comfort',label:tr('Comfort · 4 columns','Confort · 4 colonnes')},{data:'compact',label:tr('Compact · 5 columns','Compact · 5 colonnes')},{data:'list',label:tr('List','Liste')}]} onChange={o=>void run('workspace_preferences',{patch:{layout:o.data}})}/></>;
  else if(sub)content=<>{backButton()}{sub==='advanced'?<AdvancedPanel state={s} run={run as StudioClient} saving={saving}/>:sub==='assistance'?<AssistancePanel state={s} run={run as StudioClient} saving={saving}/>:<SettingsPanels state={s} run={run as StudioClient} saving={saving} section={sub as 'setup'|'playback'|'jsaux'} onCollection={()=>{setSub('');setTab('collection');setCtx({...EMPTY});focus('primary');}} inCollection={tab==='collection'}/>}</>;
  else if(tab==='settings')content=<><h2>{tr('Settings','Réglages')}</h2>{s.display_name_restart_required&&<p>{tr('The name Animated Screensaver will appear in the plugin list after the next Decky restart.','Le nom Animated Screensaver apparaîtra dans la liste des plugins au prochain redémarrage de Decky.')}</p>}<div className="collection-settings">
    {([['setup',tr('Setup','Configuration')],['playback',tr('Playback','Lecture')],['appearance',tr('Appearance','Apparence')],...(s.jsaux?.detected&&s.jsaux.compatible?[['jsaux','Faceplate JSAUX']]:[]),['steam',tr('First use in Steam','Première utilisation dans Steam')],['updates',tr('Updates','Mises à jour')],['advanced',tr('Advanced','Avancé')],['assistance',tr('Storage and assistance','Stockage et assistance')]]).map(([id,label])=><Field key={id} label={label} description={id==='playback'?s.options.scene_seconds+' s · '+(s.options.shuffle?tr('Random','Aléatoire'):tr('Collection order','Ordre de la collection')):id==='appearance'?s.options.framing+' · '+(s.workspace?.layout||'comfort'):id==='setup'?(s.key_configured?tr('Key saved','Clé enregistrée'):tr('Key needed','Clé à ajouter'))+' · '+(s.media_tools.available?tr('Tools ready','Outils prêts'):tr('Tools needed','Outils à installer')):id==='jsaux'?tr('Via GabeCubeAura','Via GabeCubeAura'):id==='steam'?tr('Select the screensaver in Steam','Choisir l’écran de veille dans Steam'):id==='advanced'?tr('All settings and JSON backups','Tous les réglages et sauvegardes JSON'):id==='updates'?tr('Plugin updates and GitHub','Mises à jour du plugin et GitHub'):tr('Diagnostics, cache and advanced tools','Diagnostics, cache et outils avancés')}> {actionButton(tr('Open','Ouvrir'),()=>setSection(id),'settings-'+id)}</Field>)}
  </div></>;
  else if(tab==='add')content=<><h2>{tr('Add games','Ajouter des jeux')}</h2>
    <section className="collection-selection-summary" data-ui-part="selection-summary" aria-label={tr('Selection','Sélection')}>
      <Field bottomSeparator="none" label={<span role="status" aria-live="polite">{tr(`${selectionCount} game${selectionCount===1?'':'s'} selected`,`${selectionCount} jeu${selectionCount===1?'':'x'} sélectionné${selectionCount===1?'':'s'}`)}</span>}>
        {actionButton(step==='activity'?tr('View preparation','Voir la préparation'):step==='resume'?tr('Resume','Reprendre'):tr('Prepare','Préparer'),()=>{if(step==='activity'||step==='resume')primary();else beginPreparation();},'prepare-selection',saving||selectionBusy||selectionCount===0)}
      </Field>
    </section>
    {managementControls()}
    <div className="collection-still-option" data-ui-part="still-image-option"><ToggleField label={tr('Include still images','Inclure les images fixes')} description={tr('When no animation is available.','Si aucune animation n’est disponible.')} checked={s.options.static_fallback} disabled={saving||selectionBusy||Boolean(s.workspace?.task.worker_active||s.job.worker_active)} onChange={static_fallback=>void run('configure',{patch:{static_fallback}})}/></div>
    <Focusable className="collection-search-view" flow-children="row" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_X}>{searchField(tr('Find a game','Rechercher un jeu'))}{sourcePicker()}{viewPicker()}</Focusable>
    {ctx.query.trim().length>0&&ctx.query.trim().length<3&&<p>{tr('Enter at least 3 characters','Saisissez au moins 3 caractères')}</p>}
    {ctx.source==='online'&&!ctx.query&&<p>{tr('Enter at least 3 characters','Saisissez au moins 3 caractères')}</p>}
    {ctx.source==='top'&&<p>{tr('Most played now · Steam','Les plus joués actuellement · Steam')}{rankAt?' · '+new Date(rankAt*1000).toLocaleString():''}{stale?' · '+tr('Saved results · offline','Résultats en cache · hors ligne'):''}</p>}
    {loading&&!page.items.length&&<p role="status">{tr('Finding games…','Recherche des jeux…')}</p>}{grid()}{pagination()}
    {notice&&!loading&&actionButton(tr('Retry','Réessayer'),()=>void load(),'retry-discovery')}
    {!notice&&!loading&&!page.total&&ctx.query.trim().length>=3&&<div className="collection-empty"><p>{tr('No games found. Try another name.','Aucun jeu trouvé. Essayez un autre nom.')}</p>{actionButton(tr('Clear search','Effacer la recherche'),()=>setCtx({...ctx,query:'',page:0}),'clear-search')}</div>}
    {ctx.source==='installed'&&actionButton(tr('Refresh installed games','Actualiser les jeux installés'),()=>void run('workspace_scan').then(()=>load()),'scan',saving)}
    </>;
  else content=<>{hero}<FaceplatePreparationStatus state={s}/>{faceplateRecovery()}
    {skippedCount(s)>0&&!s.options.static_fallback&&<Field className="collection-inclusion" data-skipped-info label={tr(`${skippedCount(s)} games without an animation`,`${skippedCount(s)} jeux sans animation`)} description={tr('Use still images to include them.','Incluez-les avec des images fixes.')} childrenContainerWidth="fixed">
      {actionButton(tr('Include still images','Inclure les images fixes'),()=>void run('configure',{patch:{static_fallback:true}}),'allow-still-images',saving||Boolean(s.workspace?.task.worker_active||s.job.worker_active))}
    </Field>}
    {ctx.filter==='attention'&&<div className="collection-attention"><strong>{tr('Games to fix','Jeux à corriger')}</strong>{actionButton(tr('Show my whole collection','Voir toute ma collection'),()=>setCtx({...EMPTY}),'clear-filter')}</div>}
    <Focusable className="collection-search-view" flow-children="row" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_X}>{searchField(tr('Search my collection','Rechercher dans ma collection'))}{filterPicker()}{viewPicker()}</Focusable>
    {ctx.query.trim().length>0&&ctx.query.trim().length<3?<p>{tr('Enter at least 3 characters','Saisissez au moins 3 caractères')}</p>:!page.total?loading?<p role="status">{tr('Loading…','Chargement…')}</p>:<div className="collection-empty"><h2>{ctx.query?tr('No matching game','Aucun jeu correspondant'):tr('Your games, on your screensaver.','Vos jeux, sur votre écran de veille.')}</h2>{ctx.query&&actionButton(tr('Clear search','Effacer la recherche'),()=>setCtx({...ctx,query:'',page:0}),'clear-search')}</div>:grid()}{pagination()}
    </>;

  function faceplateRecovery(){return s&&<FaceplateRecovery state={s} disabled={saving||selectionBusy||Boolean(s.workspace?.task.worker_active||s.job.worker_active)||jsauxPreparationBusy(s.jsaux)} onPrepare={()=>{setConfirm(s.workspace?.pending_count?'prepare':'faceplate');setPrepareMode('missing');focus('confirm');}} onConnection={()=>{void run('jsaux_refresh',{force:true});}} onDetails={()=>setSection('jsaux')}/>;}
  function grid(){return <Focusable className={'collection-grid '+(s?.workspace?.layout||'comfort')+(tab==='add'?' collection-selection-grid':'')} flow-children={s?.workspace?.layout==='list'?'column':'grid'} aria-busy={loading} onOptionsActionDescription={canSelectAll?tr('Select all','Tout sélectionner'):undefined} onOptionsButton={tab==='add'?selectAllButton:undefined} onKeyDown={event=>{if(tab==='add'&&event.key.toLowerCase()==='y'&&!event.ctrlKey&&!event.altKey&&!event.metaKey){event.preventDefault();event.stopPropagation();if(!event.repeat)void selectAllAvailable();}}}>{page.items.map(g=>{
    const selected=selectionOverrides[g.appid]??Boolean(g.collection_member&&!g.excluded);
    const artwork=<><div className="collection-game-media"><ArtworkImage src={g.thumbnail_url} alt={g.name}/></div><div className="collection-game-copy">{g.rank&&<span className="collection-rank">#{g.rank}{typeof g.players==='number'&&g.players>=0?' · '+g.players.toLocaleString()+' '+tr('players','joueurs'):''}</span>}<strong>{g.name}</strong><small>{tab==='add'?(selected?tr('Added to my collection','Ajouté à ma collection'):tr('Select','Sélectionner')):g.workspace_draft?tr('Saved choices · to prepare','Choix enregistrés · à préparer'):g.excluded?tr('Not displayed','Non affiché'):skippedGame(g)?tr('No animation · not included','Sans animation · non inclus'):g.problem&&!g.problem.skipped?tr('Unavailable','Indisponible'):stageText(g.pending_change?'pending':g.status)}</small></div></>;
    if(tab==='add')return <Focusable flow-children={s?.workspace?.layout==='list'?'row':'column'} navEntryPreferPosition={s?.workspace?.layout==='list'?NavEntryPositionPreferences.MAINTAIN_X:NavEntryPositionPreferences.MAINTAIN_Y} className={'collection-card collection-select-card'+(selected?' is-selected':'')} key={g.appid} data-ui-part={'add-game-'+g.appid}>
      <Focusable className="collection-select-main" tabIndex={0} role="checkbox" aria-checked={selected} aria-label={tr(`Select ${g.name}`,`Sélectionner ${g.name}`)} aria-busy={selectionIntents.current.has(g.appid)} data-collection-focus={'select-game-'+g.appid} onActivate={()=>{if(!saving||selectionBusy)toggleSelection(g);}} onOKActionDescription={selected?tr('Deselect','Désélectionner'):tr('Select','Sélectionner')} onSecondaryActionDescription={!selectionBusy&&!saving?tr('Customize','Personnaliser'):undefined} onSecondaryButton={event=>{event.preventDefault();event.stopPropagation();if(!selectionBusy&&!saving){setCtx({...ctx,appid:g.appid});void openGame(g);}}} onKeyDown={event=>{
        if(event.key.toLowerCase()==='x'){event.preventDefault();if(!selectionBusy&&!saving){setCtx({...ctx,appid:g.appid});void openGame(g);}}
      }}>{artwork}<span className="collection-selection-check" aria-hidden="true">{selected?'✓':''}</span></Focusable>
      <DialogButton className="collection-customize" aria-label={tr(`Customize ${g.name}`,`Personnaliser ${g.name}`)} data-collection-focus={'customize-game-'+g.appid} disabled={saving||selectionBusy} onClick={()=>{setCtx({...ctx,appid:g.appid});void openGame(g);}}>{tr('Customize','Personnaliser')}</DialogButton>
    </Focusable>;
    return <Focusable role="button" tabIndex={0} className={'collection-card'+(g.problem?' collection-card-alert':g.workspace_draft?' collection-card-pending':'')} key={g.appid} data-collection-focus={'game-'+g.appid} onActivate={()=>{setCtx({...ctx,appid:g.appid});void openGame(g);}}>{artwork}</Focusable>;
  })}</Focusable>;}

  function pagination(){
    if(s?.workspace?.layout==='list')return page.total>page.items.length?<div className="collection-load-more" ref={listSentinel} data-ui-part="collection-load-more">
      <span role="status">{tr(`${page.items.length} / ${page.total} games`,`${page.items.length} / ${page.total} jeux`)}</span>
      {actionButton(loading?tr('Loading…','Chargement…'):tr('Show 10 more games','Afficher 10 jeux de plus'),()=>{if(!loading&&!listBusy.current){listBusy.current=true;setCtx(current=>({...current,page:current.page+1}));}},'load-more',loading)}
    </div>:page.total>0?<p className="collection-list-count">{tr(`${page.items.length} games`,`${page.items.length} jeux`)}</p>:null;
    return page.total>page.page_size&&<Focusable className="collection-actions" flow-children="row">{actionButton(tr('Previous','Précédent'),()=>{setCtx({...ctx,page:Math.max(0,page.page-1)});focus('back-page');},'back-page',page.page===0)}<span>{page.page+1}/{Math.ceil(page.total/page.page_size)}</span>{actionButton(tr('Next','Suivant'),()=>{setCtx({...ctx,page:page.page+1});focus('next-page');},'next-page',(page.page+1)*page.page_size>=page.total)}</Focusable>;
  }

  const pageContent=<DialogBody className="collection-content" data-ui-screen={game?'game-'+game.appid:sub||tab}>
    {!nested&&<PluginUpdateNotice onOpen={()=>{setSection('updates');void refresh();}}/>}
    {error&&<RecoveryCard code={failure?.code} disabled={saving} onRecover={action=>void recover(action)}/>}{notice&&<p role="status">{notice}</p>}<DialogControlsSection>{content}</DialogControlsSection>
  </DialogBody>;
  const bodyContent=<Focusable ref={body} className={'collection-scroll-owner'+(nested?' collection-nested-scroll':'')} flow-children="column" onKeyDown={e=>{if(e.key==='Escape'&&!e.defaultPrevented)cancel(e);}}>{nested?<ScrollPanel>{pageContent}</ScrollPanel>:pageContent}</Focusable>;
  return <Focusable ref={root} className="das collection-frame" flow-children="column" onCancel={cancel} onCancelActionDescription={tr('Back','Retour')}><style>{COLLECTION_CSS}</style>
    <div className="collection-tab-host">{nested?<>{bodyContent}</>:Tabs?<Tabs activeTab={tab} autoFocusContents={false} onShowTab={(id:string)=>navigate(id as CollectionTab)} tabs={(['collection','add','settings'] as CollectionTab[]).map(id=>({id,title:names()[id],content:id===tab?bodyContent:null}))}/>:<><p>{tr('Native tabs unavailable. Reopen the plugin.','Onglets natifs indisponibles. Rouvrez le plugin.')}</p></>}</div>
  </Focusable>;
}
