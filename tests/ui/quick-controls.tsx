// Actual GCA compact stylesheet vs production DAS QAM. Only native controls/RPC are adapted.
import {createRoot} from 'react-dom/client';
import {DialogButton} from '@decky/ui';
import {TbSettings} from 'react-icons/tb';
import {CollectionQuick} from '../../src/CollectionStudio';
import {QuickHeader} from '../../src/QuickControls';
import {setLanguage} from '../../src/i18n';
import {publishUpdate} from '../../src/update_notice';
import {COMPACT_QUICK_CSS} from 'gca-compact-style';
import {QuickAction as GCAAction,QUICK_CONTROL_CSS} from 'gca-reference-action';
const root=createRoot(document.getElementById('root')!);
function show(lang='en',matrix=true,phase='current'){
 setLanguage(lang);const t=(en:string,fr:string)=>lang==='fr'?fr:en,noop=()=>{};
 const known=phase!=='current';const updates={channel:'private',phase:phase==='expired'?'error':phase,installed_version:'0.1.0-alpha.47',available_version:known?'0.1.0-alpha.48':'',available:known,auth:{state:phase==='expired'?'expired':'connected'}};
 const data={key_configured:true,connection:'verified',ready_count:6,included_count:6,failed_count:0,
  workspace:{member_count:6,included_count:6,pending_count:0,task:{state:'idle',worker_active:false}},
  job:{state:'idle',stage:'idle',worker_active:false},installation:{installed:true},media_tools:{available:true},updates,
  jsaux:{detected:matrix,compatible:matrix,configured:matrix,enabled:matrix,installed:true,phase:'idle',mode:'async',prepared:{ready:true}}};
 publishUpdate(updates as any);
 const label=known?t(phase==='ready'?'Update ready':'Update available',phase==='ready'?'Mise à jour prête':'Mise à jour disponible')+' · 0.1.0-alpha.48':t('Updates','Mises à jour');
 const refAction=(text:string)=><GCAAction onClick={noop}>{text}</GCAAction>;
 (window as any).__quickCalls=[];
 root.render(<main><style>{QUICK_CONTROL_CSS}{COMPACT_QUICK_CSS}</style>
 <article><h1>GCA Lab189 · actual compact stylesheet</h1><div className="gca-compact-title" style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8,width:'100%',minWidth:0}}><span>Animated Screensaver</span><DialogButton className="gca-quick-gear" noFocusRing style={{width:32,height:32,minWidth:0,minHeight:32,padding:0,flexShrink:0,display:'flex',alignItems:'center',justifyContent:'center'}}><TbSettings size={19}/></DialogButton></div>
 <div id="gca-compact-root">{known?<section>{refAction(label)}</section>:null}<section><div className="reference-status">{t('Collection installed','Collection installée')}<small>{matrix?t('JSAUX · connected','JSAUX · connectée'):''}</small></div>{refAction(t('Open my collection','Ouvrir ma collection'))}</section><section>{refAction(t('Add games','Ajouter des jeux'))}{refAction(t('Settings','Réglages'))}</section></div></article>
 <article><h1>DAS · actual CollectionQuick</h1><QuickHeader title="Animated Screensaver" onOpenSettings={()=>(window as any).__quickCalls.push(['gear','settings'])}/><CollectionQuick key={lang+matrix+phase} client={async()=>structuredClone(data) as any} open={tab=>(window as any).__quickCalls.push(['open',tab])} onOpenUpdates={()=>(window as any).__quickCalls.push(['updates'])}/></article>
 </main>);
}
show();(window as any).__parity={show};
