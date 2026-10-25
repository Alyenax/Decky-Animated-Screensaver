import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {runtimePluginName} from '../../src/runtime_identity';
test('Decky RPC follows the loaded identity across the display-name migration',()=>{
 for(const name of ['Decky-Animated-Screensaver','Animated Screensaver'])assert.equal(runtimePluginName(`http://127.0.0.1:1337/plugins/${encodeURIComponent(name)}/dist/index.js?t=123`,'fallback'),name);
 for(const url of ['https://example.com/plugins/Animated%20Screensaver/dist/index.js','http://127.0.0.1:1337/plugins/Other/dist/index.js','bad','http://127.0.0.1:1337/plugins/%/dist/index.js'])assert.equal(runtimePluginName(url,'fallback'),'fallback');
});
