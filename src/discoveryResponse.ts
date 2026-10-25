// Expected remote failures must cross Decky RPC as data, not opaque exceptions.
export function discoveryResponse(action:string,value:unknown):unknown{
 if(value&&typeof value==='object'&&'schema' in value&&value.schema==='das-action-error-v1'){
  const code='ok' in value&&value.ok===false&&'error' in value&&typeof value.error==='string'&&/^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(value.error)?value.error:'unexpected_error';
  throw new Error(code);
 }
 if(!['browse_top','browse_search','browse_candidates','preview_recipe','candidate_preview','preview_installed'].includes(action))return value;
 if(value&&typeof value==='object'&&'schema' in value&&value.schema==='das-discovery-error-v1'){
  const code='error' in value&&typeof value.error==='string'&&/^[a-z][a-z0-9_]{0,79}$/.test(value.error)?value.error:'unexpected_error';
  throw new Error(code);
 }
 return value;
}
