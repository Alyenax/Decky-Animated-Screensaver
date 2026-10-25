/** Execute in a real browser after loader55. Movement methods are unmodified
 * installed Steam NavigationNode code. Only the outer tree's transfer/focus
 * service is a deterministic host fixture, not the real Steam controller. */
export function navigationScenarios55(){
 const require=window.__steamRequire55;
 const {Bp:NavigationNode,xj:Layout,iU:Entry}=require(74562);
 const {pR:Button}=require(20505);
 const {O:flowLayout}=require(96485);
 const trace=[];
 const css=document.createElement('style');css.textContent=`
 body{margin:0} .test55{position:relative;padding:20px;width:600px;box-sizing:border-box}
 .toolbar55{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
 .toolbar56{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
 .grid55{display:grid;grid-template-columns:1fr 1fr;gap:20px}
 .card55{display:flex;flex-direction:column;gap:10px}
 .list55{display:flex;flex-direction:column;gap:20px}.row55{display:flex;gap:20px}.row55>button{flex:1;width:auto}
 .select55{height:100px}.customize55{height:40px}button,input{box-sizing:border-box;min-width:0;width:100%;height:40px}
 `;document.head.append(css);
 function environment(html){
  const container=document.createElement('section');container.className='test55';container.innerHTML=html;document.body.append(container);
  const nodes=new Map(),mounted=[];
  // Host seam: no movement/layout algorithms are supplied here. Native
  // FindNextFocusableChild/Grid/Descendant and geometry decide every target.
  const tree={Root:null,focused:null,
   Controller:{GetShowDebugFocusRing:()=>({Value:false})},
   GetParentEmbeddedNavTree:()=>null,GetLastFocusedMovementRect:()=>undefined,
   GetLastFocusedNode(){return this.focused;},
   DeferredFocus:{BHasQueuedFocusNode:()=>false,BIsQueuedFocusNode:()=>false,RequestFocus(){}},
   TransferFocus(reason,node,button){
    if(this.focused){this.focused.SetHasFocus(false);for(let n=this.focused;n;n=n.Parent)n.SetFocusWithin(false);}
    this.focused=node;
    if(node){node.SetHasFocus(true);for(let n=node;n;n=n.Parent)n.SetFocusWithin(true);node.UpdateParentActiveChild();node.Element.focus({preventScroll:true});}
    return true;
   },
  };
  function add(id,parent,flow,focusable=false,properties={}){
   const element=id==='root'?container:container.querySelector('#'+id);
   if(!element)throw Error('Fixture element missing: '+id);
   const node=new NavigationNode(tree,parent?nodes.get(parent):null,null);
   node.SetProperties({...(flow?{layout:flowLayout(flow)}:{}),focusable,noFocusRing:true,...properties});
   if(id==='root')tree.Root=node;
   nodes.set(id,node);node.OnMount(element);mounted.push(node);return node;
  }
  function focus(id){tree.TransferFocus(0,nodes.get(id));}
  function move(direction){
   const before=tree.focused?.Element.id||'root',button=Button['DIR_'+direction];let handled=false;
   for(let node=tree.focused?.Parent;node;node=node.Parent){if(node.OnNavigationEvent({detail:{button,is_repeat:false}})){handled=true;break;}}
   const after=tree.focused?.Element.id||'root';trace.push({before,direction,after,handled});return after;
  }
  return {add,focus,move,dispose(){for(const node of mounted.reverse()){node.SetHasFocus(false);node.OnUnmount();}container.remove();}};
 }
 const assert=(actual,expected,label)=>{if(actual!==expected)throw Error(label+': '+JSON.stringify({actual,expected}));};
 // Real alpha54 topology: a CSS-only toolbar contributes no navigation node;
 // the explicit body column makes both horizontal directions invalid.
 let e=environment('<div class="toolbar55"><input id="search55"><button id="view55">View</button></div>');
 e.add('root',null,'column');e.add('search55','root',null,true);e.add('view55','root',null,true);e.focus('search55');
 assert(e.move('RIGHT'),'search55','alpha54 CSS-only toolbar reproduces horizontal wall');
 assert(e.move('DOWN'),'view55','alpha54 body instead navigates vertically across visible columns');e.dispose();
 // Correct topology: the matching row owns the two fields.
 e=environment('<div id="toolbar55" class="toolbar55"><input id="search55"><button id="view55">View</button></div>');
 e.add('root',null,'column');e.add('toolbar55','root','row');e.add('search55','toolbar55',null,true);e.add('view55','toolbar55',null,true);e.focus('search55');
 assert(e.move('RIGHT'),'view55','native row crosses to View');assert(e.move('LEFT'),'search55','native row returns to Search');e.dispose();
 // Alpha56 keeps the native ROW while introducing an equal middle Source /
 // Filter control; neither horizontal crossing may be lost to CSS-only grouping.
 e=environment('<div id="toolbar56" class="toolbar56"><input id="search56"><button id="filter56">Filter / Source</button><button id="view56">View</button></div>');
 e.add('root',null,'column');e.add('toolbar56','root','row');
 for(const id of ['search56','filter56','view56'])e.add(id,'toolbar56',null,true);
 e.focus('search56');assert(e.move('RIGHT'),'filter56','native three-control toolbar reaches Filter / Source');
 assert(e.move('RIGHT'),'view56','native three-control toolbar reaches View');
 assert(e.move('LEFT'),'filter56','native three-control toolbar returns through Filter / Source');
 assert(e.move('LEFT'),'search56','native three-control toolbar returns to Search');e.dispose();
 const cards='<div id="grid55" class="grid55">'+[1,2].map(i=>`<div id="card55-${i}" class="card55"><button class="select55" id="select55-${i}">Select</button><button class="customize55" id="customize55-${i}">Customize</button></div>`).join('')+'</div>';
 // Real alpha54 topology: each plain card is transparent to Steam's registry.
 // GRID sees Select1, Customize1, Select2, Customize2 in DOM order.
 e=environment(cards);e.add('root',null,'column');e.add('grid55','root','grid');
 for(const i of [1,2]){e.add('select55-'+i,'grid55',null,true);e.add('customize55-'+i,'grid55',null,true);}
 e.focus('select55-1');assert(e.move('RIGHT'),'select55-1','alpha54 flattened Add card reproduces native grid wall');e.dispose();
 // Correct topology: GRID sees cards, and each card owns its two actions.
 e=environment(cards);e.add('root',null,'column');e.add('grid55','root','grid');
 for(const i of [1,2]){e.add('card55-'+i,'grid55','column');e.add('select55-'+i,'card55-'+i,null,true);e.add('customize55-'+i,'card55-'+i,null,true);}
 e.focus('select55-1');assert(e.move('RIGHT'),'select55-2','grouped native card crosses to next card');
 assert(e.move('LEFT'),'select55-1','grouped native card returns');assert(e.move('DOWN'),'customize55-1','native card exposes its Customize action');e.dispose();
 // List rows own two actions. Entry preference preserves the visible action
 // column while the parent COLUMN chooses the preceding/following row.
 e=environment('<div id="list55" class="list55">'+[1,2].map(i=>`<div id="row55-${i}" class="row55"><button id="list-select55-${i}">Select</button><button id="list-customize55-${i}">Customize</button></div>`).join('')+'</div>');
 e.add('root',null,'column');e.add('list55','root','column');
 for(const i of [1,2]){e.add('row55-'+i,'list55','row',false,{navEntryPreferPosition:Entry.MAINTAIN_X});e.add('list-select55-'+i,'row55-'+i,null,true);e.add('list-customize55-'+i,'row55-'+i,null,true);}
 e.focus('list-select55-1');assert(e.move('RIGHT'),'list-customize55-1','native list row reaches Customize');
 assert(e.move('DOWN'),'list-customize55-2','native list down preserves Customize column');
 assert(e.move('LEFT'),'list-select55-2','native list row returns to Select');assert(e.move('UP'),'list-select55-1','native list up preserves Select column');e.dispose();
 // Four bounded Player actions form one native row, including Close.
 e=environment('<div id="player55" class="row55">'+[1,2,3,4].map(i=>`<button id="preview55-${i}">Action ${i}</button>`).join('')+'</div>');
 e.add('root',null,'column');e.add('player55','root','row');for(const i of [1,2,3,4])e.add('preview55-'+i,'player55',null,true);
 e.focus('preview55-1');for(const i of [2,3,4])assert(e.move('RIGHT'),'preview55-'+i,'native Player right reaches action '+i);
 for(const i of [3,2,1])assert(e.move('LEFT'),'preview55-'+i,'native Player left reaches action '+i);e.dispose();
 // A wrapped 2x2 gallery owns four card groups, each with its local controls.
 e=environment('<div id="gallery55" class="grid55">'+[1,2,3,4].map(i=>`<div id="gallery-card55-${i}" class="card55"><button class="select55" id="gallery-select55-${i}">Select</button><button class="customize55" id="gallery-customize55-${i}">Customize</button></div>`).join('')+'</div>');
 e.add('root',null,'column');e.add('gallery55','root','grid');
 for(const i of [1,2,3,4]){e.add('gallery-card55-'+i,'gallery55','column',false,{navEntryPreferPosition:Entry.MAINTAIN_Y});e.add('gallery-select55-'+i,'gallery-card55-'+i,null,true);e.add('gallery-customize55-'+i,'gallery-card55-'+i,null,true);}
 e.focus('gallery-select55-1');assert(e.move('RIGHT'),'gallery-select55-2','native gallery crosses row');
 assert(e.move('DOWN'),'gallery-customize55-2','native gallery local action remains reachable');
 assert(e.move('DOWN'),'gallery-select55-4','native gallery wraps downward to next visible row');
 assert(e.move('LEFT'),'gallery-select55-3','native gallery second row crosses left');
 assert(e.move('UP'),'gallery-customize55-1','native gallery up reaches preceding row bottom action');e.dispose();
 // Recovery actions remain in ordinary native rows, reachable above the result actions.
 e=environment('<div id="recover57" class="row55"><button id="independent57">Independent</button><button id="selection57">Selection</button></div><div id="result57" class="row55"><button id="preview57">Preview</button><button id="collection57">Collection</button></div>');
 e.add('root',null,'column');
 for(const [row,ids] of [['recover57',['independent57','selection57']],['result57',['preview57','collection57']]]){e.add(row,'root','row',false,{navEntryPreferPosition:Entry.MAINTAIN_X});for(const id of ids)e.add(id,row,null,true);}
 e.focus('independent57');assert(e.move('RIGHT'),'selection57','recovery reaches selection action');
 assert(e.move('DOWN'),'collection57','recovery down reaches the result row');assert(e.move('LEFT'),'preview57','result row exposes preview');
 assert(e.move('UP'),'independent57','result row returns to recovery');e.dispose();
 assert(flowLayout('column'),Layout.COLUMN,'flow mapper is real native code');
 return {scenarios:9,trace,loadedFactories:Object.keys(window.__steamLoaded55),
  limitations:'Installed Steam NavigationNode movement and real DOM geometry; fixture tree transfer/event delivery; not live Steam CEF/controller, text editing, focus-ring painting or optical output.'};
}
