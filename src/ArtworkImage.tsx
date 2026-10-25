import {useEffect,useRef,useState} from 'react';
import {safeImage} from './model';
import {tr} from './i18n';
import {imageEvent} from './artworkDiagnostic';

// Shared two-slot pool for visible images and up to four prefetched stills.
// No GIF/video preloading. WebP thumbnails are drawn once to a display-only
// canvas: no animation loop, pixel export or CORS requirement.
const cache=new Map<string,string>();let active=0;
const queue:{start:()=>void;alive:()=>boolean}[]=[];
const retain=(url:string,shown:string)=>{cache.set(url,shown);while(cache.size>40)cache.delete(cache.keys().next().value!);};
const webp=(url:string)=>/\.(?:webp|gif)(?:\?|$)/i.test(url);
function pump(){while(active<2&&queue.length){const item=queue.shift()!;if(item.alive())item.start();}}
function enqueue(url:string,alive:()=>boolean,done:(ok:boolean)=>void,canvas?:HTMLCanvasElement|null){
 for(let i=queue.length-1;i>=0;i--)if(!queue[i].alive())queue.splice(i,1);
 queue.push({alive,start:()=>{
  active++;imageEvent('load',url);const image=new Image();let finished=false;let timer:ReturnType<typeof setTimeout>;
  const finish=(ok:boolean)=>{if(finished)return;finished=true;clearTimeout(timer);image.onload=null;image.onerror=null;image.removeAttribute('src');active--;
   if(ok){if(!webp(url))retain(url,url);imageEvent('ready',url);}if(alive())done(ok);pump();};
  image.onload=()=>{
   if(!image.naturalWidth||image.naturalWidth*image.naturalHeight>2000000){imageEvent('error',url);finish(false);return;}
   if(webp(url)){
    try{if(!canvas||!alive())throw Error('disposed');const scale=Math.min(1,320/image.naturalWidth,180/image.naturalHeight);canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));const context=canvas.getContext('2d');if(!context)throw Error('canvas');context.drawImage(image,0,0,canvas.width,canvas.height);imageEvent('snapshot',url);}
    catch{imageEvent('snapshot_failed',url);finish(false);return;}
   }
   finish(true);
  };
  image.onerror=()=>{imageEvent('error',url);finish(false);};timer=setTimeout(()=>{imageEvent('timeout',url);finish(false);},5000);image.src=url;
 }});pump();
}
export function preloadArtwork(sources:(string|undefined)[],alive:()=>boolean){
 for(const source of [...new Set(sources)].slice(0,4)){
  const url=safeImage(source);if(!url||webp(url)||cache.has(url))continue;
  // Only actual thumbnail paths or bounded local images, never a missing
  // thumbnail's full-resolution source fallback.
  if(!url.startsWith('data:')&&!/\/(?:thumb|thumbs|grid_thumb|hero_thumb|logo_thumb|icon_thumb)\//.test(new URL(url).pathname))continue;
  enqueue(url,alive,()=>{});
 }
}
export function ArtworkImage({src,alt='',className='',fallback=''}:{src?:string;alt?:string;className?:string;fallback?:string}){
 const url=safeImage(src)||'',backup=safeImage(fallback)||'';
 const [current,setCurrent]=useState(url),[loaded,setLoaded]=useState(false),[failed,setFailed]=useState(false);
 const canvas=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{if(src&&!url)imageEvent('blocked',src);},[src,url]);
 useEffect(()=>{setCurrent(url);},[url]);
 useEffect(()=>{
  let alive=true;setLoaded(false);setFailed(false);
  if(!current){setFailed(true);return;}
  if(cache.has(current)){setLoaded(true);return;}
  enqueue(current,()=>alive,ok=>{if(!ok&&backup&&backup!==current)setCurrent(backup);else{setLoaded(ok);setFailed(!ok);}},canvas.current);
  return()=>{alive=false;};
 },[current,backup]);
 return <span className={'collection-picture '+className} data-image-state={failed?'missing':loaded?'ready':'loading'}>
  {webp(current)&&<canvas ref={canvas} role="img" aria-label={alt} style={{display:loaded?'block':'none'}}/>}
  {loaded?(!webp(current)&&<img src={current} alt={alt} onError={()=>{cache.delete(current);imageEvent('error',current);setLoaded(false);if(backup&&backup!==current)setCurrent(backup);else setFailed(true);}}/>):<span>{failed?tr('Image unavailable','Image indisponible')+(alt?' · '+alt:''):tr('Loading image…','Chargement de l’image…')}</span>}
 </span>;
}
