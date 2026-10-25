/** Process-local transport evidence only. Never retain a message, URL or ID. */
type FrameCount='received'|'rejected'|'routed'|'replied'|'errors';
type StorageCount='probes'|'received'|'rejected'|'routed'|'replied'|'read_errors'|'write_errors'|'backend_errors';
export type RelayCode=''|'UNTRUSTED_ORIGIN'|'FRAME_NOT_FOUND'|'INVALID_MESSAGE'|'STALE_MESSAGE'|'BUSY'|'NO_SESSION'|'DISPOSED'|'INVALID_STORAGE'|'STALE_STORAGE'|'READ_FAILED'|'WRITE_FAILED'|'BACKEND_FAILED';
const frame={installed:false,received:0,rejected:0,routed:0,replied:0,errors:0,last_error:'' as RelayCode,last_rejection:'' as RelayCode};
const storage={available:false,running:false,probes:0,received:0,rejected:0,routed:0,replied:0,read_errors:0,write_errors:0,backend_errors:0,last_error:'' as RelayCode,last_rejection:'' as RelayCode,last_error_name:'',last_native_result:null as number|null};
const recovery={requested:0,failed:0};let enabled=false;
const bump=(n:number)=>Math.min(999999,n+1);
export function relayEnabled(value:boolean){enabled=value;}
export function frameInstalled(value:boolean){frame.installed=value;}
export function storageAvailable(value:boolean){storage.available=value;}
export function storageRunning(value:boolean){storage.running=value;}
export function frameCount(key:FrameCount){frame[key]=bump(frame[key]);}
export function storageCount(key:StorageCount){storage[key]=bump(storage[key]);}
export function frameReject(code:RelayCode){frameCount('rejected');frame.last_rejection=code;return false;}
export function storageReject(code:RelayCode){storageCount('rejected');storage.last_rejection=code;return false;}
export function frameError(code:RelayCode){frameCount('errors');frame.last_error=code;}
export function storageError(key:'read_errors'|'write_errors'|'backend_errors',code:RelayCode,error?:unknown){
  storageCount(key);storage.last_error=code;storage.last_error_name='Unknown';storage.last_native_result=null;
  try{
    const native=error as {name?:unknown;eresult?:unknown;result?:unknown}|undefined;
    if(typeof native?.name==='string'&&['Error','TypeError','ReferenceError','RangeError','SyntaxError','DOMException','AbortError','SecurityError','NotAllowedError'].includes(native.name))storage.last_error_name=native.name;
    const result=native?.eresult??native?.result;
    if(typeof result==='number'&&Number.isInteger(result)&&result>=0&&result<=999){storage.last_native_result=result;if(storage.last_error_name==='Unknown')storage.last_error_name='OperationResponse';}
  }catch{}
}
export function relayRecovery(failed=false){const key=failed?'failed':'requested';recovery[key]=bump(recovery[key]);}
export function getJsauxRelayDiagnostic(){
  return {schema:'das-jsaux-relay-v1',enabled,iframe:{...frame},storage:{...storage},recovery:{...recovery}};
}
