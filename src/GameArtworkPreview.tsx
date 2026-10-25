import type {ReactNode} from 'react';
import {useEffect,useRef,useState} from 'react';
import {ToggleField} from '@decky/ui';
import {Player} from './StudioRuntime';
import {ArtworkImage} from './ArtworkImage';
import {tr,errorText} from './i18n';
import type {StudioClient,StudioGame,StudioPreview} from './types';

/** Same player as Steam, source bytes on demand. Never prepares or writes USB. */
export function GameArtworkPreview({game,patch,client,membershipControl}:{game:StudioGame;patch:Record<string,unknown>;client:StudioClient;membershipControl?:ReactNode}){
 const [preview,setPreview]=useState<StudioPreview|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const sequence=useRef(0);
 const [prepared,setPrepared]=useState(false);
 const latest=useRef(patch);latest.current=patch;
 const recipe=prepared?'installed':JSON.stringify({choices:patch.choices,crop:patch.crop,still_mode:patch.still_mode,branding:patch.branding,cover_position:patch.cover_position});
 useEffect(()=>{
  const id=++sequence.current;let alive=true;
  const request_id=Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16).padStart(8,'0')).join('');
  setPreview(null);setLoading(true);setError('');
  // Unmount the old player first: its cleanup must not close the next server.
  const timer=setTimeout(()=>{
   void client<StudioPreview>(prepared?'preview_installed':'preview_recipe',{appid:game.appid,...(!prepared?{patch:latest.current}:{}),request_id}).then(value=>{
    if(alive&&id===sequence.current)setPreview(value);
   }).catch(e=>{if(alive&&id===sequence.current)setError(errorText(String(e)));})
   .finally(()=>{if(alive&&id===sequence.current)setLoading(false);});
  },80);
  return()=>{alive=false;sequence.current++;clearTimeout(timer);void client('close_preview',{request_id}).catch(()=>{});};
 },[game.appid,recipe,prepared,client]);
 return <section className="collection-sheet-preview" aria-label={tr('Animated artwork preview','Aperçu animé du visuel')}>
  {preview?<Player preview={preview} client={client} compact onClose={()=>setPreview(null)}/>:<ArtworkImage className="collection-detail-image" src={game.thumbnail_url} alt={game.name}/>}
  {membershipControl}
  {loading&&<p role="status">{tr('Loading animation…','Chargement de l’animation…')}</p>}
  {error&&<p role="status">{error}</p>}
  {game.installed_in_collection&&<ToggleField label={tr('Compare installed version','Comparer la version installée')} checked={prepared} disabled={loading} onChange={setPrepared}/>}
 </section>;
}
