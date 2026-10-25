"""Untrusted frontend health -> strict metadata allowlist, only on explicit export."""

COUNTERS={'received','rejected','routed','replied','errors','probes','read_errors','write_errors','backend_errors','requested','failed'}
FLAGS={'installed','available','running'}
CODES={'','UNTRUSTED_ORIGIN','FRAME_NOT_FOUND','INVALID_MESSAGE','STALE_MESSAGE','BUSY',
       'NO_SESSION','DISPOSED','INVALID_STORAGE','STALE_STORAGE','READ_FAILED','WRITE_FAILED','BACKEND_FAILED'}

def relay_snapshot(value):
    if not isinstance(value,dict) or value.get('schema')!='das-jsaux-relay-v1':
        return dict(observed=False)
    out=dict(observed=True,schema='das-jsaux-relay-v1')
    if type(value.get('enabled')) is bool:out['enabled']=value['enabled']
    for section in ('iframe','storage','recovery'):
        raw=value.get(section)
        if not isinstance(raw,dict):continue
        clean={}
        for key,item in raw.items():
            if key in COUNTERS and type(item) is int and 0<=item<=999999:clean[key]=item
            elif key in FLAGS and type(item) is bool:clean[key]=item
            elif key in {'last_error','last_rejection'} and isinstance(item,str) and item in CODES:clean[key]=item
            elif key=='last_error_name' and isinstance(item,str) and item in {'','Unknown','Error','TypeError','ReferenceError','RangeError','SyntaxError','DOMException','AbortError','SecurityError','NotAllowedError','OperationResponse'}:clean[key]=item
            elif key=='last_native_result' and (item is None or type(item) is int and 0<=item<=999):clean[key]=item
        out[section]=clean
    return out
