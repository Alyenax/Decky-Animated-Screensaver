import {useEffect,useState} from 'react';
import {ArtworkImage} from './ArtworkImage';
import {studioPreviewURL,type StudioAsset,type StudioClient} from './types';
import {tr} from './i18n';

type Result={still?:string;source_url?:string;source_format?:string};
const stills=new Map<string,string>();
const queue:{alive:()=>boolean;run:()=>Promise<void>}[]=[];let running=false;
const id=()=>Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16).padStart(8,'0')).join('');
async function pump(){if(running)return;running=true;try{while(queue.length){const next=queue.shift()!;if(next.alive())await next.run();}}finally{running=false;}}
function enqueue(alive:()=>boolean,run:()=>Promise<void>,priority=false){for(let i=queue.length-1;i>=0;i--)if(!queue[i].alive())queue.splice(i,1);if(priority)queue.unshift({alive,run});else queue.push({alive,run});void pump();}
async function load(client:StudioClient,payload:Record<string,unknown>,alive:()=>boolean):Promise<Result|null>{
 for(let attempt=0;alive();attempt++){
  try{return await client<Result>('candidate_preview',payload);}
  catch(error){if(!['busy','worker_busy','preview_cancelled'].includes(String(error).replace(/^Error:\s*/,''))||attempt>=6)throw error;await new Promise(r=>setTimeout(r,250*(attempt+1)));}
 }
 return null;
}

/** Every visible card gets a tiny backend still. Only focus admits motion. */
export function CandidateArtwork({asset,appid,role,active,client}:{asset:StudioAsset;appid:number;role:string;active:boolean;client:StudioClient}){
 const key=asset.url+'|'+asset.thumb;
 const [still,setStill]=useState(stills.get(key)||''),[value,setValue]=useState<Result|null>(null),[ready,setReady]=useState(false),[error,setError]=useState(false),[stillError,setStillError]=useState(false);
 useEffect(()=>{
  let alive=true;const request_id=id();setStill(stills.get(key)||'');setStillError(false);
  if(!stills.has(key))enqueue(()=>alive,async()=>{
   try{const result=await load(client,{appid,role,asset_id:asset.id,request_id},()=>alive);if(alive&&result?.still){stills.set(key,result.still);while(stills.size>40)stills.delete(stills.keys().next().value!);setStill(result.still);}}
   catch{if(alive)setStillError(true);}
  });
  return()=>{alive=false;void client('close_preview',{request_id}).catch(()=>{});};
 },[key,appid,role,asset.id,client]);
 useEffect(()=>{
  setValue(null);setReady(false);setError(false);if(!active||!asset.animated)return;
  let alive=true;const request_id=id();
  const timer=setTimeout(()=>enqueue(()=>alive,async()=>{
   try{const result=await load(client,{appid,role,asset_id:asset.id,motion:true,request_id},()=>alive);if(alive)setValue(result);}
   catch{if(alive)setError(true);}
  },true),350);
  return()=>{alive=false;clearTimeout(timer);void client('close_preview',{request_id}).catch(()=>{});};
 },[appid,role,asset.id,asset.animated,active,client]);
 const url=value?.source_url&&studioPreviewURL(value.source_url);
 const motionFailed=()=>{setReady(false);setError(true);setValue(null);};
 return <span className="candidate-artwork">
  {still?<ArtworkImage src={still} alt={tr('Artwork thumbnail','Vignette du visuel')}/>:<span className="collection-picture candidate-placeholder">{stillError?tr('Preview unavailable · artwork can still be selected','Aperçu indisponible · ce visuel reste sélectionnable'):tr('Loading image…','Chargement de l’image…')}</span>}
  {url&&(['webm','mp4'].includes(value?.source_format||'')?<video className="candidate-motion" src={url} autoPlay muted loop playsInline tabIndex={-1} onLoadedData={()=>setReady(true)} onError={motionFailed} style={{visibility:ready?'visible':'hidden'}}/>:<img className="candidate-motion" src={url} alt={tr('Animated artwork','Visuel animé')} onLoad={()=>setReady(true)} onError={motionFailed} style={{visibility:ready?'visible':'hidden'}}/>)}
  {active&&asset.animated&&!ready&&<span className="candidate-animation-state" role="status">{error?tr('Still preview · original remains selectable','Aperçu fixe · l’original reste sélectionnable'):tr('Loading animation…','Chargement de l’animation…')}</span>}
  {asset.animated&&<small className="candidate-animation-badge">{active&&ready?tr('Playing','Lecture'):tr('Animated','Animé')}</small>}
 </span>;
}
