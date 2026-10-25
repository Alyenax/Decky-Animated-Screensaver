/** Decky serves the module under the loaded plugin identity, including during
 * the one-time descriptor rename. The installation folder stays unchanged. */
export function runtimePluginName(moduleURL:string,fallback:string):string{
 try{const url=new URL(moduleURL);if(url.origin!=='http://127.0.0.1:1337')return fallback;
  const match=/^\/plugins\/([^/]+)\/dist\/index\.js$/.exec(url.pathname);
  const name=match?decodeURIComponent(match[1]):'';
  return name==='Decky-Animated-Screensaver'||name==='Animated Screensaver'?name:fallback;
 }catch{return fallback;}
}
