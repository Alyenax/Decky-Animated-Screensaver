"""Read-only, metadata-only recovery summaries. Never probe or alter media."""
import re

def skipped_media(game,role):
    failures=game.get('media_failures',{});failure=failures.get(role,{}) if isinstance(failures,dict) else {}
    return failure if isinstance(failure,dict) and failure.get('disposition')=='skipped' else {}

def game_problem(game, ready=False):
    if game.get('excluded'):
        return None
    for field, role in (('error','animation'),('cover_error','cover'),
                        ('logo_error','logo'),('smoothing_error','smoothing'),('motion_error','animation')):
        code=game.get(field)
        if field=='error' and code=='animation_missing':continue
        # Migration to original-image transforms retires this legacy encoder
        # failure. Keep every other source/optional-media error actionable.
        if field=='motion_error' and code=='static_motion_failed' and game.get('animated') is False:continue
        failure=skipped_media(game,'background' if role=='animation' else role)
        if code and failure.get('code')==code:continue
        if code:
            problem=dict(appid=game['appid'],name=game.get('name',''),role=role,
                        code=code if isinstance(code,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',code) else 'unexpected_error',
                        retained_media=bool(ready))
            failure=skipped_media(game,'background' if role=='animation' else role)
            if failure.get('code')==code:problem['skipped']=True
            return problem
    if game.get('status')=='error' and not skipped_media(game,'background'):
        return dict(appid=game['appid'],name=game.get('name',''),role='animation',
                    code='animation_missing' if game['status']=='missing' else 'unexpected_error',
                    retained_media=bool(ready))
    return None
