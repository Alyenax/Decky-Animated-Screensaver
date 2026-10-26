// Production React hook under react-test-renderer; no SteamOS or browser claim.
// Install react, react-dom and react-test-renderer of one version in DAS_UI_DEPS.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import vm from 'node:vm';
import {rollup} from 'rollup';
import ts from 'typescript';
const root=process.cwd(),source=process.env.DAS_AUDIT_SOURCE_ROOT||root;
const require=createRequire(path.join(root,'package.json'));
const runtime=process.env.DAS_UI_DEPS||path.resolve(root,'../ui-deps/node_modules');
const fromDecky=createRequire(require.resolve('@decky/rollup/package.json'));
const {nodeResolve}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-node-resolve')));
const {default:commonjs}=await import(pathToFileURL(fromDecky.resolve('@rollup/plugin-commonjs')));
const bundle=await rollup({input:path.join(root,'tests/ui/startup-recovery.tsx'),plugins:[{
  name:'startup-adapters',resolveId(id,importer){
    if(id==='../../src/StudioRuntime'&&importer?.endsWith('startup-recovery.tsx'))return path.join(source,'src/StudioRuntime.tsx');
    if(id==='@decky/ui')return '\0decky-ui';
    if(['react','react/jsx-runtime','react-test-renderer'].includes(id))return path.join(runtime,id==='react'?'react/index.js':id==='react-test-renderer'?'react-test-renderer/index.js':id+'.js');
  },load(id){if(id==='\0decky-ui')return 'export const DialogButton=()=>null,Focusable=()=>null;';},
  transform(code,id){if(/\.tsx?$/.test(id))return ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;}
},nodeResolve({extensions:['.js','.ts','.tsx']}),commonjs(),{name:'test-development',transform:code=>code.replaceAll('process.env.NODE_ENV','"development"')}]});
const {output}=await bundle.generate({format:'iife',name:'StartupAudit'});await bundle.close();
const host=new EventTarget();host.auditRequest=async()=>{throw new Error('Python Exception: Unexpected error');};
const context={window:host,document:{visibilityState:'hidden'},navigator:{language:'en'},localStorage:{getItem:()=>null},
  console,setTimeout,clearTimeout,setInterval,clearInterval,performance,MessageChannel,Event,
  CustomEvent:class extends Event{constructor(type,options){super(type);this.detail=options?.detail;}},IS_REACT_ACT_ENVIRONMENT:true};
context.global=context;context.globalThis=context;
vm.createContext(context);vm.runInContext(output[0].code,context);
const {mount,act}=context.StartupAudit;let tree;
try{
  await act(async()=>{tree=mount();});
  const refresh=()=>act(async()=>{await host.audit.refresh();});
  await refresh();assert.match(host.audit.error,/Python Exception/);
  host.auditRequest=async()=>({version:'recovered',job:{state:'idle',worker_active:false}});
  await refresh();assert.equal(host.audit.state.version,'recovered');
  assert.equal(host.audit.error,'','successful refresh must clear the transient Python error');assert.equal(host.audit.failure,null);
  console.log('PASS transient refresh failure clears after success');
  let rejectOld,old;
  await act(async()=>{
    host.auditRequest=()=>new Promise((_,reject)=>{rejectOld=reject;});old=host.audit.refresh();
    host.auditRequest=async()=>({version:'newest',job:{state:'idle',worker_active:false}});
    await host.audit.refresh();rejectOld(new Error('old-error'));await old;
  });
  assert.equal(host.audit.state.version,'newest');assert.equal(host.audit.error,'','late failure must not poison current state');
  console.log('PASS stale rejected refresh ignored');
  host.auditRequest=async action=>{if(action==='configure')throw new Error('disk_full');return {version:'healthy',job:{state:'idle',worker_active:false}};};
  await act(async()=>{await host.audit.run('configure');});await refresh();
  assert.notEqual(host.audit.error,'','background reads must preserve actionable mutation errors');assert.equal(host.audit.failure.action,'configure');
  console.log('PASS action error survives a healthy background refresh');
}finally{if(tree)await act(async()=>tree.unmount());}
