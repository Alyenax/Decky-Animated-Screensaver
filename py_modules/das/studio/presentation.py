"""The single bounded presentation specification shared by both outputs."""

from .membership import included

def ready_games(store):
    return [game for game in store.games() if included(game) and store.ready(game)]

def manifest(games,options):
    return dict(version=2,order=[game['appid'] for game in games],
                page_ms=options['scene_seconds']*1000,transition_ms=400,
                transition_included=True,orientation=0)
