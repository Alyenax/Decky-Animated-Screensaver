import {CollectionQuick,CollectionStudio} from './CollectionStudio';
import type {Tab} from './model';
export function StudioShell({tab,updates=false,attention=false}:{tab:Tab;updates?:boolean;attention?:boolean}){
return <CollectionStudio focusUpdates={updates} initialAttention={attention} initial={tab==='preview'?'preview':tab==='preparation'?'activity':tab==='settings'||tab==='advanced'?'settings':'collection'}/>;
}
export function QuickShell({open,openUpdates}:{open:(tab:Tab,attention?:boolean)=>void;openUpdates?:()=>void}){
return <CollectionQuick onOpenUpdates={openUpdates} open={tab=>{if(tab==='settings')try{sessionStorage.setItem('das-collection-launch','add');}catch{}open(tab==='settings'?'library':tab);}}/>;
}
