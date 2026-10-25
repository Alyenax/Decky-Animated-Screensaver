import test from 'node:test';
import assert from 'node:assert/strict';
import {artworkDiagnostic,imageEvent} from '../../src/artworkDiagnostic';
test('Image evidence distinguishes trusted categories, formats and failures without URLs',()=>{
 imageEvent('blocked','https://evil.test/private.png?key=SECRET');imageEvent('ready','https://cdn2.steamgriddb.com/thumb/a.png?token=SECRET');
 const v=artworkDiagnostic();assert(v.counts.blocked);assert.equal(v.events.at(-1)?.source,'sgdb');assert.equal(v.events.at(-1)?.format,'png');assert(!JSON.stringify(v).includes('SECRET'));assert(!JSON.stringify(v).includes('evil.test'));
 for(let i=0;i<40;i++)imageEvent('timeout','https://unknown.test/secret');assert.equal(artworkDiagnostic().events.length,24);
});
