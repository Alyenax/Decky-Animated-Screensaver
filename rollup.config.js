import {fileURLToPath} from 'node:url';
import deckyPlugin from "@decky/rollup";

const config = deckyPlugin({});
// No orphan source-map link in the installed runtime.
for (const current of Array.isArray(config) ? config : [config]) {
  current.plugins.unshift({
    name:'das-runtime-plugin-identity',
    transform(code,id){
      if(!id.replaceAll('\\','/').endsWith('/@decky/api/dist/index.js'))return null;
      const declaration='const manifest = _manifest;';
      if(!code.includes(declaration))throw new Error('Review Decky API manifest binding before upgrading');
      return {code:`import {runtimePluginName} from ${JSON.stringify(fileURLToPath(new URL('./src/runtime_identity.ts',import.meta.url)))};\n`+
        code.replace(declaration,'const manifest = {..._manifest, name:runtimePluginName(import.meta.url,_manifest.name)};'),map:null};
    }
  });
  for (const output of Array.isArray(current.output) ? current.output : [current.output]) {
    if (output) output.sourcemap = false;
  }
}
export default config;
