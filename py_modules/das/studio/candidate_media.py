"""Small gallery derivatives, separate from installed/prepared TV media."""
from pathlib import Path
from .media import signature,webp_info
from das.core.catalog import ScreensaverError

def webp_prefix(source,target,check,still=False):
    """Retain original WebP blend/disposal. Never flatten ANMFs for motion.

    A short native prefix avoids requiring animated-WebP support in FFmpeg.
    Still decoding needs only the first independently encoded frame.
    """
    info=webp_info(source)
    if not info:return None
    chunks=[];frames=milliseconds=0;size=12;seen=set()
    with Path(source).open('rb') as stream:
        stream.seek(12)
        while header:=stream.read(8):
            check()
            if len(header)!=8:raise ScreensaverError('Invalid WebP','invalid_media')
            kind=header[:4];length=int.from_bytes(header[4:],'little')
            if length>128*1024*1024:raise ScreensaverError('Invalid frame','invalid_media')
            if kind==b'ANMF':
                if frames and (frames>=72 or milliseconds>=6000 or size+length+8>8*1024*1024):break
                if length+size+8>8*1024*1024:raise ScreensaverError('Preview frame too large','source_limit')
                data=stream.read(length)
                if len(data)!=length:raise ScreensaverError('Truncated WebP','invalid_media')
                if still:
                    payload=data[16:]
                    target.write_bytes(b'RIFF'+(len(payload)+4).to_bytes(4,'little')+b'WEBP'+payload)
                    return info
                milliseconds+=max(10,int.from_bytes(data[12:15],'little'));frames+=1
                chunks.append(header+data+(b'\0' if length%2 else b''));size+=8+length+(length%2)
            elif kind in {b'VP8X',b'ANIM',b'ICCP'}:
                if kind in seen or length>1024*1024 or size+8+length>8*1024*1024:raise ScreensaverError('Invalid WebP metadata','invalid_media')
                seen.add(kind)
                data=stream.read(length)
                if kind==b'ANIM':data=data[:4]+b'\0\0' # Gallery loops only while focused.
                chunks.append(header+data+(b'\0' if length%2 else b''));size+=8+length+(length%2)
            else:stream.seek(length,1)
            if length%2:stream.seek(1,1)
    check()
    if not frames:raise ScreensaverError('No frames','invalid_media')
    target.write_bytes(b'RIFF'+(size-8).to_bytes(4,'little')+b'WEBP'+b''.join(chunks))
    return {**info,'frames':frames,'duration':milliseconds/1000,'animated':frames>1}

def render(codec,source,directory,check,motion=False):
    """One supervised codec, 320x180 still / <=6s motion, no TV preparation."""
    if not codec.runner.ffmpeg:raise ScreensaverError('Video tools are missing','ffmpeg_missing')
    source=Path(source);directory=Path(directory);fmt=signature(source)
    if fmt=='webp':
        native=directory/('motion.webp' if motion else 'first.webp')
        info=webp_prefix(source,native,check,still=not motion)
        if info:
            if motion:
                if not info['animated']:raise ScreensaverError('Static thumbnail','static_selection')
                return native
            source=native
    info=codec.inspect(source,check)
    if motion and not info['animated']:raise ScreensaverError('Static thumbnail','static_selection')
    target=directory/('motion.webm' if motion else 'still.jpg')
    inputs=['-protocol_whitelist','file,pipe','-i',str(source)]
    filters='scale=320:180:force_original_aspect_ratio=decrease:force_divisible_by=2'
    args=inputs+['-an','-sn','-vf',filters+(',fps=12,format=yuv420p' if motion else '')]
    args+=['-t','6','-c:v','libvpx','-deadline','realtime','-cpu-used','6','-b:v','300k','-fs','4194304'] if motion else ['-frames:v','1','-q:v','5']
    codec.run(args+[str(target)],directory,check,lambda _:None,timeout=35)
    if not target.is_file() or not 0<target.stat().st_size<=(4*1024*1024 if motion else 96*1024):
        raise ScreensaverError('Invalid gallery derivative','invalid_media')
    if motion:codec.inspect(target,check)
    return target
