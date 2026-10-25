from .catalog import ScreensaverError
MAX_CANDIDATES = 36

def _safe_asset(value):
    """Keep provenance, never an auth key or arbitrary provider payload."""
    from das.provider import _trusted_url,_trusted_thumbnail
    if not isinstance(value, dict) or not _trusted_url(value.get("url")):
        raise ScreensaverError("Invalid Screensaver artwork", "invalid_asset")
    try:
        identifier = int(value.get("id", 0))
        width, height = int(value.get("width", 0)), int(value.get("height", 0))
    except (ValueError, TypeError, OverflowError) as error:
        raise ScreensaverError("Invalid Screensaver artwork dimensions", "invalid_asset") from error
    if (identifier <= 0 or width < 0 or height < 0 or max(width, height) > 16384
            or width * height > 40_000_000
            or width and height and not 1 / 32 <= width / height <= 32):
        raise ScreensaverError("Screensaver artwork dimensions exceed the decode budget", "invalid_asset")
    result = {"id": identifier, "kind": "hero" if value.get("kind") == "hero" else "grid",
              "width": width, "height": height, "animated": bool(value.get("animated")),
              "score": int(value.get("score", 0) or 0), "url": str(value["url"]),
              "author": str(value.get("author", ""))[:80]}
    thumb = value.get("thumb", "")
    result["thumb"] = str(thumb) if _trusted_thumbnail(thumb) else result["url"]
    for key in ("crop_x", "crop_y"):
        result[key] = max(0, min(100, int(value.get(key, 50))))
    return result


def rank_assets(assets):
    """Animated heroes first, animated landscape grids second. Never stills.

    Duration, decoded codec and loop quality are not in SGDB's search metadata.
    They are deliberately not invented as ranking measurements.
    """
    unique = {}
    for raw in assets:
        try:
            asset = _safe_asset(raw)
        except (ScreensaverError, ValueError, TypeError):
            continue
        if asset['animated'] is not True:
            continue
        ratio = asset["width"] / max(1, asset["height"])
        # Portrait grids are not a suitable unattended TV fallback. Manual hero
        # selection remains available without stretching any image.
        if asset["kind"] == "grid" and ratio < 1.45:
            continue
        priority = 0 if asset["kind"] == "hero" else 1
        asset["rank_priority"] = priority
        unique[(asset["kind"], asset["id"])] = asset
    return sorted(unique.values(), key=lambda item: (
        item["rank_priority"], -item["score"],
        -min(item["width"] * item["height"], 3840 * 2160), item["id"],
    ))[:MAX_CANDIDATES]
