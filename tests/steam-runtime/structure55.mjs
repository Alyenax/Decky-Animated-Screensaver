import ts from 'typescript';
import fs from 'node:fs/promises';
import path from 'node:path';

/** This audit complements real algorithm tests; it never pretends JSX parsing
 * measures geometry or proves live Steam focus/controller behavior. */
export async function auditStructure55(root){
 const file=path.join(root,'src/CollectionStudio.tsx'),source=await fs.readFile(file,'utf8');
 const ast=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const toolbars=[],cards=[],backgroundActions=[],managementRows=[];
 const visit=node=>{
  if(ts.isJsxOpeningElement(node)||ts.isJsxSelfClosingElement(node)){
   const props=node.attributes.properties;
   const className=props.find(prop=>ts.isJsxAttribute(prop)&&prop.name.getText(ast)==='className')?.initializer?.getText(ast)||'';
   const flow=props.find(prop=>ts.isJsxAttribute(prop)&&prop.name.getText(ast)==='flow-children')?.initializer?.getText(ast)||'';
   const item={tag:node.tagName.getText(ast),flow,line:ast.getLineAndCharacterOfPosition(node.pos).line+1};
   if(className.includes('collection-search-view'))toolbars.push(item);
   if(className.includes('collection-select-card'))cards.push(item);
   if(className.includes('collection-background-actions'))backgroundActions.push(item);
   if(className.includes('collection-management-actions')||className.includes('collection-selection-undo'))managementRows.push(item);
  }
  ts.forEachChild(node,visit);
 };visit(ast);
 const blockers=[];
 if(toolbars.length!==2)blockers.push('Expected2 Collection/Add toolbar navigation groups; inspect changed component contract.');
 for(const item of toolbars)if(item.tag!=='Focusable'||item.flow!=='"row"')blockers.push(`Toolbar line${item.line} is ${item.tag}/${item.flow||'implicit'}: CSS columns are not a native ROW group.`);
 if(!cards.length)blockers.push('Add-card group not recognized; inspect changed component contract.');
 for(const item of cards)if(item.tag!=='Focusable')blockers.push(`Add-card line${item.line} is a plain ${item.tag}: Select and Customize flatten under GRID.`);
 if(backgroundActions.length!==1||backgroundActions.some(item=>item.tag!=='Focusable'||item.flow!=='"row"'))blockers.push('Animation and still-image choices require one explicit native ROW.');
 if(managementRows.length!==2||managementRows.some(item=>item.tag!=='Focusable'||item.flow!=='"row"'))blockers.push('Management and Undo must each form an explicit native ROW.');
 const recoverySource=await fs.readFile(path.join(root,'src/FaceplateRecovery.tsx'),'utf8');
 const recoveryAst=ts.createSourceFile('FaceplateRecovery.tsx',recoverySource,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);let recoveryRows=0;
 const checkRecovery=node=>{if(ts.isJsxOpeningElement(node)&&node.attributes.properties.some(p=>ts.isJsxAttribute(p)&&p.name.getText(recoveryAst)==='className'&&p.initializer?.getText(recoveryAst).includes('collection-actions'))){
  recoveryRows++;const flow=node.attributes.properties.find(p=>ts.isJsxAttribute(p)&&p.name.getText(recoveryAst)==='flow-children');if(node.tagName.getText(recoveryAst)!=='Focusable'||flow?.initializer?.getText(recoveryAst)!=='"row"')blockers.push('Recovery actions must form an explicit native ROW.');
 }ts.forEachChild(node,checkRecovery);};checkRecovery(recoveryAst);if(recoveryRows!==1)blockers.push('Expected one native recovery action row.');
 return {recoveryRows,toolbars,cards,backgroundActions,managementRows,blockers,limitations:'AST verifies explicit known group contracts only; no layout, native text editor, accessibility tree, focus-ring or live controller proof.'};
}
