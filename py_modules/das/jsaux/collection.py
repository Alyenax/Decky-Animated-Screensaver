"""Offline identities compiler. Full opaque RGB332 frames, never hardware IO."""
from __future__ import annotations
import hashlib
import json
from .gif import encode
from .protocol import BrokerError
from .power import PALETTE,POWER_POLICY,POWER_BUDGET_PPM,limit_frame,energy,load_ppm
from das.studio.presentation import manifest as presentation
from .timing import transfer_ms, SYNC_MAX_BYTES

MAX_BYTES=196608
STARTUP_TARGET_BYTES=65536

def transfer_estimate_ms(size):
    """Precautionary admission estimate, not a measured USB/optical guarantee."""
    return transfer_ms(size) if int(size)>0 else 0

def preparation_spec(games,options,tv,*,mode_policy=False,batched=False):
    rows=[]
    for game in games:
        media=game.get('media',{}); hashes=game.get('sha256',{})
        role=next((key for key in ('panel_source','cover','thumbnail') if media.get(key)),None)
        crop=game.get('faceplate_crop',{})
        digest=hashes.get(role)
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            digest=None
        row=dict(appid=game['appid'],source_role=role,source=None if digest else media.get(role),
                 sha256=digest,crop={axis:crop.get(axis,50) for axis in ('x','y')})
        # An explicit new square selection has not been downloaded yet. Do not
        # continue advertising a GIF made from the previously committed square.
        if game.get('panel_pending') and game.get('panel_asset'):
            asset=game['panel_asset']
            row['pending_selection']={key:asset.get(key) for key in ('id','url')}
        rows.append(row)
    seconds=tv['scene_seconds'] if options['mode']=='sync' else options['page_seconds']
    # Only pixel/timing inputs belong in this key. Names, enabled/configured,
    # TV-only media and an unused independent duration never alter these pixels.
    spec=dict(version=6,games=rows,playback=dict(page_seconds=seconds,transition=options['transition']),
              order='installed-player-order',profile='gca-collection-rgb332-opaque-v1',
              startup_target_bytes=STARTUP_TARGET_BYTES,
              power=dict(policy=POWER_POLICY,budget_ppm=POWER_BUDGET_PPM))
    # All newly prepared loops use the compact 80 KiB budget. Large independent
    # collections use lots instead of retaining an old dense 192 KiB GIF.
    # Keep the synchronised input key unchanged; invalidate old async outputs.
    if options['mode']=='async':spec['maximum_bytes']=SYNC_MAX_BYTES
    # The unchanged square mode retains alpha42's exact identity/cache key.
    # Only the new pixel-changing option needs another prepared collection.
    if options.get('framing','square')=='fill':spec['framing']='fill'
    if mode_policy:
        spec['requested_mode']=options['mode']
        if batched:spec['playback']['fallback_page_seconds']=options['page_seconds']
    return spec

def fingerprint(games,options,tv,*,mode_policy=False,batched=False):
    spec=preparation_spec(games,options,tv,mode_policy=mode_policy,batched=batched)
    return hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def index_rgb(data):
    if len(data)!=64*54*3:raise BrokerError('CONTENT_INVALID')
    return bytes((((data[i]*7+127)//255)<<5)|(((data[i+1]*7+127)//255)<<2)|((data[i+2]*3+127)//255) for i in range(0,len(data),3))

def interpolate(a,b,p,kind):
    if kind=='none':return b
    out=bytearray(3456); shift=round(64*p); gain=p*p*(3-2*p)
    for y in range(54):
        for x in range(64):
            i=y*64+x
            if kind=='slide':
                sx=x+shift;out[i]=a[y*64+sx] if sx<64 else b[y*64+sx-64]
            elif kind=='wipe':out[i]=b[i] if x<shift else a[i]
            elif kind=='dissolve':out[i]=b[i] if ((x*37+y*17)%64)/64<p else a[i]
            else:
                rgb=[round(c+(d-c)*gain) for c,d in zip(PALETTE[a[i]],PALETTE[b[i]])]
                out[i]=(((rgb[0]*7+127)//255)<<5)|(((rgb[1]*7+127)//255)<<2)|((rgb[2]*3+127)//255)
    return bytes(out)

def compile_pages(pages,seconds,transition,maximum=MAX_BYTES,checkpoint=lambda:None,*,prefer_small=False):
    # USB startup is dominated by bytes, not the collection's playback duration.
    # Try fewer transition samples before accepting a multi-second transfer.
    # Keep every identity, RGB332 palette, power check and exact page duration.
    # Both modes prefer a compact transfer. Sync never expands beyond its
    # timing-safe ceiling; independent mode retains the larger hard budget.
    maximum=min(maximum,SYNC_MAX_BYTES) if prefer_small else maximum
    target=min(maximum,STARTUP_TARGET_BYTES)
    try:
        return _compile_pages(pages,seconds,transition,maximum,checkpoint,target=target,
                              smallest_fallback=not prefer_small)
    except BrokerError as error:
        if prefer_small and target<maximum and error.code=='CONTENT_TOO_LARGE':
            raise BrokerError('JSAUX_SYNC_WINDOW') from error
        raise

def compile_batches(pages,seconds,transition,maximum=SYNC_MAX_BYTES,checkpoint=lambda:None):
    """Compact independent loops, preserving every page and its order.

    Eight identities bound each encode attempt. An unusually small broker
    budget is handled by splitting further, never by dropping identities.
    """
    if not pages or len(pages)>2000:raise BrokerError('CONTENT_INVALID')
    maximum=min(maximum,SYNC_MAX_BYTES)
    result=[]
    def part(chunk):
        checkpoint()
        try:result.append(compile_pages(chunk,seconds,transition,maximum,checkpoint,prefer_small=True))
        except BrokerError as error:
            if error.code not in {'CONTENT_TOO_LARGE','JSAUX_SYNC_WINDOW'} or len(chunk)==1:raise
            middle=len(chunk)//2;part(chunk[:middle]);part(chunk[middle:])
    for start in range(0,len(pages),8):part(pages[start:start+8])
    return result

def batch_identity(source_identity,batches):
    if (not isinstance(batches,list) or not 1<=len(batches)<=512 or any(
        not isinstance(b,dict) or not isinstance(b.get('sha256'),str) or len(b['sha256'])!=64
        or any(c not in '0123456789abcdef' for c in b['sha256'])
        or any(type(b.get(k)) is not int or b[k]<=0 for k in ('duration_cs','pages')) for b in batches)):
        raise ValueError('Invalid batch manifest')
    rows=[dict(sha256=b['sha256'],duration_cs=b['duration_cs'],pages=b['pages']) for b in batches]
    return hashlib.sha256((source_identity+json.dumps(rows,sort_keys=True,separators=(',',':'))).encode()).hexdigest()

def _compile_pages(pages,seconds,transition,maximum,checkpoint,*,target=None,smallest_fallback=False):
    if not pages or len(pages)>120 or any(len(p)!=3456 for p in pages):raise BrokerError('CONTENT_INVALID')
    if type(seconds) is not int or not 2<=seconds<=180 or transition not in {'fade','wipe','slide','dissolve','none'}:raise BrokerError('INVALID_REQUEST')
    # Preserve every page, native RGB332 palette and exact page timing. Only
    # over-budget pixels are adapted offline, including transition frames.
    # Only transition sampling is adaptive. Never ask users to discard games
    # before trying the lower densities, and never enlarge the hardware budget.
    target=maximum if target is None else min(maximum,target)
    best=None
    for steps in ((8,6,4,2,1) if transition!='none' else (0,)):
        frames=[];delays=[];move=0 if transition=='none' else 40
        for n,page in enumerate(pages):
            checkpoint();frames.append(page);delays.append(seconds*100-move)
            if move:
                for step in range(1,steps+1):
                    checkpoint()
                    # The next full identity begins at the page boundary, not
                    # 400 ms early when the adaptive pass has only one sample.
                    frames.append(interpolate(page,pages[(n+1)%len(pages)],step/(steps+1),transition))
                    delays.append(round(step*move/steps)-round((step-1)*move/steps))
        # A one-page collection retains explicit timed frames, unlike a static upload.
        if len(frames)==1:frames.append(frames[0]);delays=[seconds*100-1,1]
        source_peak=max(map(energy,frames));limited=[];adjusted=0
        for frame in frames:
            checkpoint();safe=limit_frame(frame,checkpoint);limited.append(safe);adjusted+=safe!=frame
        peak=max(map(energy,limited))
        checkpoint();data=encode(64,54,PALETTE,limited,delay_cs=delays,loop=True)
        if len(data)<=maximum:
            candidate=data,dict(bytes=len(data),frames=len(frames),duration_cs=sum(delays),pages=len(pages),
                             transition_steps=steps,transition_optimized=bool(transition!='none' and steps<8),
                             power_policy=POWER_POLICY,power_budget_ppm=POWER_BUDGET_PPM,
                             source_peak_load_ppm=load_ppm(source_peak),peak_load_ppm=load_ppm(peak),
                             power_limited_frames=adjusted)
            if len(data)<=target:return candidate
            # Independent output keeps the smallest valid fallback. Sync keeps
            # its legacy first-fit 80 KiB fallback, preserving its cache/output
            # contract without a second identical encoding pass.
            if best is None or smallest_fallback and len(data)<len(best[0]):best=candidate
    if best is not None:return best
    raise BrokerError('CONTENT_TOO_LARGE')
