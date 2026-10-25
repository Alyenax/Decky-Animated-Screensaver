"""Local calibration and bounded timing evidence. No hardware operations."""
import hashlib

MAX_CORRECTION_MS = 10000
MAX_CALIBRATIONS = 8


def calibration_key(device, collection):
    if (not isinstance(device, str) or not 1 <= len(device) <= 80
            or not isinstance(collection, str) or len(collection) != 64
            or any(c not in '0123456789abcdef' for c in collection)):
        return None
    # Connection identity is supplied by GCA. Never export its raw device key.
    return hashlib.sha256((device + ':' + collection).encode()).hexdigest()


def correction(value):
    return type(value) is int and -MAX_CORRECTION_MS <= value <= MAX_CORRECTION_MS and value % 100 == 0


def saved_calibrations(raw):
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in list(raw.items())[-MAX_CALIBRATIONS:]
            if isinstance(key, str) and len(key) == 64
            and all(c in '0123456789abcdef' for c in key) and correction(value)}


def reference(operation, sent_ms, received_ms):
    """Bound the broker confirmation-event clock using its existing event age.

    Both backends use host CLOCK_MONOTONIC. The event age is sampled during the
    RPC, so half its round trip bounds our midpoint estimate. This is software
    receipt evidence, not a measurement of the first optically visible frame.
    """
    ages = operation.get('event_ages_ms')
    age = ages.get('candidate') if isinstance(ages, dict) else None
    if (type(age) is not int or not 0 <= age <= 15000
            or type(sent_ms) is not int or type(received_ms) is not int
            or not 0 <= received_ms - sent_ms <= 50 or sent_ms < age):
        return None
    return dict(reference_mono_ms=(sent_ms + received_ms) // 2 - age,
                uncertainty_ms=(received_ms - sent_ms + 1) // 2 + 1,
                basis='broker-confirmation-event')
