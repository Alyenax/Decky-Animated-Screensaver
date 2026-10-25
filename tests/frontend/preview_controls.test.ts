import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
test('Decky preview keeps native controls and never offers browser fullscreen',()=>{
  const source=readFileSync(new URL('../../src/StudioRuntime.tsx',import.meta.url),'utf8');
  const player=source.slice(source.indexOf('export function Player('));
  assert.doesNotMatch(player,/requestFullscreen|Fullscreen|Plein écran|allowFullscreen|autoplay; fullscreen/);
  for(const action of ['previous','pause','play','next','Close'])assert(player.includes(action));
  assert(player.includes('allow="autoplay"'));
});
