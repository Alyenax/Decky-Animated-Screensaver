"""One native-pixel crop for both offline preparation and software preview."""
from .protocol import BrokerError


def framing_filter(framing='square', crop=None):
    if framing not in ('square', 'fill'):
        raise BrokerError('INVALID_REQUEST')
    crop = {} if crop is None else crop
    if not isinstance(crop, dict) or set(crop) - {'x', 'y'}:
        raise BrokerError('INVALID_REQUEST')
    for value in crop.values():
        if type(value) not in (int, float) or not 0 <= value <= 100:
            raise BrokerError('INVALID_REQUEST')
    x, y = (crop.get(axis, 50) / 100 for axis in ('x', 'y'))
    width = 64 if framing == 'fill' else 54
    result = (f'scale={width}:54:force_original_aspect_ratio=increase,'
              f'crop={width}:54:(iw-{width})*{x}:(ih-54)*{y}')
    # Preserve the existing full square. Filling uses the whole 64x54 matrix,
    # never independent x/y scaling or a stretched 1:1 source.
    return result if framing == 'fill' else result + ',pad=64:54:5:0:black'
