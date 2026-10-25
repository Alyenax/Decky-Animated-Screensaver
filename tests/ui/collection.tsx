// Actual production React components; only Decky controls and RPC are adapted.
import {createRoot} from 'react-dom/client';
import {StudioShell,QuickShell} from '../../src/StudioShell';
import {StudioRoute} from '../../src/StudioRoute';
import {publishUpdate} from '../../src/update_notice';
import {setLanguage} from '../../src/i18n';
import {discoveryResponse} from '../../src/discoveryResponse';
import {ArtworkImage} from '../../src/ArtworkImage';
import {artworkDiagnostic} from '../../src/artworkDiagnostic';
import {Player} from '../../src/StudioRuntime';

export const root=createRoot(document.getElementById('root')!);
const names=['Elden Ring','Cyberpunk 2077','Hades','Portal 2','Deep Rock Galactic','Stardew Valley','Hollow Knight','Baldur’s Gate 3','Dead Cells','Balatro','Terraria','Noita'];
const ids=[1245620,1091500,1145360,620,548430,413150,367520,1086940,588650,2379780,105600,881100];
let selectionUndo:any=null,managementError=false,orderIds:number[]=[],orderFailure=false,orderDelay=0;
let state:any,games:any[],drafts:any,calls:any[],generation=0,topFailures=0,candidateThumb='',candidateSquare=false,candidateMany=false,candidateMotionError=false,detailsFailure='',selectionFailure=false,selectionDelay=0,jsauxAfterRefresh:any=null,gameRunning=false,gameRunningCode='GAME_RUNNING';
function reset(){
  games=names.map((name,i)=>({appid:ids[i],name,installed:true,installed_in_collection:i<8,excluded:i>=8,collection_member:i<8,status:i<8?'ready':'pending',animated:true,thumbnail_url:'',media:i<8?{tv:'prepared/test.gif'}:{},crop:{mode:'inherit',x:50,y:50}}));
  state={version:'0.1.0-alpha.32',key_configured:true,connection:'verified',game_count:12,ready_count:8,included_count:8,failed_count:0,excluded_count:4,
    options:{scene_seconds:15,shuffle:false,transition:'crossfade',show_title:true,show_logo:true,show_cover:true,cover_position:'bottom-right',name_display:'both',framing:'original',static_fallback:false,reduced_motion:false,smoothing:false,smoothing_mode:'fast',smoothing_fps:30,logo_position:'bottom-left',storage_mib:10240,max_video_mib:256},
    capabilities:{ffmpeg:true,ffprobe:true},job:{state:'idle',stage:'idle',worker_active:false,total:0,completed:0,percent:0},
    installation:{installed:true,scene_count:8,needs_repair:false,needs_update:false,name:'decky-animated-screensaver'},
    media_tools:{available:true,installed:true,state:'ready'},storage:{used_bytes:1000000,budget_bytes:2147483648,free_bytes:999999999},
    updates:{channel:'stable',auto_check:true,interval_minutes:1440,phase:'current',error:'',auth:{state:'connected',user_code:'',verification_uri:'',expires_at:0},repository:'Alyenax/Decky-Animated-Screensaver',repository_state:'ready',installed_version:'0.1.0-alpha.32',available_version:'0.1.0-alpha.32',available:false,checked_at:1792396800,percent:0,confirmation:''},
    jsaux:{detected:false,compatible:false,configured:false,enabled:false,mode:'sync',transition:'fade',page_seconds:24,framing:'square',phase:'idle',prepared:{ready:false}},
    workspace:{mode:'collection',layout:'comfort',member_count:8,included_count:8,pending_count:0,pending_ids:[],draft_count:0,issues_count:0,task:{state:'idle',worker_active:false}}};
  drafts={};calls=[];gameRunning=false;selectionUndo=null;managementError=false;orderIds=[];orderFailure=false;orderDelay=0;
}
async function rpc(name:string,p:any={}){
  calls.push([name,structuredClone(p)]);
  if(gameRunning&&['workspace_prepare','workspace_install'].includes(name))throw Error(gameRunningCode);
  if(name==='jsaux_refresh'&&p.force===true&&jsauxAfterRefresh){Object.assign(state.jsaux,jsauxAfterRefresh);jsauxAfterRefresh=null;}
  if(name==='settings_snapshot')return {backup:{schema:'das-settings-v1',options:structuredClone(state.options),faceplate:{},interface:{mode:state.workspace.mode,layout:state.workspace.layout}},updates:state.updates,calibration:null,home:'/home/deck'};
  if(name==='settings_export')return {path:'/home/deck/Documents/AnimatedScreensaver/settings.json'};
  if(name==='settings_import')return {restored:true,previous_path:'/home/deck/Documents/AnimatedScreensaver/previous.json'};
  if(name==='state'||name==='jsaux_refresh')return structuredClone(state);
  if(name==='jsaux_configure'){Object.assign(state.jsaux,p.patch);state.jsaux.prepared={...state.jsaux.prepared,ready:false,reason:'PREPARATION_STALE'};state.jsaux.reason='';return structuredClone(state);}
  if(name==='workspace_details'&&detailsFailure){const code=detailsFailure;detailsFailure='';throw Error(code);}
  if(name==='workspace_order'){
    const members=games.map(g=>({...g,...drafts[g.appid]})).filter(g=>g.collection_member);
    const arranged=orderIds.length?[...members].sort((a,b)=>orderIds.indexOf(a.appid)-orderIds.indexOf(b.appid)):members;
    return {revision:arranged.map(g=>g.appid).join(','),items:structuredClone(arranged.map(({appid,name})=>({appid,name})))};
  }
  if(name==='workspace_reorder'){
    if(orderDelay)await new Promise(r=>setTimeout(r,orderDelay));
    if(orderFailure){orderFailure=false;throw Error('collection_change_failed');}
    const snap=await rpc('workspace_order');if(p.revision!==snap.revision)throw Error('collection_order_changed');
    orderIds=[...p.appids];state.installation.needs_update=true;return structuredClone(state);
  }
  if(name==='workspace_preferences'){Object.assign(state.workspace,p.patch);return structuredClone(state);}
  if(name==='workspace_details'||name==='details'||name==='browse_open')return structuredClone({...games.find(g=>g.appid===p.appid),...drafts[p.appid]});
  if(name==='workspace_library'||name==='library'){
    let rows=games.map(g=>({...g,...drafts[g.appid],workspace_draft:!!drafts[g.appid]}));
    if(p.filter==='collection')rows=rows.filter(g=>g.collection_member);
    if(p.filter==='installed')rows=rows.filter(g=>g.installed);
    if(p.filter==='attention')rows=rows.filter(g=>g.problem&&g.problem.code!=='animation_missing');
    if(p.query)rows=rows.filter(g=>g.name.toLowerCase().includes(p.query.toLowerCase()));
    if(p.filter==='installed'||p.filter==='all')rows.sort((a,b)=>a.name.localeCompare(b.name));
    else if(orderIds.length)rows.sort((a,b)=>orderIds.indexOf(a.appid)-orderIds.indexOf(b.appid));
    const size=p.page_size||8,page=Math.min(p.page||0,Math.max(0,Math.ceil(rows.length/size)-1));
    return {items:structuredClone(rows.slice(p.limit?0:page*size,p.limit||(page+1)*size)),total:rows.length,page,page_size:size};
  }
  if(name==='workspace_deselect_all'){
    if(managementError)throw Error('collection_change_failed');
    const selected=games.filter(g=>({...g,...drafts[g.appid]}).collection_member&&!({...g,...drafts[g.appid]}).excluded);
    selectionUndo=structuredClone(drafts);state.workspace.selection_undo={token:'60'.repeat(16),count:selected.length};
    for(const g of selected)drafts[g.appid]={...drafts[g.appid],collection_member:false,excluded:false};
    state.workspace.included_count=0;state.workspace.draft_count=Object.keys(drafts).length;state.workspace.pending_count=0;return structuredClone(state);
  }
  if(name==='workspace_select_all'){
    if(selectionDelay)await new Promise(r=>setTimeout(r,selectionDelay));
    if(selectionFailure){selectionFailure=false;throw Error('collection_change_failed');}
    const matches=games.filter(g=>p.source==='installed'?g.installed&&g.name.toLowerCase().includes((p.query||'').toLowerCase()):p.appids.includes(g.appid));
    for(const g of matches)drafts[g.appid]={...drafts[g.appid],collection_member:true,excluded:false};
    selectionUndo=null;state.workspace.selection_undo=null;
    state.workspace.included_count=games.filter(g=>({...g,...drafts[g.appid]}).collection_member&&!({...g,...drafts[g.appid]}).excluded).length;
    state.workspace.draft_count=Object.keys(drafts).length;state.workspace.pending_count=state.workspace.draft_count;state.workspace.pending_ids=Object.keys(drafts).map(Number);return structuredClone(state);
  }
  if(name==='workspace_undo_selection'){
    if(p.token!==state.workspace.selection_undo?.token)throw Error('selection_undo_expired');
    drafts=structuredClone(selectionUndo);state.workspace.selection_undo=null;state.workspace.included_count=games.filter(g=>({...g,...drafts[g.appid]}).collection_member&&!({...g,...drafts[g.appid]}).excluded).length;
    state.workspace.draft_count=Object.keys(drafts).length;state.workspace.pending_count=state.workspace.draft_count;return structuredClone(state);
  }
  if(name==='workspace_delete_collection'){
    if(!p.confirm)throw Error('confirmation_required');if(managementError)throw Error('collection_change_failed');
    games.forEach(g=>Object.assign(g,{collection_member:false,excluded:false,installed_in_collection:false}));drafts={};selectionUndo=null;
    Object.assign(state.workspace,{selection_undo:null,included_count:0,member_count:0,draft_count:0,pending_count:0,pending_ids:[],task:{state:'idle',worker_active:false}});
    Object.assign(state.installation,{installed:false,scene_count:0,needs_update:false});state.jsaux.installed=false;return structuredClone(state);
  }
  if(name==='workspace_draft'){
    selectionUndo=null;state.workspace.selection_undo=null;
    if(p.reconcile_membership&&selectionDelay)await new Promise(r=>setTimeout(r,selectionDelay));
    if(p.reconcile_membership&&selectionFailure){selectionFailure=false;throw Error('storage_limit');}
    drafts[p.appid]={...drafts[p.appid],...p.patch};
    if(p.reconcile_membership){const base=games.find(g=>g.appid===p.appid);if(!p.patch.collection_member&&!base.collection_member)drafts[p.appid].excluded=Boolean(base.excluded);for(const key of ['collection_member','excluded'])if(drafts[p.appid][key]===Boolean(base?.[key]))delete drafts[p.appid][key];if(!Object.keys(drafts[p.appid]).length)delete drafts[p.appid];}
    state.workspace.included_count=games.filter(g=>({...g,...drafts[g.appid]}).collection_member&&!({...g,...drafts[g.appid]}).excluded).length;
    state.workspace.draft_count=Object.keys(drafts).length;
    state.workspace.pending_count=state.workspace.draft_count;state.workspace.pending_ids=Object.keys(drafts).map(Number);
    return structuredClone(state);
  }
  if(name==='candidates'||name==='browse_candidates')return Array.from({length:candidateMany?8:1},(_,i)=>({id:(p.role==='animation'?100:p.role==='cover'?200:p.role==='logo'?300:400)+i,width:candidateSquare?1024:460,height:candidateSquare?1024:215,thumb:candidateThumb||games.find(g=>g.appid===p.appid)?.thumbnail_url,animated:p.role==='animation',author:'Browser fixture',url:`https://cdn.steamgriddb.com/test${i}.gif`}));
  if(name==='candidate_preview'){
    if(p.motion){if(candidateMotionError)throw Error('source_limit');return {source_url:`http://127.0.0.1:${location.port}/${'a'.repeat(40)}/${'c'.repeat(24)}`,source_format:'gif',derivative:true};}
    const canvas=document.createElement('canvas');canvas.width=32;canvas.height=candidateSquare?32:24;
    const context=canvas.getContext('2d')!;context.fillStyle=p.asset_id%2?'#ec428c':'#438dcf';context.fillRect(0,0,canvas.width,canvas.height);
    return {still:canvas.toDataURL('image/jpeg'),derivative:true};
  }
  if(name==='workspace_prepare'||name==='workspace_install'){
    state.workspace.task={state:name==='workspace_prepare'?'preparing':'applying',worker_active:true};state.job={...state.job,state:'running',stage:'checking',worker_active:true,total:8,completed:0,percent:0};return structuredClone(state);
  }
  if(name==='pause'||name==='resume'||name==='cancel'){
    Object.assign(state.job,{state:name==='resume'?'running':name==='pause'?'paused':'cancelled',worker_active:name==='resume'});
    Object.assign(state.workspace.task,{state:name==='cancel'?'cancelled':name==='pause'?'paused':'preparing',worker_active:name!=='cancel'});return structuredClone(state);
  }
  if(name==='preview'||name==='preview_recipe'||name==='preview_installed')return {url:`http://127.0.0.1:${location.port}/${'a'.repeat(40)}/${'b'.repeat(24)}`,nonce:'fixture',count:name==='preview_recipe'||p.appid?1:8,...(p.artwork_only?{source_url:`http://127.0.0.1:${location.port}/${'a'.repeat(40)}/${'c'.repeat(24)}`,source_format:'gif'}:{})};
  if(name==='close_preview')return {};
  if(name==='browse_search'){if(p.query==='offline')throw Error('search_unavailable');if(p.query==='slow')await new Promise(r=>setTimeout(r,900));return {items:games.filter(g=>g.name.toLowerCase().includes(p.query.toLowerCase())||p.query==='slow').map(g=>({...g,...drafts[g.appid]})),total:12};}
  if(name==='browse_top'){if(topFailures-->0)return {schema:'das-discovery-error-v1',ok:false,error:'steam_tls_unavailable'};return {items:games.map((g,i)=>({...g,...drafts[g.appid],rank:i+1,players:100000-i*1000})),total:12,at:1792396800};}
  if(name==='search')return [{id:1000,name:'Test game'}];
  if(name==='configure'){Object.assign(state.options,p.patch);return structuredClone(state);}
  if(name==='workspace_scan'||name==='scan')return structuredClone(state);
  if(name==='diagnostic')return {saved:true,path:'/home/deck/.config/AnimatedScreensaver/diagnostic.json',report:{fixture:true,jsaux_delivery:{stages:{},player_debug:{}}}};
  return structuredClone(state);
}
(window as any).__dasNestedScroll=true;(window as any).__collectionRpc=async(name:string,p:any)=>discoveryResponse(name,await rpc(name,p));
async function mount(lang='fr',options:any={}){
  reset();(window as any).__dasQamVisible=!options.hiddenQuick;localStorage.removeItem('das-interface-mode');sessionStorage.removeItem('das-collection-launch');
  topFailures=options.topError?1:0;candidateThumb=options.candidateThumb||'';candidateSquare=!!options.square;candidateMany=!!options.candidateMany;candidateMotionError=!!options.motionError;
  detailsFailure=options.detailsFailure||'';selectionFailure=Boolean(options.selectionFailure);selectionDelay=options.selectionDelay||0;
  (window as any).__dasDialogTag=options.native?'div':'button';if(options.add)sessionStorage.setItem('das-collection-launch','add');
  if(options.update)Object.assign(state.updates,options.update);
  publishUpdate(state.updates);
  if(options.classic){localStorage.setItem('das-interface-mode','classic');state.workspace.mode='classic';}
  if(options.busy){state.workspace.task={state:'preparing',worker_active:true};state.job={state:'running',stage:'checking',worker_active:true,total:8,completed:2,percent:25};}
  gameRunning=Boolean(options.gameRunning);gameRunningCode=options.gameRunningCode||'GAME_RUNNING';managementError=Boolean(options.managementError);
  orderFailure=Boolean(options.orderFailure);orderDelay=options.orderDelay||0;
  if(options.manyOrder){for(let i=0;i<24;i++)games.push({...games[0],appid:9000+i,name:'Order game '+i,thumbnail_url:''});state.workspace.member_count=32;state.workspace.included_count=32;}
  if(options.missing){state.key_configured=false;state.connection='missing';state.media_tools.available=false;state.workspace.pending_count=2;}
  if(options.error){games[0].problem={appid:ids[0],name:names[0],code:'decode_failed',role:'animation',retained_media:true};state.workspace.issues_count=1;}
  if(options.skipped){Object.assign(games[0],{status:'skipped',skip_reason:'no_animation',error:'animation_missing',media:{},problem:{appid:ids[0],name:names[0],code:'animation_missing',role:'animation',retained_media:false}});state.workspace.skipped_count=1;state.ready_count=7;}
  if(options.skippedVisual){Object.assign(games[0],{status:'error',error:'worker_signal',media:{},problem:{appid:ids[0],name:names[0],code:'worker_signal',role:options.skippedVisual===true?'animation':options.skippedVisual,retained_media:false,skipped:true}});state.workspace.issues_count=1;state.workspace.skipped_visual_count=1;state.job.skipped_count=1;state.ready_count=7;}
  if(options.jsaux)state.jsaux={...state.jsaux,detected:true,compatible:true,configured:true,enabled:true,reason:'JSAUX_SYNC_WINDOW',prepared:{ready:true,sync_admissible:false}};
  if(options.jsauxState)state.jsaux={...state.jsaux,...options.jsauxState};
  jsauxAfterRefresh=options.jsauxAfterRefresh||null;
  if(options.jsauxPhase)state.jsaux={...state.jsaux,phase:options.jsauxPhase,worker_active:false};
  if(options.first){state.installation={...state.installation,installed:false,scene_count:0};state.ready_count=0;state.workspace.pending_count=8;}
  if(options.pending)state.workspace.pending_count=2;
  if(options.discoveryOnly)games.forEach(g=>g.installed=false);
  if(options.emptyCollection){state.workspace.member_count=0;state.workspace.included_count=0;games.forEach(g=>g.collection_member=false);}
  if(options.task){state.workspace.task={worker_active:false,error:'',...options.task};state.job={...state.job,state:'complete'};}
  if(options.task?.outcome==='empty'){state.installation.installed=false;state.installation.scene_count=0;state.ready_count=0;state.workspace.skipped_count=8;}
  if(options.sceneCount!==undefined)state.installation.scene_count=options.sceneCount;
  if(options.jobState)state.job.state=options.jobState;
  if(options.needsUpdate)state.installation.needs_update=true;
  const images=await Promise.all(ids.map(async id=>{const r=await fetch(`/images/${id}.jpg`);const b=await r.blob();return new Promise<string>(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.readAsDataURL(b);});}));
  games.forEach((g,i)=>{g.thumbnail_url=images[i];if(options.unprepared){g.media={};g.status='pending';g.installed_in_collection=false;}});
  setLanguage(lang);generation++;
  root.render(options.quick?<QuickShell key={generation} open={(tab)=>calls.push(['open',{tab}])} openUpdates={()=>calls.push(['open-updates',{}])}/>:<StudioRoute key={generation}><StudioShell tab={options.activity?'preparation':'library'}/></StudioRoute>);
}
(window as any).__collection={mount,update:(patch:any)=>{Object.assign(state.updates,patch);publishUpdate(state.updates);},calls:()=>calls,patch:(value:any)=>{Object.assign(state,value);},state:()=>state,drafts:()=>drafts,images:(sources:string[])=>root.render(<div>{sources.map(src=><ArtworkImage key={src} src={src} alt="Test"/>)}</div>),imageReport:artworkDiagnostic,
 popup:()=>{const popup=window.open('about:blank','das-preview-owner');if(!popup)throw Error('No popup');const node=popup.document.createElement('div');popup.document.body.append(node);const popupRoot=createRoot(node);popupRoot.render(<Player preview={{url:`http://127.0.0.1:${location.port}/${'a'.repeat(40)}/${'b'.repeat(24)}`,nonce:'fixture',count:3,revision:'test'}} client={async()=>({}) as any} onClose={()=>popup.close()}/>);}};
void mount();
