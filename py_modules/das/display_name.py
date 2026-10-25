"""One-time Decky label migration, keeping the installation and settings folder."""
import hashlib
import json
from das.core.catalog import atomic_json
from das.github import read_json

LEGACY='Decky-Animated-Screensaver'
DISPLAY='Animated Screensaver'

def migrate(root):
    # Alpha65's updater requires the legacy name in the downloaded manifest.
    # Change only the installed descriptor after archive verification. Decky
    # picks up the new label on its next backend reload/restart; settings use
    # the unchanged directory, as specified by Decky's sandbox contract.
    root=root.resolve();manifest=read_json(root/'manifest.sha256.json')
    descriptor=read_json(root/'plugin.json')
    if descriptor.get('name')==DISPLAY:return False
    if descriptor.get('name')!=LEGACY:raise ValueError('Unexpected plugin identity')
    if not manifest or manifest.get('plugin.json')!=hashlib.sha256((root/'plugin.json').read_bytes()).hexdigest():
        raise ValueError('Plugin descriptor not verified')
    descriptor['name']=DISPLAY
    # The old updater/helper finishes using its already validated staging tree;
    # a failed migration never prevents startup or the health handshake.
    old=(root/'plugin.json').read_bytes()
    old_manifest=(root/'manifest.sha256.json').read_bytes()
    descriptor_mode=(root/'plugin.json').stat().st_mode&0o777
    manifest_mode=(root/'manifest.sha256.json').stat().st_mode&0o777
    try:
        atomic_json(root/'plugin.json',descriptor)
        (root/'plugin.json').chmod(descriptor_mode)
        manifest['plugin.json']=hashlib.sha256((root/'plugin.json').read_bytes()).hexdigest()
        atomic_json(root/'manifest.sha256.json',manifest)
        (root/'manifest.sha256.json').chmod(manifest_mode)
    except BaseException:
        atomic_json(root/'plugin.json',json.loads(old))
        (root/'plugin.json').chmod(descriptor_mode)
        atomic_json(root/'manifest.sha256.json',json.loads(old_manifest))
        (root/'manifest.sha256.json').chmod(manifest_mode)
        raise
    return True
