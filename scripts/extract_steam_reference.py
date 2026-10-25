# Local QA only. Reads installed assets; emits names/hashes, never Valve CSS/JS.
from pathlib import Path
import re,json,hashlib,argparse
parser=argparse.ArgumentParser(description='Read installed Steam CSS module metadata; never copy assets')
parser.add_argument('steamui',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
r=args.steamui.resolve();s=(r/'sp.js').read_text();modules={}
for m in re.finditer(r'\.exports=\{([^{}]+)\}',s):
 obj={a or b:c for a,b,c in re.findall(r'(?:"([^"\\]+)"|([A-Za-z_$][\w$]*)):"([^"\\]*)"',m[1])}
 tests={'dialog':bool(obj.get('GamepadDialogContent'))and'BindingButtons'not in obj,'panel':bool(obj.get('BatteryPercentageLabel')and obj.get('PanelSection'))and not any(k in obj for k in ['vr-dashboard-bar-height','QuickAccessMenu','QuickAccess','PerfProfileInfo']),'tabs':bool(obj.get('GamepadTabbedPage')),'sidebar':bool(obj.get('ScaledChildren')and obj.get('PagedSettingsDialog_PageContent')),'slider':bool(obj.get('SliderTrack')and obj.get('SliderHandle')and obj.get('SliderTrackDark'))}
 for k,v in tests.items():
  if v and k not in modules:modules[k]=obj
m=re.search(r'20189:\([^}]+\.exports=\{([^{}]+)\}',s)
if m:modules['panel']={a or b:c for a,b,c in re.findall(r'(?:"([^"\\]+)"|([A-Za-z_$][\w$]*)):"([^"\\]*)"',m[1])}
out={'steamRoot':str(r),'sha256':{n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in ['sp.js','css/sp.css']},'modules':modules}
args.output.write_text(json.dumps(out,indent=2))
print({k:{n:v.get(n) for n in ['Field','PanelSection','Tab','SliderTrack','PagedSettingsDialog']} for k,v in modules.items()})
