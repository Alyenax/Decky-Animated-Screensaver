import {useCallback,useEffect,useRef,useState} from 'react';
import {DialogButton,Focusable} from '@decky/ui';
import type {StudioClient,StudioState,StudioPreview} from './types';
import {studioPreviewURL} from './types';
import {shouldPoll} from './model';
import {tr,errorText} from './i18n';
import {publishUpdate} from './update_notice';
import {safeErrorCode,type Failure} from './recovery';
export function useStudio(client:StudioClient,discoverOnOpen=true,visible=true){
  const [state,setState]=useState<StudioState|null>(null),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  const [failure,setFailure]=useState<Failure|null>(null);
  const alive=useRef(true),locked=useRef(false),sequence=useRef(0),discoveryAt=useRef(0);
  const failureSource=useRef<'refresh'|'action'|null>(null);
  const refresh=useCallback(async(discover=false)=>{
    const id=++sequence.current;if(discover)discoveryAt.current=Date.now();
    try{const value=await client(discover?'jsaux_refresh':'state');if(alive.current && id===sequence.current){setState(value);if(value.updates)publishUpdate(value.updates);
      if(failureSource.current==='refresh'){failureSource.current=null;setError('');setFailure(null);}}}
    catch(e){if(alive.current && id===sequence.current && failureSource.current!=='action'){failureSource.current='refresh';setError(errorText(String(e)));setFailure({code:safeErrorCode(e),action:'state'});}}
  },[client]);
  useEffect(()=>{alive.current=true;if(visible)void refresh(discoverOnOpen);return()=>{alive.current=false;sequence.current++;};},[refresh,discoverOnOpen,visible]);
  const run=useCallback(async<T=StudioState,>(name:string,payload:Record<string,unknown>={}):Promise<T|undefined>=>{
    if(['pause','cancel','resume'].includes(name)){
      const id=++sequence.current;
      try{const result=await client<T>(name,payload);if(alive.current&&id===sequence.current)setState(result as unknown as StudioState);return result;}
      catch(e){if(alive.current){failureSource.current='action';setError(errorText(String(e)));setFailure({code:safeErrorCode(e),action:name});}return undefined;}
    }
    if(locked.current)return;
    locked.current=true;sequence.current++;setSaving(true);failureSource.current=null;setError('');setFailure(null);
    const ticket=sequence.current;
    try{const result=await client<T>(name,payload);if(!alive.current || ticket!==sequence.current)return undefined;if(alive.current){
      if(result && typeof result==='object' && 'job' in result){setState(result as unknown as StudioState);const update=(result as unknown as StudioState).updates;if(update)publishUpdate(update);}
      else if(!['preview','preview_installed','close_preview','diagnostic','library','candidates','search'].includes(name))await refresh();
    }return result;}
    catch(e){if(alive.current){failureSource.current='action';setError(errorText(String(e)));setFailure({code:safeErrorCode(e),action:name,
      appid:typeof payload.appid==='number'&&Number.isSafeInteger(payload.appid)?payload.appid:undefined,
      role:typeof payload.role==='string'?payload.role:undefined});}return undefined;}
    finally{locked.current=false;if(alive.current)setSaving(false);}
  },[client,refresh]);
  const polling=shouldPoll(state);
  useEffect(()=>{if(state)window.dispatchEvent(new CustomEvent('das-jsaux-availability',{detail:{enabled:Boolean(state.jsaux?.relay_enabled),transport:state.jsaux?.relay_transport}}));},[state?.jsaux?.relay_enabled,state?.jsaux?.relay_transport]);
  useEffect(()=>{
    if(!visible)return;
    let stop=false;let timer:ReturnType<typeof setTimeout>;
    const tick=async()=>{if(document.visibilityState!=='hidden'&&!locked.current)await refresh(Date.now()-discoveryAt.current>=5000);if(!stop)timer=setTimeout(()=>void tick(),polling?1200:5000);};
    timer=setTimeout(()=>void tick(),polling?1200:5000);
    return()=>{stop=true;clearTimeout(timer);};
  },[polling,refresh,visible]);
  return {state,error,failure,saving,run,refresh,clearError:()=>{failureSource.current=null;setError('');setFailure(null);}};
}
export function Player({preview,client,onClose,compact=false}:{preview:StudioPreview;client:StudioClient;onClose:()=>void;compact?:boolean}){
  const frame=useRef<HTMLIFrameElement>(null);
  const [playing,setPlaying]=useState(true),[error,setError]=useState('');
  const url=studioPreviewURL(preview.url);
  const send=useCallback((action:string)=>{if(url&&frame.current?.getAttribute('src')===url)frame.current.contentWindow?.postMessage({type:'screensaver',action,nonce:preview.nonce},new URL(url).origin);},[url,preview.nonce]);
  useEffect(()=>{
    setError('');
    const host=frame.current?.ownerDocument.defaultView||window;
    let attempts=0;const handshake=setInterval(()=>{if(++attempts<=4)send('status');else clearInterval(handshake);},1500);
    const receive=(event:MessageEvent)=>{
      if(!url||event.source!==frame.current?.contentWindow||event.origin!==new URL(url).origin||event.data?.nonce!==preview.nonce)return;
      if(event.data.type!=='screensaver-player')return;
      if(['playing','paused','media-error'].includes(event.data.status))clearInterval(handshake);
      if(event.data.status==='media-error')setError(tr('This animation cannot be played.','Cette animation ne peut pas être lue.'));
      else if(['playing','paused'].includes(event.data.status)){setPlaying(event.data.status==='playing');setError('');}
    };
    host.addEventListener('message',receive);
    // Subscribe before navigation; a warm iframe can otherwise answer too early.
    if(frame.current&&url)frame.current.src=url;
    return()=>{clearInterval(handshake);send('pause');host.removeEventListener('message',receive);void client('close_preview',{nonce:preview.nonce}).catch(()=>{});};
  },[url,preview.nonce,send,client]);
  return <div className="box collection-player">
    {url?<div className="collection-player-stage"><iframe className="player" ref={frame} onLoad={()=>send('status')} title={tr('Screensaver preview','Aperçu de l’écran de veille')} tabIndex={-1} allow="autoplay"/></div>:<p role="alert">{tr('Invalid preview address','Adresse d’aperçu invalide')}</p>}
    {!compact&&<Focusable className="collection-player-controls" flow-children="row">
      <DialogButton style={{width:'auto',minWidth:0,flex:'1 1 0'}} onClick={()=>send('previous')}>{tr('Previous','Précédent')}</DialogButton>
      <DialogButton style={{width:'auto',minWidth:0,flex:'1 1 0'}} onClick={()=>send(playing?'pause':'play')}>{playing?tr('Pause','Pause'):tr('Play','Lecture')}</DialogButton>
      <DialogButton style={{width:'auto',minWidth:0,flex:'1 1 0'}} onClick={()=>send('next')}>{tr('Next','Suivant')}</DialogButton>
      <DialogButton style={{width:'auto',minWidth:0,flex:'1 1 0'}} onClick={onClose}>{tr('Close','Fermer')}</DialogButton>
    </Focusable>}
    {error&&<p className="error" role="alert">{error}</p>}
  </div>;
}
