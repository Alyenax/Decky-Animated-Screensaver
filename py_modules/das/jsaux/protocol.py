"""Pinned JSAUX Broker contract, not a serial/USB implementation."""
import json
import math
import re

PROTOCOL = "jsaux-broker"
VERSION = "1.0"
CONTRACT_REVISION = 4
CONTRACT_COMMIT = "8fba79bda684102eb0e3fdd01692fe46fdcff131"
CONTRACT_SHA256 = "480b8abaa9ee5669106f55fae46bb9acf0213abf4d28eb05568c499eccc4c11f"
PROFILE = "gca-collection-rgb332-opaque-v1"
MESSAGE_BYTES = 65536
OPERATIONS = frozenset(("hello", "status", "register_content", "content_chunk",
    "commit_content", "abort_content", "acquire_display", "player_ready",
    "renew_display", "operation_status", "tv_started", "release_display", "goodbye"))
LIMITS = dict(message_bytes=65536, chunk_bytes=24576, max_content_bytes=196608,
    canvas_width=64, canvas_height=54, max_frames=6000, max_loop_duration_cs=2400000,
    min_frame_delay_cs=1, max_frame_delay_cs=65535, max_contents=4,
    max_cached_content_bytes=786432, max_uploads=1, max_staging_bytes=196608,
    max_total_content_staging_bytes=1048576, min_free_disk_bytes=67108864,
    validator_memory_bytes=67108864, validator_cpu_ms=5000, validator_wall_ms=10000,
    upload_idle_ms=60000, max_connections=2, max_resident_clients=4,
    client_gc_idle_ms=10000, max_requests_per_second=20, request_burst=40,
    rpc_deadline_ms=2000, idle_read_ms=5000, renew_interval_ms=2000, lease_ms=8000,
    steam_freshness_ms=5000, sync_wait_ms=15000, max_clock_uncertainty_ms=50,
    clock_sample_max_age_ms=30000, screensaver_min_attempt_interval_ms=5000)
SAFE_INTEGER = 9007199254740991
ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ERROR = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


class BrokerError(Exception):
    """Safe public error. Never contains endpoint, capability or raw exceptions."""
    def __init__(self, code, retry_after_ms=0, *, uncertain=False):
        self.code = code if isinstance(code, str) and ERROR.fullmatch(code) else "INTERNAL_ERROR"
        self.retry_after_ms = max(0, min(int(retry_after_ms), SAFE_INTEGER))
        self.uncertain = bool(uncertain)
        super().__init__(self.code)

    def public(self):
        return dict(code=self.code, retry_after_ms=self.retry_after_ms, uncertain=self.uncertain)


def integer(value, minimum=0, maximum=SAFE_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        raise BrokerError("PROTOCOL_INVALID")
    return value


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise BrokerError("INVALID_REQUEST")
    return value


def digest(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise BrokerError("INVALID_REQUEST")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BrokerError("PROTOCOL_INVALID")
        result[key] = value
    return result


def _depth(value, level=0):
    if level > 8:
        raise BrokerError("PROTOCOL_INVALID")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise BrokerError("PROTOCOL_INVALID")
            _depth(child, level + 1)
    elif isinstance(value, list):
        for child in value:
            _depth(child, level + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise BrokerError("PROTOCOL_INVALID")
    elif type(value) is int and abs(value) > SAFE_INTEGER:
        raise BrokerError("PROTOCOL_INVALID")


def decode(raw):
    if len(raw) > MESSAGE_BYTES:
        raise BrokerError("PROTOCOL_INVALID")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(BrokerError("PROTOCOL_INVALID")))
        _depth(value)
    except (ValueError, UnicodeError, RecursionError):
        raise BrokerError("PROTOCOL_INVALID") from None
    if not isinstance(value, dict):
        raise BrokerError("PROTOCOL_INVALID")
    return value


def encode(value, limit=MESSAGE_BYTES):
    _depth(value)
    try:
        raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, RecursionError):
        raise BrokerError("INVALID_REQUEST") from None
    if len(raw) > min(limit, MESSAGE_BYTES):
        raise BrokerError("INVALID_REQUEST")
    return raw


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise BrokerError("PROTOCOL_INVALID")


def validate_hello(value):
    keys(value, ("negotiated_version", "contract_revision", "connection_id", "broker_mono_ms",
        "clock_domain", "capabilities", "limits", "state"))
    batched=value["negotiated_version"]=="1.2" and value["contract_revision"]==6
    extended=batched or value["negotiated_version"]=="1.1" and value["contract_revision"]==5
    if (not extended and (value["negotiated_version"] != VERSION or value["contract_revision"] not in (3,CONTRACT_REVISION))
            or value["clock_domain"] != "linux-host-clock-monotonic"):
        raise BrokerError("VERSION_UNSUPPORTED")
    identifier(value["connection_id"])
    integer(value["broker_mono_ms"])
    caps = value["capabilities"]
    keys(caps, ("operations", "content_profiles", "modes", "serial_owner", "tv_only_independent",
        "hardware_fallback", "software_coordinated_start", "physical_alignment_measured",
        "content_registration_without_usb", *( ["autonomous_player"] if extended else []), *(["autonomous_batches"] if batched else [])))
    if (not isinstance(caps["operations"], list) or set(caps["operations"]) != (OPERATIONS|{"publish_player","remove_player","calibrate_player","player_status"}|({"publish_player_batch"} if batched else set()) if extended else OPERATIONS)
            or caps["content_profiles"] != [PROFILE] or set(caps["modes"]) != {"sync", "async"}
            or caps["serial_owner"] != "GabeCubeAura" or caps["tv_only_independent"] is not True
            or caps["hardware_fallback"] is not False or caps["software_coordinated_start"] is not True
            or caps["physical_alignment_measured"] is not False
            or caps["content_registration_without_usb"] is not True):
        raise BrokerError("VERSION_UNSUPPORTED")
    if batched and caps["autonomous_batches"] is not True:raise BrokerError("VERSION_UNSUPPORTED")
    if extended and caps["autonomous_player"] is not True:raise BrokerError("VERSION_UNSUPPORTED")
    limits = value["limits"]
    keys(limits, LIMITS)
    # Capacity may be restricted, but budgets/deadlines may never be silently enlarged.
    # Free-space floor, minimum delay and cooldown may only become more conservative.
    floors = {"min_free_disk_bytes", "min_frame_delay_cs", "screensaver_min_attempt_interval_ms"}
    exact = {"canvas_width", "canvas_height"}
    for name, baseline in LIMITS.items():
        current = integer(limits[name], 1)
        if ((name in exact and current != baseline)
                or (name in floors and current < baseline)
                or (name not in floors | exact and current > baseline)):
            raise BrokerError("VERSION_UNSUPPORTED")
    if limits['sync_wait_ms'] != (2500 if value['contract_revision']==3 else 15000):
        raise BrokerError('VERSION_UNSUPPORTED')
    validate_status(value["state"])
    return value


def validate_status(value):
    keys(value, ("hardware", "policy", "steam", "ownership", "flash", "lease", "cache"))
    if value["hardware"] not in ("absent", "available", "busy", "ownership-unavailable"):
        raise BrokerError("PROTOCOL_INVALID")
    keys(value["policy"], ("faceplate_enabled", "display_on", "suspended", "thermal_blocked", "priority_active", "reason"))
    for name in ("faceplate_enabled", "display_on", "suspended", "thermal_blocked", "priority_active"):
        if type(value["policy"][name]) is not bool:
            raise BrokerError("PROTOCOL_INVALID")
    _reason(value["policy"]["reason"])
    steam = value["steam"]
    keys(steam, ("observed", "observation_age_ms", "activation_id", "activation_closed"))
    if steam["observed"] not in ("active", "inactive", "unknown") or type(steam["activation_closed"]) is not bool:
        raise BrokerError("PROTOCOL_INVALID")
    if steam["observation_age_ms"] is not None:
        integer(steam["observation_age_ms"])
    if steam["activation_id"] is not None:
        identifier(steam["activation_id"])
    own = value["ownership"]
    keys(own, ("logical_owner", "serial_busy", "device_key"))
    if own["logical_owner"] not in ("GabeCubeAura", "other", "none") or type(own["serial_busy"]) is not bool:
        raise BrokerError("PROTOCOL_INVALID")
    if own["device_key"] is not None:
        identifier(own["device_key"])
    flash = value["flash"]
    keys(flash, ("allowed", "retry_after_ms", "policy_revision", "receipt_state"))
    if type(flash["allowed"]) is not bool or flash["receipt_state"] not in ("known", "uncertain"):
        raise BrokerError("PROTOCOL_INVALID")
    integer(flash["retry_after_ms"])
    identifier(flash["policy_revision"])
    keys(value["cache"], ("completed_count", "completed_bytes", "staging_bytes", "evictable_count"))
    for number in value["cache"].values():
        integer(number)
    if value["lease"] is not None:
        validate_lease(value["lease"])
    return value


def _reason(value):
    if value is not None and (not isinstance(value, str) or not ERROR.fullmatch(value)):
        raise BrokerError("PROTOCOL_INVALID")


def validate_lease(value, events=False):
    expected = {"lease_id", "generation", "session_id", "activation_id", "content_id", "operation_id", "mode",
        "lease_state", "transfer_state", "alignment_state", "restore_state", "expires_in_ms",
        "deadline_mono_ms", "candidate", "reason", "retry_after_ms"}
    if events:
        expected.add("event_ages_ms")
    keys(value, expected)
    for name in ("lease_id", "session_id", "activation_id", "content_id", "operation_id"):
        identifier(value[name])
    integer(value["generation"], 1)
    for name in ("expires_in_ms", "retry_after_ms"):
        integer(value[name])
    if value["deadline_mono_ms"] is not None:
        integer(value["deadline_mono_ms"])
    _reason(value["reason"])
    enums = dict(mode=("sync", "async"), lease_state=("pending", "active", "revoking", "released", "expired", "preempted", "rejected"),
        transfer_state=("not-started", "deferred", "queued", "transferring", "confirmed", "unconfirmed", "failed", "cancelled"),
        alignment_state=("not-requested", "waiting", "candidate", "software-coordinated", "unconfirmed", "abandoned"),
        restore_state=("not-needed", "pending", "deferred", "confirmed", "unconfirmed", "blocked"))
    for name, choices in enums.items():
        if value[name] not in choices:
            raise BrokerError("PROTOCOL_INVALID")
    candidate = value["candidate"]
    if candidate is not None:
        keys(candidate, ("candidate_id", "deadline_mono_ms", "phase_basis", "optical_alignment"))
        identifier(candidate["candidate_id"])
        integer(candidate["deadline_mono_ms"])
        if candidate["phase_basis"] != "gif-end-ack-assumption" or candidate["optical_alignment"] != "unknown":
            raise BrokerError("PROTOCOL_INVALID")
    if events:
        ages = value["event_ages_ms"]
        if not isinstance(ages, dict) or len(ages) > 8:
            raise BrokerError("PROTOCOL_INVALID")
        for name, number in ages.items():
            identifier(name)
            integer(number)
    return value
