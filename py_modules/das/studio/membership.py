"""One selection contract for workspace counts, preparation and both exports."""

def member(game):
    # Explicit modern membership wins; retain the established legacy fallback.
    return bool(game.get('collection_member',not game.get('excluded') or bool(game.get('media'))))

def included(game):
    return member(game) and not game.get('excluded',False)
