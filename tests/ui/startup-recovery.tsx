import {create,act} from 'react-test-renderer';
import {useStudio} from '../../src/StudioRuntime';
import type {StudioClient,StudioState} from '../../src/types';
const host=window as any;
const client:StudioClient=async<T=StudioState>(action:string)=>host.auditRequest(action) as Promise<T>;
function Probe(){
  const api=useStudio(client,false,false);host.audit=api;
  return <div>{api.error}{api.failure?.action}{api.state?.version}</div>;
}
export const mount=()=>create(<Probe/>);
export {act};
