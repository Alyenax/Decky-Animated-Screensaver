"""Native-first media. Every codec subprocess uses the Lab130 supervisor."""
from __future__ import annotations
import json
import hashlib
import math
from fractions import Fraction
from pathlib import Path
import shutil
import time
from das.core.catalog import ScreensaverError
from das.core.media import FFmpegMediaCompiler, _decoder_environment
from das.core.process_guard import capture

MAX_PIXELS=3840*2160
MAX_DURATION=600
STILL_MIN_ZOOM=1.02
STILL_ZOOM_TRAVEL=.08
STILL_PAN_X=.10
STILL_PAN_Y=.07

def still_motion_spec(options):
    # Still originals now move in the player through a bounded compositor
    # transform. The recipe is independent of the TV/JSAUX page calendar and
    # invalidates old encoded derivatives without decoding or regenerating them.
    return dict(version=8,renderer='transform',seconds=60,max_scale=1.18,pan_x=.06)

def still_motion_path(frame,frames,anchor):
    """Reference trajectory used by tests and mirrored by the FFmpeg filter."""
    phase=2*math.pi*frame/frames
    ease=(1-math.cos(phase))/2
    zoom=STILL_MIN_ZOOM+STILL_ZOOM_TRAVEL*ease
    return zoom,anchor[0]+STILL_PAN_X*math.sin(phase),anchor[1]-STILL_PAN_Y*math.sin(phase)

def signature(path):
    with Path(path).open('rb') as stream: head=stream.read(12)
    if head[:6] in (b'GIF87a',b'GIF89a'): return 'gif'
    if head[:4]==b'RIFF' and head[8:12]==b'WEBP': return 'webp'
    if head[:4]==b'\x1aE\xdf\xa3': return 'webm'
    if head[:8]==b'\x89PNG\r\n\x1a\n': return 'png'
    if head[:3]==b'\xff\xd8\xff': return 'jpg'
    raise ScreensaverError('Unsupported media signature','unsupported_source')

def webp_info(path):
    size=Path(path).stat().st_size; width=height=frames=milliseconds=0
    with Path(path).open('rb') as stream:
        head=stream.read(12)
        if int.from_bytes(head[4:8],'little')+8 != size: raise ScreensaverError('Invalid WebP length','invalid_media')
        position=12
        while position+8<=size:
            stream.seek(position); kind=stream.read(4); length=int.from_bytes(stream.read(4),'little')
            if position+8+length>size: raise ScreensaverError('Invalid WebP chunk','invalid_media')
            if kind==b'VP8X' and length>=10:
                data=stream.read(10); width=int.from_bytes(data[4:7],'little')+1; height=int.from_bytes(data[7:10],'little')+1
            if kind==b'ANMF':
                if length<16: raise ScreensaverError('Invalid WebP frame','invalid_media')
                data=stream.read(16); x=int.from_bytes(data[:3],'little')*2; y=int.from_bytes(data[3:6],'little')*2
                w=int.from_bytes(data[6:9],'little')+1; h=int.from_bytes(data[9:12],'little')+1
                if not width or not height or x+w>width or y+h>height: raise ScreensaverError('Invalid WebP canvas','invalid_media')
                milliseconds+=max(10,int.from_bytes(data[12:15],'little')); frames+=1
                if frames>18000 or milliseconds>600000: raise ScreensaverError('Animation too long','invalid_media')
            position+=8+length+(length%2)
    if not frames: return None
    if not width or not height or width*height>MAX_PIXELS: raise ScreensaverError('Image too large','invalid_media')
    return dict(width=width,height=height,frames=frames,duration=milliseconds/1000,codec='webp',animated=frames>1,audio=False)

class Media:
    def __init__(self, ffmpeg=None, library_path=None):
        self.runner=FFmpegMediaCompiler(ffmpeg=ffmpeg,library_path=library_path)
        self._probe=self._find_probe()
        self._decoder_ready=None

    @property
    def last_failure(self): return self.runner.last_failure
    def configure_runtime(self,*args):
        self.runner.configure_runtime(*args)
        self._probe=self._find_probe()
        self._decoder_ready=None
    def cancel(self): self.runner.cancel()
    @property
    def lease_fd(self): return self.runner.lease_fd
    @lease_fd.setter
    def lease_fd(self,value): self.runner.lease_fd=value

    def capabilities(self):
        return dict(ffmpeg=bool(self.runner.ffmpeg and self._decoder_ready is not False),ffprobe=bool(self._probe),native_first=True)

    def ensure_runtime(self):
        # One supervised decoder capability query per selected runtime, and only
        # on explicit Prepare. A version string or system binary is not proof.
        output=capture([self.runner.ffmpeg,'-hide_banner','-decoders'],environment=_decoder_environment(self.runner.library_path),
            timeout=4,maximum=512*1024,lease_fd=self.lease_fd,owner_pid=self.runner._owner_pid) if self.runner.ffmpeg else b''
        self._decoder_ready=all(token in output.split() for token in (b'gif',b'webp',b'vp8',b'vp9',b'png',b'mjpeg'))
        if not self._decoder_ready:
            raise ScreensaverError('Install the compatible video tools','ffmpeg_missing')
        if not self._probe: raise ScreensaverError('Install the video inspection tools','ffprobe_missing')

    def _find_probe(self):
        path=Path(self.runner.ffmpeg).with_name('ffprobe') if self.runner.ffmpeg else None
        return str(path) if path and path.is_file() else shutil.which('ffprobe')

    def inspect(self,path,checkpoint):
        checkpoint(); fmt=signature(path)
        if fmt=='webp':
            result=webp_info(path)
            if result: return {**result,'format':fmt}
        probe=self._probe
        if not probe: raise ScreensaverError('Video inspection tools are missing','ffprobe_missing')
        value=json.loads(capture([probe,'-v','error','-protocol_whitelist','file,pipe',
            '-f',{'webm':'matroska','jpg':'jpeg_pipe','png':'png_pipe','webp':'webp_pipe'}.get(fmt,fmt),
            '-count_frames','-show_entries','stream=codec_type,codec_name,width,height,nb_read_frames,r_frame_rate:format=duration',
            '-of','json',str(path)],environment=_decoder_environment(self.runner.library_path),timeout=30,
            maximum=65536,checkpoint=checkpoint,lease_fd=self.lease_fd,owner_pid=self.runner._owner_pid))
        streams=value.get('streams',[]); visual=[s for s in streams if s.get('codec_type')=='video']
        if len(visual)!=1: raise ScreensaverError('A single visual stream is required','invalid_media')
        video=visual[0]; width=int(video['width']); height=int(video['height']); frames=int(video.get('nb_read_frames') or 1)
        duration=float(value.get('format',{}).get('duration') or 0)
        if not 0<width*height<=MAX_PIXELS or width<=0 or height<=0 or not 0<=duration<=MAX_DURATION or not 0<frames<=18000:
            raise ScreensaverError('Media exceeds playback budgets','invalid_media')
        if frames>1 and duration<=0:
            try: duration=frames/float(Fraction(video['r_frame_rate']))
            except (ValueError,ZeroDivisionError,KeyError): raise ScreensaverError('Unknown animation timing','invalid_media')
        return dict(width=width,height=height,frames=frames,duration=duration,animated=frames>1,
            codec=video.get('codec_name'),format=fmt,audio=any(s.get('codec_type')=='audio' for s in streams))

    def run(self,args,directory,checkpoint,progress,duration=0,timeout=180):
        telemetry=Path(directory)/'.progress'
        telemetry.unlink(missing_ok=True)
        def check():
            checkpoint()
            if telemetry.is_file():
                if telemetry.stat().st_size>256*1024: raise ScreensaverError('Progress overflow','invalid_media')
                with telemetry.open('rb') as stream:
                    stream.seek(max(0,telemetry.stat().st_size-4096)); lines=stream.read(4096).decode(errors='replace').splitlines()
                values=dict(line.split('=',1) for line in lines if '=' in line)
                # FFmpeg can report N/A before the first timestamp, and this
                # bounded tail may end in a partial write. Progress telemetry
                # is optional; neither case invalidates the actual media.
                try: micros=float(values.get('out_time_us',''))
                except ValueError: micros=float('nan')
                known=math.isfinite(micros) and micros>=0 and duration>0
                progress(min(.99,micros/1000000/duration) if known else None)
        command=[self.runner.ffmpeg,'-v','error','-xerror','-nostdin','-y','-threads','2',
                 '-filter_threads','2','-max_alloc','134217728','-progress',str(telemetry),*args]
        try: self.runner._run(command,directory,check,timeout)
        finally: telemetry.unlink(missing_ok=True)

    def prepare(self,source,directory,options,checkpoint,progress,static=False):
        if not self.runner.ffmpeg: raise ScreensaverError('Video tools are missing','ffmpeg_missing')
        source=Path(source); directory=Path(directory); directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        progress('validating',None); info=self.inspect(source,checkpoint)
        if static and info['animated'] or not static and not info['animated']:
            raise ScreensaverError('Select a genuine animation or a static cover','static_selection')
        inputs=['-protocol_whitelist','file,pipe']+(['-ignore_loop','1'] if info['format']=='webp' and info['animated'] else [])+['-i',str(source)]
        if info['format']=='webp' and info['animated']:
            # Animated WebP demuxing is missing in many otherwise valid FFmpeg
            # builds. Validate every embedded image in ONE explicit image pipe;
            # the browser keeps the original RIFF for correct blend/disposal.
            pipe=directory/'.webp-image-pipe'
            try:
                with source.open('rb') as stream,pipe.open('xb') as target:
                    stream.seek(12)
                    while True:
                        checkpoint(); header=stream.read(8)
                        if not header: break
                        if len(header)!=8: raise ScreensaverError('Truncated WebP','invalid_media')
                        kind=header[:4]; length=int.from_bytes(header[4:8],'little')
                        if kind==b'ANMF':
                            if length<16 or length>128*1024*1024: raise ScreensaverError('Invalid WebP frame','invalid_media')
                            stream.read(16); payload=stream.read(length-16)
                            if len(payload)!=length-16: raise ScreensaverError('Truncated WebP','invalid_media')
                            target.write(b'RIFF'+(len(payload)+4).to_bytes(4,'little')+b'WEBP'+payload)
                        else: stream.seek(length,1)
                        if length%2: stream.seek(1,1)
                inputs=['-protocol_whitelist','file,pipe','-f','image2pipe','-c:v','webp','-i',str(pipe)]
                self.run(inputs+['-an','-sn','-f','null','-'],directory,checkpoint,lambda p:progress('validating',p),info['duration'])
                thumb=directory/'thumbnail.jpg'
                self.run(inputs+['-vf','scale=640:360:force_original_aspect_ratio=decrease','-frames:v','1','-an','-sn',str(thumb)],directory,checkpoint,lambda _:None,timeout=30)
                tv=directory/'original.webp';shutil.copyfile(source,tv)
                return dict(tv=tv,thumbnail=thumb,original_preserved=True,**info)
            finally: pipe.unlink(missing_ok=True)
        # A complete bounded decode once, not once per subsequent state query.
        self.run(inputs+['-an','-sn','-f','null','-'],directory,checkpoint,lambda p:progress('validating',p),info['duration'])
        native=info['format'] in {'gif','webp','png','jpg'} or info['codec'] in {'vp8','vp9'} and not info['audio']
        tv=directory/('original.'+info['format'] if native else 'compatible.webm')
        if native:
            if source.stat().st_size>options.get('_storage_output_bytes',float('inf')):raise ScreensaverError('Storage budget reached','storage_limit')
            shutil.copyfile(source,tv)
        else:
            progress('converting',0)
            self.run(inputs+['-an','-sn','-vf','scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p',
                '-c:v','libvpx-vp9','-threads','2','-deadline','realtime','-cpu-used','6','-crf','28','-b:v','0',
                *(['-fs',str(options.get('_storage_output_bytes',options['max_video_mib']*1024*1024))] if options.get('_storage_output_bytes',options['max_video_mib']) else []),str(tv)],directory,checkpoint,lambda p:progress('converting',p),info['duration'])
            converted=self.inspect(tv,checkpoint)
            if abs(converted['duration']-info['duration'])>.25: raise ScreensaverError('Incomplete conversion','invalid_media')
        thumb=directory/'thumbnail.jpg'
        self.run(inputs+['-vf','scale=640:360:force_original_aspect_ratio=decrease','-frames:v','1','-an','-sn',str(thumb)],
            directory,checkpoint,lambda _:None,timeout=30)
        if not thumb.is_file() or not 0<thumb.stat().st_size<=512*1024: raise ScreensaverError('Invalid preview','invalid_media')
        return dict(tv=tv,thumbnail=thumb,original_preserved=native,**info)

    def animate_still(self,source,directory,options,checkpoint,progress):
        """Optional offline TV derivative. Covers/logos never call this path."""
        source=Path(source); directory=Path(directory)
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        info=self.inspect(source,checkpoint)
        if info['animated']: raise ScreensaverError('A still image is required','static_selection')
        spec=still_motion_spec(options); duration=spec['seconds']; frames=round(duration*30)
        # Preserve aspect ratio, including 16:10 and square images. Never
        # upscale a small source into a large stored video just for movement.
        scale=min(1,1280/info['width'],720/info['height'])
        width=max(2,int(info['width']*scale)//2*2)
        height=max(2,int(info['height']*scale)//2*2)
        # Stable off-centre framing per source; no random changes on replay.
        digest=hashlib.sha256()
        with source.open('rb') as stream:
            while block:=stream.read(65536): checkpoint(); digest.update(block)
        seed=digest.digest()
        ax=.28 if seed[0]&1 else .72; ay=.32 if seed[1]&1 else .68
        phase=f'(2*PI*on/{frames})'
        filters=(f'scale={width*2}:{height*2}:flags=lanczos,'
                 f"zoompan=z='{STILL_MIN_ZOOM}+{STILL_ZOOM_TRAVEL/2}*(1-cos({phase}))':"
                 f"x='(iw-iw/zoom)*({ax}+{STILL_PAN_X}*sin({phase}))':"
                 f"y='(ih-ih/zoom)*({ay}-{STILL_PAN_Y}*sin({phase}))':"
                 f'd={frames}:s={width}x{height}:fps=30,setsar=1,format=yuv420p')
        target=directory/'still-motion.webm'
        progress('converting',0)
        self.run(['-protocol_whitelist','file,pipe','-i',str(source),'-vf',filters,
                  '-frames:v',str(frames),'-an','-sn','-c:v','libvpx-vp9','-threads','2',
                  '-deadline','realtime','-cpu-used','6','-crf','24','-b:v','0',
                  *(['-fs',str(options.get('_storage_output_bytes',options['max_video_mib']*1024*1024))] if options.get('_storage_output_bytes',options['max_video_mib']) else []),str(target)],
                 directory,checkpoint,lambda p:progress('converting',p),duration)
        result=self.inspect(target,checkpoint)
        if result['frames']!=frames or abs(result['duration']-duration)>.1:
            raise ScreensaverError('Incomplete still animation','invalid_media')
        return dict(tv=target,**result)

    def smooth(self,source,directory,options,checkpoint,progress):
        info=self.inspect(source,checkpoint); fps=options['smoothing_fps']; mode=options['smoothing_mode']
        if info['frames']/max(.001,info['duration'])>=fps-.5: return None
        w,h=(1920,1080) if mode=='quality' else (1280,720)
        extent=f"'min(iw,{w})':'min(ih,{h})'"
        algorithm='mi_mode=blend' if mode=='blend' else ('mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1' if mode=='quality' else 'mi_mode=mci:mc_mode=obmc:me_mode=bidir:search_param=16:vsbmc=0')
        target=Path(directory)/f'smooth-{mode}-{fps}.webm'
        filters=f'scale={extent}:force_original_aspect_ratio=decrease:force_divisible_by=2,tpad=stop_mode=clone:stop_duration=1,minterpolate=fps={fps}:{algorithm},format=yuv420p'
        inputs=(['-ignore_loop','1'] if info['format']=='webp' else [])+['-protocol_whitelist','file,pipe','-i',str(source)]
        self.run(inputs+['-vf',filters,'-t',str(info['duration']),'-an','-sn','-c:v','libvpx-vp9' if mode=='quality' else 'libvpx',
            '-threads','2','-deadline','realtime','-cpu-used','6','-b:v','0' if mode=='quality' else '4000000',
            '-crf','28' if mode=='quality' else '10',*(['-fs',str(options.get('_storage_output_bytes',options['max_video_mib']*1024*1024))] if options.get('_storage_output_bytes',options['max_video_mib']) else []),str(target)],
            directory,checkpoint,lambda p:progress('smoothing',p),info['duration'],timeout=3600)
        result=self.inspect(target,checkpoint)
        if abs(result['duration']-info['duration'])>.15 or result['frames']<info['frames']:
            target.unlink(missing_ok=True); raise ScreensaverError('Incomplete smoothing','invalid_media')
        return target
