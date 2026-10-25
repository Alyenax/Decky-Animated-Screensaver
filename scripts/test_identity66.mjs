// Exercise the actual bundled native API initialization under both Decky URLs.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const bundle=await fs.readFile('dist/index.js','utf8');
const prefix=bundle.slice(0,bundle.indexOf('const callable = api.callable;'));
assert(prefix.includes('runtimePluginName(import.meta.url,'));
for(const expected of ['Decky-Animated-Screensaver','Animated Screensaver']){
 const loaded=[];const window={__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit:{connect:(version,name)=>{loaded.push({version,name});return {_version:2};}}};
 const url=`http://127.0.0.1:1337/plugins/${encodeURIComponent(expected)}/dist/index.js?t=123`;
 new Function('window',prefix.replaceAll('import.meta.url',JSON.stringify(url)))(window);
 assert.deepEqual(loaded,[{version:2,name:expected}]);
}
console.log('PASS production bundle uses the native API under both Decky plugin identities');
