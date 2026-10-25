// Read installed Steam factories without running its application entrypoint.
// Valve code stays in memory: it is not copied into this repo or release ZIP.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import ts from 'typescript';
import {createRequire} from 'node:module';

export async function steamBootstrap55(root){
 const library=await fs.readFile(path.join(root,'library.js'),'utf8');
 const shared=await fs.readFile(path.join(root,'sp.js'),'utf8');
 const styles=await Promise.all(['css/library.css','css/sp.css'].map(name=>fs.readFile(path.join(root,name),'utf8')));
 const ast=ts.createSourceFile('library.js',library,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
 let factories;
 const visit=node=>{
  if(ts.isVariableDeclaration(node)&&node.initializer&&ts.isObjectLiteralExpression(node.initializer)
   &&node.initializer.properties.some(property=>property.name?.getText(ast)==='43310')){
   if(factories)throw Error('Ambiguous Steam core factory table');
   factories=node.initializer.getText(ast);
  }
  ts.forEachChild(node,visit);
 };
 visit(ast);
 if(!factories)throw Error('Installed Steam core factory table not recognized');
 const require=createRequire(import.meta.url),reactRoot=path.dirname(require.resolve('react/package.json'));
 const react=await fs.readFile(path.join(reactRoot,'cjs/react.production.js'),'utf8');
 const source=`window.__steamHostReact55=(()=>{const module={exports:{}},exports=module.exports;${react};return module.exports;})();
 window.__steamFactories55=(${factories});
 const captured=[];window.webpackChunksteamui={push(chunk){captured.push(chunk);Object.assign(window.__steamFactories55,chunk[1]);}};
 ${shared}
 (()=>{
 const factories=window.__steamFactories55,cache={},loading=[];
 function require(id){
  if(id===63696)return window.__steamHostReact55;
  if(cache[id])return cache[id].exports;
  if(!factories[id])throw Error('Steam factory '+id+' absent; required by '+loading.join(' > '));
  const module={exports:{}};cache[id]=module;loading.push(id);
  try{factories[id](module,module.exports,require);}finally{loading.pop();}
  return module.exports;
 }
 Object.assign(require,{
  d(exports,getters){for(const [name,get]of Object.entries(getters))Object.defineProperty(exports,name,{enumerable:true,get});},
  r(exports){Object.defineProperty(exports,'__esModule',{value:true});},
  n(module){const get=module&&module.__esModule?()=>module.default:()=>module;require.d(get,{a:get});return get;},
  o:(object,key)=>Object.prototype.hasOwnProperty.call(object,key),g:window,
 });
 window.__steamRequire55=require;window.__steamLoaded55=cache;
 })();`;
 return {source,metadata:{library_sha256:createHash('sha256').update(library).digest('hex'),sp_sha256:createHash('sha256').update(shared).digest('hex'),
  library_css_sha256:createHash('sha256').update(styles[0]).digest('hex'),sp_css_sha256:createHash('sha256').update(styles[1]).digest('hex'),
  host_react_version:JSON.parse(await fs.readFile(path.join(reactRoot,'package.json'),'utf8')).version}};
}
