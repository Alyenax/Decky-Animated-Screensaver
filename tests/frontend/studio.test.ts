import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
const read=(p:string)=>readFileSync(new URL('../../src/'+p,import.meta.url),'utf8');
test('Only collection mounts with no classic route',()=>{
const shell=read('StudioShell.tsx');assert(shell.includes('<CollectionStudio'));assert(shell.includes('<CollectionQuick'));assert(!shell.includes('useInterface'));assert(!shell.includes('QuickPanel'));assert(!existsSync(new URL('../../src/Studio.tsx',import.meta.url)));
});
test('Preview and hook are independent of old workspace',()=>{
const runtime=read('StudioRuntime.tsx');assert(runtime.includes('export function Player('));assert(runtime.includes('export function useStudio('));assert(!runtime.includes('Workspace'));
});
test('Grouped drafts and explicit prepare/install remain',()=>{
const page=read('CollectionStudio.tsx');for(const key of ['workspace_draft','workspace_prepare','workspace_install','setConfirm'])assert(page.includes(key));
});
test('Discovery is read-only and checks stale responses and minimum length',()=>{
const page=read('CollectionStudio.tsx');for(const key of ['client<DiscoveryPage>','browse_candidates','id===loadSerial.current','q.length>0&&q.length<3'])assert(page.includes(key));
});
test('Optional hardware and separate Updates survive UI removal',()=>{
const page=read('CollectionStudio.tsx'),panels=read('SettingsPanels.tsx');for(const item of ['AssistancePanel','SettingsPanels','UpdatesPanel'])assert(page.includes(item));for(const item of ['jsauxVisible(jsaux)','openSteamGridDBPage','alignment_ms'])assert(panels.includes(item));
});
test('No serial or standalone frontend',()=>{
for(const name of ['CollectionStudio.tsx','StudioRuntime.tsx','SettingsPanels.tsx','AssistancePanel.tsx'])assert.doesNotMatch(read(name),/navigator.serial|WebUSB|import.*signalbar|import.*electron/);
});
