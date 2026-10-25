/** Resolve Steam's current CSS module tokens. Missing exports match nothing. */
export function nativeClassSelector(scope:string,classes:Record<string,string>|undefined,key:string):string{
  const tokens=classes?.[key]?.split(/\s+/).filter(Boolean)??[];
  const escape=(value:string)=>value.replace(/\\/g,'\\\\').replace(/"/g,'\\"');
  return tokens.length?`${scope} ${tokens.map(token=>`[class~="${escape(token)}"]`).join('')}`:`${scope} [data-das-native-unavailable="${escape(key)}"]`;
}
