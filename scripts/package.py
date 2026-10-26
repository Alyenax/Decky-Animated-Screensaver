"""Small Decky ZIP with corresponding source, no user data or dev dependencies."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAME='Decky-Animated-Screensaver'
VERSION=json.loads((ROOT/'package.json').read_text())['version']

def main():
    if not (ROOT/'dist/index.js').is_file():raise SystemExit('Build the frontend first')
    files=[ROOT/'docs/VALIDATION_PUBLIC.json',ROOT/'docs/NATIVE_STEAM_UI.md',ROOT/f'docs/RELEASE_NOTES_{VERSION}.md']
    files += [ROOT/name for name in ('plugin.json','package.json','main.py','README.md','CHANGELOG.md','LICENSE','pnpm-lock.yaml','rollup.config.js','tsconfig.json')]
    # Source included alongside the compiled bundle for GPL correspondence.
    for folder in ('dist','assets','licenses','py_modules','src'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.map'})
    files.extend(ROOT/name for name in ('scripts/build.mjs','scripts/package.py','docs/JSAUX_CONTRACT_PIN.json','docs/JSAUX_INTEGRATION.md','docs/UPDATES.md'))
    files.extend((ROOT/'docs/wiki').glob('*.md'))
    files.append(ROOT/'docs/wiki/media/CREDITS.md')
    files.append(ROOT/'docs/wiki/media/manifest.json')
    for p in files:
        if p.is_symlink():raise SystemExit('Do not package links')
        if p.stat().st_size>512*1024:raise SystemExit('Unexpected oversized source asset: '+p.name)
    # Exact allowlist: the optional 64MB runtime, cache, credentials, local
    # preview artifacts, node_modules and hardware drivers cannot enter here.
    production='\n'.join(p.read_text(errors='ignore') for p in files if p.suffix in {'.py','.ts','.tsx','.js'} and p.name!='package.py')
    for token in ('signalbar.', 'import serial','from serial','prepare_faceplate','triple_sync','/dev/ttyUSB'):
        if token in production:raise SystemExit('Hardware or parent-plugin dependency entered package: '+token)
    for token in ('diagnostic_upload','settings_github','update_auth_start','auto_install','github.com/login/device','CLIENT_ID'):
        if token in production:raise SystemExit('Private or automatic update feature entered public package: '+token)
    pin=json.loads((ROOT/'docs/JSAUX_CONTRACT_PIN.json').read_text())
    if pin['contract_revision']!=4 or pin['sha256']!='480b8abaa9ee5669106f55fae46bb9acf0213abf4d28eb05568c499eccc4c11f':
        raise SystemExit('Shared JSAUX contract pin changed without review')
    if json.loads((ROOT/'plugin.json').read_text()).get('flags')!=['root']:
        raise SystemExit('JSAUX client requires the explicitly approved Decky backend identity')
    out=ROOT/'out';out.mkdir(exist_ok=True)
    def payload(p):return p.read_bytes()
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(payload(p)).hexdigest() for p in files}
    archive=out/f'{NAME}-v{VERSION}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(files):
            name=f'{NAME}/{p.relative_to(ROOT)}';info=zipfile.ZipInfo(name,(2026,10,17,0,0,0));info.external_attr=0o100644<<16
            z.writestr(info,payload(p),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
        z.writestr(f'{NAME}/manifest.sha256.json',json.dumps(manifest,sort_keys=True,indent=2))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'SHA256SUMS').write_text(f'{digest}  {archive.name}\n')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,expected in manifest.items():assert hashlib.sha256(z.read(f'{NAME}/{name}')).hexdigest()==expected
        assert json.loads(z.read(f'{NAME}/plugin.json'))['name']=='Animated Screensaver'
        assert json.loads(z.read(f'{NAME}/package.json'))['version']==VERSION
    print(f'{archive}\n{archive.stat().st_size} bytes\nSHA256 {digest}\nVerified {len(manifest)} files, ZIP integrity and independent plugin identity')

if __name__=='__main__':main()
