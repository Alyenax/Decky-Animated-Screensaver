// No URL, game name, query string or key is retained in image diagnostics.
type Stage='blocked'|'load'|'ready'|'error'|'timeout'|'snapshot'|'snapshot_failed';
const counts:Partial<Record<Stage,number>>={},events:{stage:Stage;source:string;format:string}[]=[];
export function imageLocation(value?:string){
 try{const u=new URL(value||'');return {source:u.protocol==='data:'?'local':u.hostname==='s3.amazonaws.com'&&u.pathname.startsWith('/steamgriddb/thumb/')?'sgdb_legacy':u.hostname==='steamgriddb.s3.amazonaws.com'?'sgdb_legacy':u.hostname==='steamgriddb.com'||u.hostname.endsWith('.steamgriddb.com')?'sgdb':u.hostname.endsWith('.steamstatic.com')?'steam':'other',format:u.protocol==='data:'?'data':u.pathname.match(/\.(png|jpe?g|webp|gif)$/i)?.[1]?.toLowerCase()||'other'};}catch{return {source:'other',format:'other'};}
}
export function imageEvent(stage:Stage,value?:string){counts[stage]=Math.min(999999,(counts[stage]||0)+1);events.push({stage,...imageLocation(value)});if(events.length>24)events.shift();}
export function artworkDiagnostic(){return {schema:'das-artwork-load-v1',counts:{...counts},events:events.map(e=>({...e}))};}
