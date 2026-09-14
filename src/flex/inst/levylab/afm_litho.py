"""FLEX driver for the Levy Lab conductive-AFM lithography service (``afm-litho``).

The service publishes a JSON-RPC 2.0 provider on **two** ZMQ REP sockets
(``docs/FLEX_PROVIDER.md`` in the afm-litho repo):

===========  ======  ==========================================================
Port         Socket  Serves
===========  ======  ==========================================================
29180        command every mutating verb, serialised -- plus the read table
29181        read    the read table only; it can never queue behind a command
===========  ======  ==========================================================

This driver therefore keeps **two** links. ``super().__init__`` opens the
command socket (with the eager ``ACK`` connect check FLEX does for every ZMQ
instrument); a second :class:`~flex.inst.base.Instrument` opens the read
socket, and every ``get*`` / polling call goes there. That is the whole point
of the split: a 5 Hz ``getState`` loop must not stall behind a blocking
command once mutating verbs land.

**Milestone 3 wired the control plane.** ``acquireControl`` / ``releaseControl``
/ ``heartbeat`` and the token-free fail-safe verbs ``abort`` / ``safePark`` are
**command-socket only**, matched by ``ControlHeld`` / ``ControlRevoked`` /
``ControlRequired`` exceptions for the arbitration error codes.

**Asana 07 added scan control**: ``getMode``, ``setMode``, ``startApproach``,
``withdraw``, ``setZGain``, ``startScan``, ``setContinuous`` -- the first
verbs that can drive the tip toward a surface -- plus the blocking
convenience helpers :meth:`AFMLitho.approach` and :meth:`AFMLitho.scan` and
the :meth:`AFMLitho.session` context manager. Every verb here requires a held
token except :meth:`AFMLitho.withdraw`, matched by :class:`Busy` (-32020),
:class:`Refused` (-32021) and :class:`BackendMismatch` (-32010) exceptions.

**This build (Asana 09) adds write control**: ``loadPattern``, ``startWrite``
and the token-free ``abortWrite`` -- the first verb that puts VOLTAGE on a
tip already on the surface -- plus the blocking :meth:`AFMLitho.write`
helper. There is no size refusal (Joe's decision, 2026-09-11) and, as of a
second decision the same day, no more 8,192-point split inside a stroke
either -- the tip no longer lifts in the middle of a line the user drew as
one stroke. A big object simply CHAINS at the DSP's 87,000-point out-wave
cap instead: ``loadPattern`` reports the true out-wave count via
``segments`` (one arm per stroke, plus one per chain chunk) alongside
``strokes`` (continuous tip paths) and ``multi_segment_objects``, instead of
raising. There is no ``max_segment_points`` key on this wire any more.
:class:`PatternTooLarge` is kept for backward compatibility -- see its
docstring. ``startMeasure`` / ``executePass`` are still named by the
provider and answer ``-32601 "not implemented in this build"`` -- see
:data:`RESERVED_VERBS`.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from flex.inst.base import Instrument, ZMQInstrumentError

#: Added to a published ``bound_s`` before it is used as a per-call timeout.
#: Small on purpose: ``bound_s`` is already the provider's honest worst case
#: for the handler, so the margin covers only the round trip and scheduling.
#: A large margin would swamp the fast reads -- which are most of them -- and
#: put every read back at the multi-second wait :data:`MIN_TIMEOUT` exists to
#: bound.
TIMEOUT_MARGIN = 0.5

#: No derived timeout is ever shorter than this, however small the bound. A
#: read whose bound is 20 ms still gets a second, because the number that
#: matters for a *timeout* is "how long before I call this socket dead", and
#: one round trip on a loaded PC is not a reason to.
MIN_TIMEOUT = 1.0

#: How many times ``auto_decimate=True`` will re-ask using the provider's
#: ``required_decimate``. Each attempt strictly increases the decimation, so a
#: small bound is enough; it exists to stop a pathological loop, not to retry.
MAX_DECIMATE_ATTEMPTS = 4

#: JSON-RPC code the provider uses for "invalid params", which is also how it
#: reports an inline result over ``inline_cap_bytes``.
INVALID_PARAMS = -32602

#: The most :meth:`AFMLitho.approach` / :meth:`AFMLitho.scan` will sleep on a
#: published ``est_s`` before their first poll. `est_s` is honest -- it is
#: what a script SLEEPS on -- but a long estimate (a 1800 s scan) must not
#: turn the first poll into a multi-minute wait with no dead-man beat; the
#: `heartbeat_context()` these helpers run inside covers the rest.
PRE_POLL_SLEEP_CAP = 2.0

#: How long :meth:`AFMLitho.scan` / :meth:`AFMLitho.write` will keep polling
#: ``get_scan_result`` / ``get_write_result`` for the record to settle
#: (``completed`` or ``aborted``) once ``get_state()`` has already left the
#: busy state. The provider's own pump can lag a tick behind thread death --
#: a ``getState`` read racing the worker's own persistence/close step -- so a
#: bare ``{completed: false, aborted: false}`` fetched right at that instant
#: is a transient READ, not a finished (or failed) run; a script must never
#: see it as either. This is a bounded grace window for that lag, not a
#: normal wait -- past it, :meth:`AFMLitho._await_terminal_result` raises
#: rather than let a caller read an unsettled record as done.
SETTLE_CAP_S = 10.0
SETTLE_POLL_S = 0.2

#: The arbitration error codes (``docs/FLEX_PROVIDER.md`` "Error codes"),
#: mapped below to typed exceptions so a script can ``except ControlRevoked``
#: rather than sniffing ``ZMQInstrumentError.code``.
CONTROL_REVOKED = -32011   #: the token WAS ours and is not any more
CONTROL_REQUIRED = -32030  #: no token, or one this service never issued
CONTROL_HELD = -32040      #: someone else is the commander right now

#: The scan-control error codes (``docs/FLEX_PROVIDER.md`` "Error codes"),
#: mapped below to :class:`BackendMismatch` / :class:`Busy` / :class:`Refused`.
BACKEND_MISMATCH = -32010  #: a mutating verb on a hardware station with no live bridge
BUSY = -32020              #: a start verb arrived while another run holds the claim
REFUSED = -32021           #: a STATE refusal (e.g. setMode with the tip engaged)

#: The fields a RELATIVE engage resolves server-side and reports on the
#: ``startApproach`` reply -- copied onto :meth:`AFMLitho.approach`'s returned
#: status, which is otherwise a plain ``getStatus`` and would drop them.
#: Beyond the three numbers of the engage itself: ``sum_v`` is the detector
#: sum the clamp was taken against (null on the twin, which models no
#: detector), ``park_z_v`` the Z the tip was parked at when the baseline was
#: read (0 V on hardware, -10 V on the twin), ``free_air_settle_s`` how long
#: the deflection was left to settle, and ``mode`` the imaging mode it was
#: resolved in. All of it is evidence ABOUT the engage, which is exactly what a
#: sweep report has to carry -- a setpoint with no record of what it was
#: resolved against cannot be checked afterwards.
APPROACH_RESOLUTION_KEYS = ("free_air_v", "setpoint_relative_v", "setpoint",
                            "sum_v", "park_z_v", "free_air_settle_s", "mode",
                            "baseline_check")

#: The subset of :data:`APPROACH_RESOLUTION_KEYS` a RELATIVE engage MUST echo
#: for :meth:`AFMLitho.start_approach` to trust the reply at all. A provider
#: that doesn't implement ``setpoint_relative_v`` has no reason to send any of
#: these three -- it just ignores the unknown param -- so their absence is
#: the signal, not ``sum_v`` / ``park_z_v`` / etc., which a real
#: implementation may legitimately omit (``sum_v`` is null on the twin).
APPROACH_RELATIVE_REQUIRED_KEYS = ("free_air_v", "setpoint", "setpoint_relative_v")

#: The ``-32021`` :class:`Refused` reasons that mean **stop the run**, not
#: "try again". Both say the tip is not where the free-air baseline assumed it
#: was -- ``tip_not_parked`` because the last retract did not verify or Z is
#: off the park value, ``free_air_jump`` because the fresh read disagrees with
#: the last ACCEPTED baseline by more than the guard allows. Retrying either
#: just engages on the same bad premise, one attempt later; the honest answer
#: is to stop and look at the instrument.
HARD_STOP_REFUSALS = ("tip_not_parked", "free_air_jump")

#: The upper bound this driver enforces on ``setpoint_relative_v`` before
#: sending it. **A placeholder, named on purpose**: the provider has the real
#: limit (and clamps to 0.9x the detector SUM besides), and this only stops an
#: obvious typo -- a 10 that was meant to be 0.10 -- from becoming a crash the
#: instrument has to refuse. Raise it here only when the provider's own named
#: max moves.
SETPOINT_RELATIVE_MAX_V = 2.0

#: ``readDeflection``'s ``tip_state`` values that mean the tip is NOT clear of
#: the surface. ``approaching`` is one of them: a relative engage resolved
#: against a deflection read while the tip was already on its way down is not a
#: free-air baseline at all.
TIP_NOT_WITHDRAWN_STATES = ("engaged", "approaching", "scanning", "writing")

#: Verbs the provider names but does not implement in this build. Milestone 3
#: moved the five control verbs out of this set; Asana 07 moved the seven
#: scan-control verbs out; Asana 09 (this build) moved the three write-control
#: verbs out too. Listed so the driver can say *why* a call would fail
#: without sending it.
RESERVED_VERBS = (
    "startMeasure",
    "executePass",
)


class ControlHeld(ZMQInstrumentError):
    """-32040 ``control_held``: someone else is the commander.

    ``data["holder"]`` names them (``docs/FLEX_PROVIDER.md``). Raised by
    :meth:`AFMLitho.acquire_control`.
    """

    def __init__(self, message: str, code: int = CONTROL_HELD, data: Any = None):
        super().__init__(message, code=code, data=data)


class ControlRevoked(ZMQInstrumentError):
    """-32011 ``control_revoked``: the token WAS ours and is not any more --
    an operator preempted it, or the dead-man expired it. ``data["valid"]``
    is ``False``. **Do not blindly re-acquire**: a human may be at the panel.

    Raised by any token-bearing call (:meth:`AFMLitho.heartbeat` above all).
    """

    def __init__(self, message: str, code: int = CONTROL_REVOKED, data: Any = None):
        super().__init__(message, code=code, data=data)


class ControlRequired(ZMQInstrumentError):
    """-32030 ``control_required``: no token, or one this service never
    issued. Call :meth:`AFMLitho.acquire_control` first."""

    def __init__(self, message: str, code: int = CONTROL_REQUIRED, data: Any = None):
        super().__init__(message, code=code, data=data)


class BackendMismatch(ZMQInstrumentError):
    """-32010 ``backend_mismatch``: a mutating verb arrived at a station
    configured as hardware whose bridge is not live -- the silent-twin guard
    (plan Sec C.2) -- or ``setZGain`` on the twin, which has no servo to
    re-arm and would rather refuse than report a tune that never happened."""

    def __init__(self, message: str, code: int = BACKEND_MISMATCH, data: Any = None):
        super().__init__(message, code=code, data=data)


class Busy(ZMQInstrumentError):
    """-32020 ``busy``: a start verb arrived while another run holds the
    single-writer claim. **Never queues** -- poll :meth:`AFMLitho.get_state`,
    then retry. ``.run_id`` names the run in flight (``data["run_id"]``)."""

    def __init__(self, message: str, code: int = BUSY, data: Any = None):
        super().__init__(message, code=code, data=data)

    @property
    def run_id(self) -> str | None:
        return self.data.get("run_id") if isinstance(self.data, dict) else None


class Refused(ZMQInstrumentError):
    """-32021 ``refused``: a STATE refusal -- e.g. ``setMode`` while the tip is
    engaged, scanning or writing. Distinct from :class:`Busy`: retrying never
    clears it, only the state change named by ``.reason`` does (a
    ``withdraw``, most often)."""

    def __init__(self, message: str, code: int = REFUSED, data: Any = None):
        super().__init__(message, code=code, data=data)

    @property
    def reason(self) -> str | None:
        return self.data.get("reason") if isinstance(self.data, dict) else None


class PatternTooLarge(ZMQInstrumentError):
    """-32602 ``invalid_params`` from :meth:`AFMLitho.load_pattern`, shaped as
    ``.objects`` (``data["objects_over_cap"]``) -- ``[{name, points, cap},
    ...]``.

    **Kept for backward compatibility; the current provider never raises it.**
    As of Joe's 2026-09-11 decisions there is no size refusal at all, and no
    8,192-point split inside a stroke either: a big object is simply CHAINED
    at the 87,000-point out-wave cap, and :meth:`AFMLitho.load_pattern`
    reports that via ``segments``, ``strokes`` and ``multi_segment_objects``
    on a normal successful reply -- see its docstring. :meth:`load_pattern`
    still maps a ``data.objects_over_cap`` reply to this exception if the
    provider ever sends one (some other bad-argument shape it might reuse),
    so this class stays for that mapping and for any caller still catching
    it.

    Not one of :data:`_MAPPED_ERROR_TYPES` -- ``-32602`` covers many
    unrelated bad-argument cases, so :meth:`AFMLitho.load_pattern` raises
    this itself, only when ``data.objects_over_cap`` is actually present.
    """

    def __init__(self, message: str, code: int = INVALID_PARAMS, data: Any = None):
        super().__init__(message, code=code, data=data)

    @property
    def objects(self) -> list[dict[str, Any]]:
        if not isinstance(self.data, dict):
            return []
        return self.data.get("objects_over_cap") or []


class ProviderLacksCapability(RuntimeError):
    """Raised by :meth:`AFMLitho.start_approach` when ``setpoint_relative_v=``
    was sent but the ``startApproach`` reply is missing one or more of
    ``free_air_v``, ``setpoint``, ``setpoint_relative_v``.

    A provider that does not implement the relative-engage verb simply
    ignores the unknown ``setpoint_relative_v`` param rather than refusing
    it, ARC-error style -- there is no ``-32602`` to catch. Left unchecked,
    the tip engages at whatever setpoint the provider defaults to (an
    absolute one, typically 1.0 V) while the caller believes it engaged at
    free-air plus the requested offset, because nothing on the reply says
    otherwise. This is **not** a wire error code -- it is a client-side
    integrity check with no ``.code`` -- so it is a bare :class:`RuntimeError`
    subclass rather than a :class:`ZMQInstrumentError`, and is not in
    :data:`_MAPPED_ERROR_TYPES`.

    :meth:`~AFMLitho.start_approach` calls :meth:`~AFMLitho.withdraw` (bounded,
    token-free) before raising this, since the approach it can no longer
    trust may already be descending.
    """


#: Wire error code -> the typed exception :meth:`AFMLitho._command_call`
#: raises instead of a bare :class:`ZMQInstrumentError`. The raw code stays
#: reachable on the exception (``.code``), so nothing that inspects it today
#: breaks.
_MAPPED_ERROR_TYPES: dict[int, type[ZMQInstrumentError]] = {
    CONTROL_HELD: ControlHeld,
    CONTROL_REVOKED: ControlRevoked,
    CONTROL_REQUIRED: ControlRequired,
    BACKEND_MISMATCH: BackendMismatch,
    BUSY: Busy,
    REFUSED: Refused,
}


#: The two object ``kind``s :func:`chiral_spec` / :func:`rect_spec` build, and
#: the only ones ``loadPattern``'s inline ``objects`` list accepts. A spec with
#: any other ``kind`` is a client-side ``ValueError`` rather than a round trip
#: that comes back ``-32602``.
OBJECT_KINDS = ("chiral", "region")

#: The two legal handednesses of a chiral wire. ``+1`` and ``-1`` name the two
#: senses of the transverse modulation; WHICH physical chirality each one is has
#: NOT been confirmed by Joe (see :func:`chiral_spec`), so this driver only
#: enforces that it is one of the two.
HANDS = (1, -1)


def _finite(value: Any, what: str) -> float:
    """``float(value)``, refusing NaN/inf and anything non-numeric, naming the
    field in the message -- a spec is built once and written many times, so a
    bad number is worth catching here rather than at the ARMFIRE."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number, got {value!r}") from None
    if math.isnan(out) or math.isinf(out):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return out


def _positive(value: Any, what: str) -> float:
    out = _finite(value, what)
    if out <= 0:
        raise ValueError(f"{what} must be > 0, got {out!r}")
    return out


def _hand(hand: Any) -> int:
    """``hand`` as the int ``+1`` / ``-1``. ``True`` / ``False`` are refused
    outright: ``bool`` is an ``int`` in Python and ``True == 1`` would sail
    through as "right-handed" from a caller who meant a flag."""
    if isinstance(hand, bool):
        raise ValueError(f"hand must be 1 or -1, not a bool ({hand!r})")
    try:
        out = int(hand)
    except (TypeError, ValueError):
        raise ValueError(f"hand must be 1 or -1, got {hand!r}") from None
    if out not in HANDS:
        raise ValueError(f"hand must be 1 or -1, got {hand!r}")
    return out


def _points_um(points: Any) -> list[list[float]]:
    """Validate an ``[[x, y], ...]`` polyline: at least two finite XY pairs."""
    if isinstance(points, (str, bytes)) or not isinstance(points, Iterable):
        raise ValueError(f"points_um must be a sequence of [x, y] pairs, got {points!r}")
    out: list[list[float]] = []
    for i, point in enumerate(points):
        if isinstance(point, (str, bytes)) or not isinstance(point, Iterable):
            raise ValueError(f"points_um[{i}] must be an [x, y] pair, got {point!r}")
        pair = list(point)
        if len(pair) != 2:
            raise ValueError(
                f"points_um[{i}] must be an [x, y] pair, got {len(pair)} value(s)"
            )
        out.append([_finite(pair[0], f"points_um[{i}][0]"),
                    _finite(pair[1], f"points_um[{i}][1]")])
    if len(out) < 2:
        raise ValueError(f"points_um needs at least 2 points, got {len(out)}")
    return out


def chiral_spec(
    *,
    points_um: Any,
    lambda_um: float,
    y_amp_um: float,
    v0: float,
    v_k: float,
    phase_deg: float,
    hand: int = 1,
    name: str | None = None,
    speed_um_s: float | None = None,
) -> dict[str, Any]:
    """One ``{"kind": "chiral", ...}`` object spec for :meth:`AFMLitho.load_pattern`.

    A chiral wire is a centre line (``points_um``, an ``[[x, y], ...]``
    polyline in microns) plus a transverse modulation: wavelength
    ``lambda_um``, amplitude ``y_amp_um``, starting ``phase_deg``, and a tip
    bias that follows the modulation as ``v0 + v_k * <modulation>`` (``v0`` the
    mean bias, ``v_k`` its swing). ``speed_um_s`` overrides the provider's own
    write speed when given.

    **``hand`` is a PARAMETER, not a settled convention.** ``+1`` / ``-1``
    select the two senses of the modulation, but which of them is the physical
    chirality Joe means by "right-handed" has NOT been confirmed -- so every
    caller (``flex_afm.experiments.chiral_sweep`` included) carries it as an
    explicit knob and reports it with every result, rather than baking a guess
    into a default. Confirm it against a written wire before reading any
    handedness conclusion out of a sweep.

    Every value is validated here (finite numbers, at least two points,
    ``lambda_um > 0``, ``hand`` in :data:`HANDS`) so a typo is a ``ValueError``
    in the caller's own stack frame rather than a ``-32602`` after a round
    trip. The provider validates again, authoritatively -- notably the
    curvature clamp, which only it can apply (its reply carries
    ``profile.curvature_clamped``).
    """
    y_amp = _finite(y_amp_um, "y_amp_um")
    if y_amp < 0:
        raise ValueError(f"y_amp_um must be >= 0, got {y_amp!r}")
    spec: dict[str, Any] = {
        "kind": "chiral",
        "points_um": _points_um(points_um),
        "lambda_um": _positive(lambda_um, "lambda_um"),
        "y_amp_um": y_amp,
        "v0": _finite(v0, "v0"),
        "v_k": _finite(v_k, "v_k"),
        "phase_deg": _finite(phase_deg, "phase_deg"),
        "hand": _hand(hand),
    }
    if name is not None:
        spec["name"] = str(name)
    if speed_um_s is not None:
        spec["speed_um_s"] = _positive(speed_um_s, "speed_um_s")
    return spec


def rect_spec(
    *,
    x_um: float,
    y_um: float,
    w_um: float,
    h_um: float,
    pitch_um: float,
    voltage: float,
    name: str | None = None,
    fill: str | None = None,
    speed_um_s: float | None = None,
) -> dict[str, Any]:
    """One ``{"kind": "region", "shape": "rect", ...}`` spec -- a raster-filled
    rectangle, which is how an ERASE is written: the same tip, the same pass
    primitive, a negative ``voltage`` over the area a wire already occupies.

    ``x_um`` / ``y_um`` are the rectangle's origin and ``w_um`` / ``h_um`` its
    size (all microns); ``pitch_um`` is the raster line spacing and ``fill``
    the provider's fill strategy when a caller wants to override its default.
    ``voltage`` is the tip bias for the whole region -- deliberately NOT
    sign-checked, because an erase is exactly the negative case.

    ``pitch_um`` must be at most **half the shorter side**: a raster whose
    lines are further apart than that does not fill the rectangle, it draws a
    couple of stripes across it -- an erase that does not erase. The provider
    refuses the same thing (-32602); checking it here means finding out before
    a pattern is half-chosen. Pitch should be no wider than the written line
    itself (the twin's deposit stamp is ~0.26 um, so 0.05-0.1 um is the sane
    band for an erase that actually clears a wire).
    """
    spec: dict[str, Any] = {
        "kind": "region",
        "shape": "rect",
        "x_um": _finite(x_um, "x_um"),
        "y_um": _finite(y_um, "y_um"),
        "w_um": _positive(w_um, "w_um"),
        "h_um": _positive(h_um, "h_um"),
        "pitch_um": _positive(pitch_um, "pitch_um"),
        "voltage": _finite(voltage, "voltage"),
    }
    limit = min(spec["w_um"], spec["h_um"]) / 2
    if spec["pitch_um"] > limit:
        raise ValueError(
            f"pitch_um {spec['pitch_um']} is over half the shorter side of the "
            f"{spec['w_um']} x {spec['h_um']} um region ({limit}): that raster "
            f"does not fill the rectangle, it stripes it"
        )
    if name is not None:
        spec["name"] = str(name)
    if fill is not None:
        spec["fill"] = str(fill)
    if speed_um_s is not None:
        spec["speed_um_s"] = _positive(speed_um_s, "speed_um_s")
    return spec


def validate_object_spec(spec: Any) -> dict[str, Any]:
    """Validate ONE inline ``loadPattern`` object spec and return it normalized.

    Dispatches on ``kind`` to :func:`chiral_spec` / :func:`rect_spec`, so a
    hand-built dict gets exactly the checks (and the normalization) a spec
    built by the helpers already has -- and passing a helper's own output back
    through is a no-op. An unknown key is refused rather than forwarded: on
    this wire an unrecognised key is a typo for a real one, and sending it
    means discovering that at ``-32602`` time, with the previously loaded
    pattern still in place and a caller who thinks it replaced it.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"an object spec must be a dict, got {type(spec).__name__}")
    kind = spec.get("kind")
    if kind not in OBJECT_KINDS:
        raise ValueError(f"object spec kind must be one of {OBJECT_KINDS}, got {kind!r}")
    if kind == "region" and spec.get("shape", "rect") != "rect":
        raise ValueError(f"the only region shape this driver builds is 'rect', "
                         f"got {spec['shape']!r}")
    builder = chiral_spec if kind == "chiral" else rect_spec
    fields = {k: v for k, v in spec.items() if k not in ("kind", "shape")}
    try:
        return builder(**fields)
    except TypeError as e:  # an unknown / missing key, named by Python itself
        raise ValueError(f"invalid {kind} object spec: {e}") from None


def read_address_for(address: str) -> str:
    """The read endpoint that pairs with a command endpoint: ``port + 1``.

    The provider always binds the read socket one above the command port
    (``AFM_LITHO_FLEX_PORT`` sets the command port and nothing else), so the
    pairing is derivable and ``read_address`` rarely needs to be configured.
    """
    parts = urlsplit(address)
    if parts.port is None:
        raise ValueError(f"cannot derive a read address from {address!r}: no port")
    if not 1 <= parts.port + 1 <= 65535:
        raise ValueError(
            f"cannot derive a read address from {address!r}: port {parts.port} + 1 "
            f"is not a port. Give read_address explicitly."
        )
    host = parts.hostname or "localhost"
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    return urlunsplit((parts.scheme, f"{host}:{parts.port + 1}", "", "", ""))


class AFMLitho(Instrument):
    """Levy Lab conductive-AFM lithography service (``afm-litho``).

    Args:
        name: FLEX instrument name.
        address: the **command** endpoint (ZMQ REP), default ``29180``.
        read_address: the read-only endpoint; defaults to ``address`` port + 1.
        timeout: floor for every per-call timeout. ``None`` uses FLEX's 5 s.
            Per-call timeouts are derived from the provider's published
            ``getCapabilities.method_bounds`` and are never *shorter* than a
            method's own bound.

    Every other keyword (``connect_check``, ``metadata``, ...) is passed to
    both links.
    """

    #: Not a LabVIEW Instrument-Framework app -- there is no lvclass.
    lv_class = None

    def __init__(
        self,
        name: str = "afm",
        address: str = "tcp://localhost:29180",
        *,
        read_address: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ):
        # `timeout` is omitted entirely when None so the base Instrument's own
        # default stays the single source of that number -- a restated copy here
        # would fork silently the day FLEX changes it.
        if timeout is None:
            super().__init__(address=address, name=name, **kwargs)
        else:
            super().__init__(address=address, name=name, timeout=timeout, **kwargs)

        self._read_address = read_address or read_address_for(address)
        try:
            self._read = Instrument(address=self._read_address, name=f"{name}_read",
                                     timeout=self._timeout, **kwargs)
        except Exception:
            # a half-open instrument would poll a socket that is not there
            self.close()
            raise

        # Cache the capability block once: method_bounds is what per-call
        # timeouts are derived from, and it does not change while the service
        # runs. Tolerated as absent -- an old provider must degrade to FLEX's
        # plain default rather than refuse to construct.
        self._capabilities: dict[str, Any] = {}
        try:
            self._capabilities = self._read.call("getCapabilities") or {}
        except Exception as e:  # noqa: BLE001 - never fatal
            self.log.warning("getCapabilities failed; using default timeouts: %s", e)
        self._bounds: dict[str, float] = dict(self._capabilities.get("method_bounds") or {})
        self._check_read_port()

        # Control-plane state (plan Sec E / milestone 3). `None` until
        # `acquire_control()` succeeds; cleared by `release_control()`.
        self._token: str | None = None
        self._deadman_s: float | None = None
        # One line, so a probe transcript records which backend answered. The
        # twin and the instrument are indistinguishable from the socket alone,
        # and that is exactly the confusion `backend` exists to prevent.
        self.log.info("Connected: %s (read %s), backend=%s", address, self._read_address,
                      self._capabilities.get("backend", "unknown"))

        self.add_parameter("state", getter=self.get_state, doc="AFM state machine state")
        self.add_parameter("backend", getter=lambda: self.get_status()["backend"],
                           doc="hardware | twin | disconnected, from the live bridge")
        self.add_parameter("x", getter=lambda: self.get_telemetry()["x_um"], unit="um",
                           doc="Tip X from the last cached telemetry frame")
        self.add_parameter("y", getter=lambda: self.get_telemetry()["y_um"], unit="um",
                           doc="Tip Y from the last cached telemetry frame")
        self.add_parameter("deflection", getter=lambda: self.get_telemetry()["defl_v"],
                           unit="V", doc="Cantilever deflection")
        self.add_parameter("sum", getter=lambda: self.get_telemetry()["sum_v"], unit="V",
                           doc="Detector sum (null on the twin: it models no detector)")
        self.add_parameter("zdrive", getter=lambda: self.get_telemetry()["zdrive_v"],
                           unit="V", doc="Z drive output")

    # -- transport ------------------------------------------------------------

    @property
    def read_address(self) -> str:
        """The read-only endpoint this driver polls."""
        return self._read_address

    @property
    def capabilities(self) -> dict[str, Any]:
        """The cached ``getCapabilities`` block (fetched once, on connect)."""
        return self._capabilities

    def timeout_for(self, method: str) -> float:
        """Per-call timeout for a wire method, from the published bounds.

        ``bound_s + margin`` for a published method, this instrument's
        configured ``timeout`` for one the provider does not publish, floored
        at :data:`MIN_TIMEOUT`.

        The configured timeout is a **fallback, not a floor**. It has to be: a
        station file that sets ``timeout = 10.0`` (so that a future 30 s
        hardware verb has room) would otherwise make a 50 ms ``getState`` wait
        ten seconds before admitting the read socket is dead -- turning the
        generous setting for one call into a slow failure for every other. The
        provider publishes what each call can actually take; that number wins.
        """
        bound = self._bounds.get(method)
        derived = self._timeout if bound is None else float(bound) + TIMEOUT_MARGIN
        return max(derived, MIN_TIMEOUT)

    def _check_read_port(self) -> None:
        """Warn if the read endpoint we derived is not the one the provider
        says it bound. Never fatal, and never overrides an explicit
        ``read_address``: an SSH tunnel or an ipc:// endpoint legitimately
        disagrees with what the service sees locally."""
        published = (self._capabilities.get("ports") or {}).get("read")
        if published is None:
            return
        try:
            ours = urlsplit(self._read_address).port
        except ValueError:
            ours = None
        if ours is not None and ours != published:
            self.log.warning(
                "read socket mismatch: polling %s but the provider says it bound "
                "port %s (fine for a tunnel; otherwise the address is wrong)",
                self._read_address, published,
            )

    def _read_call(self, method: str, params: Any = None) -> Any:
        """One read, on the read-only socket, with a bound-derived timeout."""
        return self._read.call(method, params, timeout=self.timeout_for(method))

    def _command_call(self, method: str, params: Any = None, timeout: float | None = None) -> Any:
        """One call on the serialised command socket, with the error-mapping
        hook: a -32010/-32011/-32020/-32021/-32030/-32040 reply is re-raised
        as the matching typed exception (:data:`_MAPPED_ERROR_TYPES`) so a
        script can ``except ControlRevoked`` / ``except Busy`` instead of
        sniffing ``ZMQInstrumentError.code``. The raw code and ``data`` block
        survive on the re-raised exception unchanged."""
        try:
            to = timeout if timeout is not None else self.timeout_for(method)
            return self.call(method, params, timeout=to)
        except ZMQInstrumentError as e:
            exc_type = _MAPPED_ERROR_TYPES.get(e.code)
            if exc_type is None:
                raise
            raise exc_type(str(e), code=e.code, data=e.data) from e

    def close(self) -> None:
        """Close both links. The read link first, but in a try -- the
        command link is the one that can still be asked to withdraw, so it
        must be closed (and its context termed) even when tearing the read
        link down raises."""
        read = getattr(self, "_read", None)
        try:
            if read is not None:
                read.close()
        finally:
            super().close()

    # -- built-ins ------------------------------------------------------------

    def ack(self) -> str:
        """``ACK`` on the **command** socket: proves the serialised socket is
        answering, which the read socket cannot tell you."""
        return self._command_call("ACK")

    def idn(self) -> dict[str, str | None]:
        """Identity, mapped from the provider's ``IDN`` key spellings.

        Adds ``backend`` to FLEX's four standard keys: it is the provider's
        anti-fallback field (``hardware`` | ``twin`` | ``disconnected``,
        derived from the live bridge, never from a config read), and a script
        that is about to write must assert it.
        """
        result = self._read_call("IDN")
        if not isinstance(result, dict):
            return {"vendor": None, "model": str(result), "serial": None,
                    "firmware": None, "backend": None}
        return {
            "vendor": result.get("Manufacturer"),
            "model": result.get("Model") or type(self).__name__,
            "serial": result.get("Serial Number"),
            "firmware": result.get("Firmware"),
            "backend": result.get("Backend"),
        }

    def help(self, command: str | None = None) -> Any:
        """The provider's own method list, or one method's card."""
        return self._read_call("HELP", {"command": command} if command else None)

    # -- state and status (read socket) --------------------------------------

    def get_state(self) -> str:
        """One of ``disconnected|idle|approaching|engaged|scanning|writing|
        measuring|parked|fault``. A pure in-memory read: it answers inside its
        50 ms bound at all times, including mid-run."""
        return self._read_call("getState")

    def get_status(self) -> dict[str, Any]:
        """State plus the run in flight, progress, safe-park and bridge blocks."""
        return self._read_call("getStatus")

    def get_capabilities(self) -> dict[str, Any]:
        """Re-read the capability block from the provider (bypasses the cache)."""
        return self._read_call("getCapabilities")

    def get_telemetry(self) -> dict[str, Any]:
        """The last **cached** telemetry frame -- never a new instrument
        round-trip. ``age_s`` is the liveness signal: a frozen bridge shows a
        growing age while ``getState`` keeps answering instantly."""
        return self._read_call("getTelemetry")

    def get_pattern(self) -> dict[str, Any]:
        """The loaded design, one entry per object, with point *counts* and
        each object's own ``segments`` (out-waves that object is actually
        fired as -- more than its ``strokes`` for an object that CHAINS; see
        :meth:`load_pattern`) and ``strokes`` (continuous tip paths)."""
        return self._read_call("getPattern")

    def get_written(self) -> dict[str, Any]:
        """What this session has actually written. **One entry per STROKE**,
        not per object and not per fired out-wave: a filled shape that
        expands into several disconnected strokes arrives as several
        entries; a chaining object -- one continuous tip path fired as more
        than one out-wave -- is still only ONE entry, because a chain chunk
        is an arm, not a written piece."""
        return self._read_call("getWritten")

    # -- terminal run records -------------------------------------------------

    @staticmethod
    def _result_params(run_id: str | None, inline: bool, decimate: int | None) -> dict[str, Any]:
        """Only the keys the caller actually asked for go on the wire, so a
        default fetch is ``{}`` and the provider's own defaults apply."""
        params: dict[str, Any] = {}
        if run_id is not None:
            params["run_id"] = run_id
        if inline:
            params["inline"] = True
        if decimate is not None:
            params["decimate"] = decimate
        return params

    def _get_result(
        self,
        method: str,
        run_id: str | None,
        inline: bool,
        decimate: int | None,
        auto_decimate: bool,
    ) -> dict[str, Any]:
        params = self._result_params(run_id, inline, decimate)
        if not auto_decimate:
            return self._read_call(method, params)
        return self._with_auto_decimate(method, run_id, inline, decimate)

    def _with_auto_decimate(
        self, method: str, run_id: str | None, inline: bool, decimate: int | None
    ) -> dict[str, Any]:
        """Re-ask using the provider's ``required_decimate`` until it fits.

        Over ``inline_cap_bytes`` the provider *errors* rather than truncating
        (a silently shortened array is a wrong measurement) and hands back the
        decimation that would have worked, computed from the payload it was
        about to send with that step folded in -- so one retry normally
        succeeds. The loop is bounded anyway, and refuses to go backwards.
        """
        for _ in range(MAX_DECIMATE_ATTEMPTS):
            try:
                return self._read_call(method, self._result_params(run_id, inline, decimate))
            except ZMQInstrumentError as e:
                data = e.data if isinstance(e.data, dict) else {}
                required = data.get("required_decimate")
                if e.code != INVALID_PARAMS or required is None:
                    raise
                try:
                    required = int(required)
                except (TypeError, ValueError):
                    # a nonsense required_decimate is the provider's problem;
                    # surface ITS error, not a ValueError from this line
                    raise e from None
                if required < 1 or (decimate is not None and required <= decimate):
                    raise  # would re-send the same request: not a retry, a loop
                self.log.info("%s over the inline cap; retrying at decimate=%s", method, required)
                decimate = required
        raise RuntimeError(
            f"{self.name}: {method} still over the inline cap after "
            f"{MAX_DECIMATE_ATTEMPTS} attempts (last decimate={decimate})"
        )

    def get_scan_result(
        self,
        run_id: str | None = None,
        *,
        inline: bool = False,
        decimate: int | None = None,
        auto_decimate: bool = False,
    ) -> dict[str, Any]:
        """The terminal record of a scan run (the last completed one if
        ``run_id`` is omitted).

        Branch on ``aborted``, never on ``completed``: ``completed`` promises
        only that the paths in ``files`` are whole, and a scan stopped halfway
        still writes a valid, shorter frame -- so ``completed and aborted`` is
        a normal combination.

        ``inline=True`` puts the arrays in ``data``; ``decimate=N`` adds a
        strided ``preview``. Both count against the 2 MB inline cap;
        ``auto_decimate=True`` retries with whatever decimation the provider
        says would fit.
        """
        return self._get_result("getScanResult", run_id, inline, decimate, auto_decimate)

    def get_write_result(
        self,
        run_id: str | None = None,
        *,
        inline: bool = False,
        decimate: int | None = None,
        auto_decimate: bool = False,
    ) -> dict[str, Any]:
        """The terminal record of a litho write run. See :meth:`get_scan_result`.

        ``inline=True`` additionally adds ``trace``: the written path with
        the tip voltage applied along it, per object, in lab microns -- the
        x-axis a lock-in series gets correlated against. It is a pure memory
        read (bounded, last 8 runs), so it works on the twin, survives an
        :meth:`abort_write`, and never turns this call into a file scan.
        Prefer :meth:`write` (``inline=True`` by default) for a blocking call
        that already fetches this."""
        return self._get_result("getWriteResult", run_id, inline, decimate, auto_decimate)

    def get_measure_result(
        self,
        run_id: str | None = None,
        *,
        inline: bool = False,
        decimate: int | None = None,
        auto_decimate: bool = False,
    ) -> dict[str, Any]:
        """The terminal record of a measure run. See :meth:`get_scan_result`."""
        return self._get_result("getMeasureResult", run_id, inline, decimate, auto_decimate)

    # -- control / arbitration (command socket only) --------------------------
    #
    # One commander at a time -- script or operator. `acquire_control` /
    # `release_control` / `heartbeat` carry a token; `abort` / `safe_park` are
    # token-free from both sides, because an emergency stop must never be
    # blocked by arbitration. All five are `command_only` on the wire: the
    # read socket refuses them with -32601, so 29181 stays a plane that cannot
    # move the tip at all (`docs/FLEX_PROVIDER.md`).

    @property
    def token(self) -> str | None:
        """The control token this instance currently holds, or ``None``."""
        return self._token

    def require_token(self) -> str:
        """The held token, or a clear ``RuntimeError`` -- the guard every
        mutating helper (scan / write control) opens with.

        **The one intentional difference from FLEX main's own copy of this
        driver.** Pubudu's ``flex.inst.levylab.afm_litho`` *auto-acquires*
        control here (``acquire_control(self.name, deadman_s=60)``) when no
        token is held. This one RAISES instead: a script that is about to move
        the tip must say so, by taking control explicitly, rather than have a
        helper silently become the commander on its behalf. When this file is
        copied back to FLEX main this is the single method whose body differs
        on purpose -- see the README's "Sync to FLEX"."""
        if self._token is None:
            raise RuntimeError(
                f"{self.name}: no control token held -- call acquire_control() first"
            )
        return self._token

    def acquire_control(
        self, client: str, *, deadman_s: float = 30, withdraw_on_deadman: bool = False
    ) -> dict[str, Any]:
        """Become the single commander. Stores the returned token (and
        ``deadman_s``, for :meth:`heartbeat_context`) so later calls need no
        argument.

        Refused :class:`ControlHeld` (-32040) while an operator holds control
        or another script holds an unexpired token -- ``e.data["holder"]``
        names them. ``deadman_s`` is clamped server-side to ``[5, 300]`` and
        can never be disabled; both it and ``withdraw_on_deadman`` are always
        sent with explicit JSON types (a bare ``None``/non-bool would be
        ``-32602 invalid params`` on the wire).
        """
        params = {
            "client": client,
            "deadman_s": float(deadman_s),
            "withdraw_on_deadman": bool(withdraw_on_deadman),
        }
        result = self._command_call("acquireControl", params)
        self._token = result.get("token")
        self._deadman_s = result.get("deadman_s", deadman_s)
        return result

    def release_control(self, token: str | None = None) -> dict[str, Any]:
        """Give up control. Uses the stored token when ``token`` is omitted.

        **Never raises** -- a stale or unknown token is `{ok: True, stale:
        True}` on the wire already. A transport failure (the provider
        unreachable, a timeout, a reset socket) is caught here -- broadly,
        not just :class:`ZMQInstrumentError`: ``ZMQInstrument.call`` also
        raises a bare ``TimeoutError`` and re-raises ``zmq.ZMQError`` -- and
        folded into the same shape, because this call belongs in a
        ``finally`` block and a cleanup path that can itself throw is not a
        cleanup path. The local token is cleared on every path, in a
        ``finally``, so a failed release never leaves this instance believing
        it still holds a token it just tried to give up.
        """
        tok = token if token is not None else self._token
        try:
            return self._command_call("releaseControl", {"token": tok})
        except Exception as e:  # noqa: BLE001 - a cleanup call must not throw
            return {"ok": False, "stale": True, "error": repr(e)}
        finally:
            self._token = None

    def heartbeat(
        self, token: str | None = None, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Refresh the dead-man. Uses the stored token when ``token`` is
        omitted (via :meth:`require_token`, so a script holding no token gets
        an immediate, clear ``RuntimeError`` rather than a wire round trip).

        ``timeout``, when given, overrides :meth:`timeout_for`'s
        bound-derived default for this one call -- what :class:`Heartbeat`
        uses to give its beats a generous, latency-tolerant timeout instead of
        the tight one an interactive command gets. ``None`` (the default)
        keeps the normal :meth:`_command_call` behaviour.

        Raises :class:`ControlRevoked` (-32011) if the token was ours and is
        not any more -- a human took the instrument, or the dead-man expired
        it. **Do not blindly re-acquire** on that exception.
        """
        tok = token if token is not None else self.require_token()
        return self._command_call("heartbeat", {"token": tok}, timeout=timeout)

    def abort(self, scope: str | None = None) -> dict[str, Any]:
        """**Token-free** emergency stop: cooperative stop of whatever is in
        flight plus a verified retract, through the same ``safe_park`` the
        cockpit's Abort button fires -- never the non-retracting COM
        ``AFM_Abort``. ``scope`` is recorded in the park reason; there is
        only one stop, and it stops everything."""
        params = {}
        if scope is not None:
            params["scope"] = scope
        return self._command_call("abort", params)

    def safe_park(self, reason: str = "script") -> dict[str, Any]:
        """**Token-free** verified retract -- the same route as :meth:`abort`,
        for when the intent is "get the tip somewhere safe" rather than "stop
        what I started"."""
        return self._command_call("safePark", {"reason": reason})

    def heartbeat_context(self, period: float | None = None) -> Heartbeat:
        """A :class:`Heartbeat` sized to this instrument's dead-man.

        **Requires a held token** (:meth:`require_token`) -- this method
        exists to refresh control while a blocking call runs, and without a
        token there is no dead-man to refresh: a ``Heartbeat`` built here
        with no token would silently fall back to beating ``get_state()``,
        refreshing nothing, while a script believes it holds the instrument
        and the dead-man it never acquired runs down. Call
        :meth:`acquire_control` first.

        ``period`` defaults to ``deadman_s / 3`` (two missed beats of slack)
        from the last :meth:`acquire_control`, and its beat is
        ``self.heartbeat(timeout=...)`` -- a generous, latency-tolerant
        per-beat timeout (:data:`HEARTBEAT_TIMEOUT_S`, clamped to at most
        ``period / 2``), retried after :data:`HEARTBEAT_RETRY_S` rather than
        a full ``period`` on a miss; see :class:`Heartbeat` for the full
        timeout/retry/death contract. Wrap any blocking third-party call while
        holding control::

            afm.acquire_control("flex-exp", deadman_s=60)
            try:
                with afm.heartbeat_context():
                    lockin.lockin_sweep(config, timeout=120)
            finally:
                afm.release_control()
        """
        self.require_token()
        if period is None:
            period = (self._deadman_s or 30.0) / 3
        return Heartbeat(self, period=period)

    # -- scan control (command socket unless noted) --------------------------
    #
    # The first verbs that can drive the tip TOWARD a surface (plan Sec I
    # stage 3, Asana 07). Every one requires a held token except `withdraw`,
    # and every one refreshes the dead-man when it carries a valid token --
    # command socket only (see "Token refresh happens only via the command
    # socket" above). `getMode` is the one read-only member of this family: a
    # pure memory read with no bridge I/O, served by the read socket like
    # every other get*.
    #
    # Write control is wired below, in its own section. `startMeasure` and
    # `executePass` are still `RESERVED_VERBS` -- named by the provider,
    # answering -32601 "not implemented in this build". Do not wire one here
    # without the matching guard on the provider side.

    def get_mode(self) -> dict[str, Any]:
        """``{mode, engaged, gate, backend}`` -- the instrument's imaging mode
        plus the live engage/scan gate, from memory. Served by the **read**
        socket: unlike every other verb in this family it issues no bridge
        I/O, so a script deciding whether :meth:`set_mode` would even be
        accepted should not have to queue behind a blocking command. ``mode``
        is ``None`` until first established (a :meth:`set_mode` call, or a
        hardware approach)."""
        return self._read_call("getMode")

    def read_deflection(self) -> dict[str, Any]:
        """``{defl_v, tip_state, mode, fresh}`` -- a FRESH cantilever deflection
        read, **token-free and read-only**, on the **command** socket.

        Not a telemetry field and not the read socket, deliberately. The
        deflection this returns is the free-air baseline a *relative* engage is
        resolved against (:meth:`start_approach`'s ``setpoint_relative_v``), so
        it must be read from the instrument at the moment it is asked for, not
        served from the cached telemetry frame :meth:`get_telemetry` answers
        with -- a frame that can be a poll period old, taken before the tip was
        withdrawn, or (with the bridge down) stale in a way nothing in it
        announces. Hence the command socket, where the bridge I/O serialises
        with everything else that touches the instrument, and hence ``fresh:
        true`` in the reply: it is an assertion about THIS read.

        Token-free like :meth:`withdraw` / :meth:`abort` -- it moves nothing and
        arms nothing, so making an operator's own session the precondition for
        reading a voltage would buy nothing.

        The reply is ``{defl_v, tip_state, mode, fresh, backend}``.
        ``tip_state`` is one of ``withdrawn`` / ``parked`` /
        :data:`TIP_NOT_WITHDRAWN_STATES`; anything in that last set --
        ``approaching`` included -- means this deflection is NOT a free-air
        baseline, and a relative engage resolved against it would be wrong."""
        return self._command_call("readDeflection", {})

    def set_mode(self, mode: str) -> dict[str, Any]:
        """Contact <-> AC. **Refused** (:class:`Refused`, -32021) while the
        tip is engaged, scanning or writing -- the vendor switch changes the
        Z feedback channel and the gain sign and does **not** withdraw, so
        doing it with the tip down is a crash. Call :meth:`withdraw` first.
        The bound is real -- a vendor mode-profile popup plus a readback, the
        slowest verb on the wire -- and :meth:`timeout_for` picks it up from
        the live ``method_bounds`` rather than a number copied out of a doc."""
        token = self.require_token()
        return self._command_call("setMode", {"token": token, "mode": mode})

    def start_approach(
        self,
        *,
        setpoint: float | None = None,
        setpoint_relative_v: float | None = None,
        pgain: float | None = None,
        igain: float | None = None,
        settle_s: float | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """START+POLL fine engage: ``{run_id, est_s, state}``. ``get_state()``
        reads ``approaching`` from the moment this returns until the run
        record closes, then ``engaged`` -- or ``parked``, because a failed
        engage fires ``safe_park`` server-side. Only the keywords actually
        given are sent, so the provider's own defaults apply to the rest.
        Prefer :meth:`approach` for a blocking call that already polls and
        keeps the dead-man alive.

        ``setpoint_relative_v`` is the **relative** engage: an offset ABOVE the
        free-air deflection rather than an absolute setpoint voltage. The
        provider requires the tip withdrawn and contact mode, reads Deflection
        fresh itself (the same read :meth:`read_deflection` serves), and
        resolves ``setpoint = free_air_v + setpoint_relative_v``; its reply
        reports all three (``free_air_v``, ``setpoint_relative_v``,
        ``setpoint``) so a script can record what it actually engaged at. It is
        **mutually exclusive with** ``setpoint`` -- passing both is a
        client-side ``ValueError`` before anything is sent, because the
        provider would only refuse it (-32021) after a round trip -- and must
        be ``> 0`` and ``<= SETPOINT_RELATIVE_MAX_V``, checked here for the
        same reason.

        The provider refuses in a fixed order, and every refusal carries a
        ``.reason`` worth surfacing rather than swallowing. ``-32602``:
        ``bad_params`` (both setpoints) and ``offset_out_of_range`` (the same
        ``0 < offset <= SETPOINT_RELATIVE_MAX_V`` bound checked above, so this
        one should never come back). ``-32010``: no live bridge. ``-32021``
        :class:`Refused`: ``engaged`` (the tip is down -- ``tip_state``
        ``approaching`` counts), ``mode`` (not contact), ``tip_not_parked``
        (**the last retract was not verified** -- the withdraw's own, or a
        litho run's end-of-run one -- or Z is not at the park value, 0 V on
        hardware and -10 V on the twin), ``free_air_jump`` (the fresh read
        differs from the last ACCEPTED baseline by more than the guard's jump
        fraction; ``data`` carries ``last_free_air_v`` and ``value_v``),
        ``sum_lost`` / ``sum_read_failed``, ``free_air_unstable`` /
        ``read_failed`` (the repeated-read stability guard), and
        ``setpoint_over_sum`` (the resolved setpoint is over the detector-SUM
        clamp; ``data`` carries ``sum_v``, ``clamp_v`` and ``value_v``).

        ``tip_not_parked`` and ``free_air_jump`` are
        :data:`HARD_STOP_REFUSALS`: both mean the tip is not where the
        baseline assumed, so retrying engages on the same bad premise one
        attempt later. A caller should :meth:`withdraw` explicitly and check
        that reply's ``verified`` before coming here.

        The reply's ``baseline_check`` says which of those happened:
        ``"ok"`` when the fresh read agreed with the last accepted baseline,
        ``"none"`` when there was no baseline to compare against (the first
        relative approach after a service start).

        The settle plus five repeated reads is why this verb's bound is ~9.5 s
        rather than milliseconds; :meth:`timeout_for` takes it from the live
        ``method_bounds`` and this driver never hard-codes it.

        **Hard stop if the provider doesn't actually resolve the relative
        engage.** When ``setpoint_relative_v=`` is sent, the reply MUST echo
        :data:`APPROACH_RELATIVE_REQUIRED_KEYS` (``free_air_v``, ``setpoint``,
        ``setpoint_relative_v``) -- a provider that doesn't implement this verb
        has no reason to send them, since it just ignores the unknown param
        rather than refusing it. If any are missing, this immediately
        :meth:`withdraw`\\ s (bounded, token-free -- the approach may already
        be descending against a setpoint nobody resolved) and raises
        :class:`ProviderLacksCapability`: the tip would otherwise engage at
        whatever the provider defaults to (an absolute setpoint, typically
        1.0 V) while the caller believes it engaged at free-air plus the
        requested offset."""
        if setpoint is not None and setpoint_relative_v is not None:
            raise ValueError(
                f"{self.name}: start_approach takes setpoint= OR "
                f"setpoint_relative_v=, not both -- an absolute setpoint and an "
                f"offset above free air are two different engages"
            )
        if setpoint_relative_v is not None:
            offset = _finite(setpoint_relative_v, "setpoint_relative_v")
            if not 0 < offset <= SETPOINT_RELATIVE_MAX_V:
                raise ValueError(
                    f"{self.name}: setpoint_relative_v must be > 0 and <= "
                    f"{SETPOINT_RELATIVE_MAX_V} V (the offset ABOVE free air that "
                    f"becomes the engage force), got {setpoint_relative_v!r}"
                )
        token = self.require_token()
        params: dict[str, Any] = {"token": token}
        if setpoint is not None:
            params["setpoint"] = float(setpoint)
        if setpoint_relative_v is not None:
            params["setpoint_relative_v"] = float(setpoint_relative_v)
        if pgain is not None:
            params["pgain"] = float(pgain)
        if igain is not None:
            params["igain"] = float(igain)
        if settle_s is not None:
            params["settle_s"] = float(settle_s)
        if mode is not None:
            params["mode"] = mode
        result = self._command_call("startApproach", params)
        if setpoint_relative_v is not None:
            missing = [key for key in APPROACH_RELATIVE_REQUIRED_KEYS if key not in result]
            if missing:
                self.withdraw()
                raise ProviderLacksCapability(
                    f"{self.name}: startApproach(setpoint_relative_v={setpoint_relative_v!r}) "
                    f"reply is missing {missing} -- this provider does not implement "
                    f"relative setpoints; use setpoint= or run a provider that does"
                )
        return result

    def withdraw(self) -> dict[str, Any]:
        """Blocking retract, from any state. **Deliberately the least gated
        verb on the wire**: the token is sent when this instance holds one
        and omitted otherwise, and there is no backend gate -- the same
        reason :meth:`abort` and :meth:`safe_park` are token-free, because
        getting the tip OFF the surface must never wait on bookkeeping.
        Still command-socket only: the read socket cannot move the tip at
        all. Bound ~6.5 s (``method_bounds["withdraw"]``); unlike
        :meth:`approach` / :meth:`scan` this call is **not** wrapped in
        :meth:`heartbeat_context` -- it already blocks for its own bounded
        duration and there is nothing left to poll once it returns."""
        params: dict[str, Any] = {"token": self._token} if self._token is not None else {}
        return self._command_call("withdraw", params)

    def set_zgain(self, pgain: float, igain: float) -> dict[str, Any]:
        """Re-arm the running Z loop with new P/I gains, without withdrawing.
        **Hardware only** -- the twin has no servo to re-arm and answers
        :class:`BackendMismatch` (-32010) rather than reporting a tune it
        never made."""
        token = self.require_token()
        return self._command_call(
            "setZGain", {"token": token, "pgain": float(pgain), "igain": float(igain)}
        )

    #: Keys `start_scan` requires -- a missing one is a client-side
    #: ``ValueError``, not a round trip to the provider to find out.
    _SCAN_REQUIRED: tuple[str, ...] = (
        "size_um", "pixels", "lines", "line_rate_hz", "x_offset_um", "y_offset_um",
    )
    #: Keys `start_scan` accepts beyond the required set, sent only if given.
    #: `engage` / `setpoint` matter most: on hardware a `setpoint` sent
    #: without `engage: true` is rejected server-side (-32602) rather than
    #: silently run at the current engagement force.
    _SCAN_OPTIONAL: tuple[str, ...] = (
        "angle_deg", "direction", "trace_retrace", "mode", "setpoint", "engage", "chained",
    )

    def start_scan(self, **params: Any) -> dict[str, Any]:
        """START+POLL raster: ``{run_id, est_s, state, backend, config}``.
        Poll ``get_state()``, then :meth:`get_scan_result` (``run_id``) --
        gated on persistence, so the paths in ``files`` are whole once it
        answers. Required keys (:data:`_SCAN_REQUIRED`) are checked
        client-side before anything is sent; everything else
        (:data:`_SCAN_OPTIONAL`) is passed through only when given -- an
        unrecognised keyword is a client-side ``ValueError`` rather than a
        silent typo on the wire. Prefer :meth:`scan` for a blocking call that
        already polls and fetches the result."""
        token = self.require_token()
        missing = [k for k in self._SCAN_REQUIRED if k not in params]
        if missing:
            raise ValueError(
                f"{self.name}: start_scan missing required parameter(s): "
                f"{', '.join(missing)}"
            )
        allowed = set(self._SCAN_REQUIRED) | set(self._SCAN_OPTIONAL)
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise ValueError(
                f"{self.name}: start_scan got unknown parameter(s): {', '.join(unknown)}"
            )
        return self._command_call("startScan", {"token": token, **params})

    #: Keys `set_continuous` accepts beyond `enabled`.
    _CONTINUOUS_OPTIONAL: tuple[str, ...] = (
        "config", "max_frames", "max_seconds", "interval_s", "withdraw_on_stop", "rail",
    )

    def set_continuous(self, enabled: bool, **opts: Any) -> dict[str, Any]:
        """Arm or stop the auto-repeat imaging loop. ``enabled`` is always
        sent as a real JSON bool -- the provider treats a truthy string as a
        typo, since this flag governs an unattended run. ``rail`` may only
        *tighten* the rail-dwell guard: a looser value is floored to the
        armed one, silently and by construction, never refused. Disabling is
        never refused for backend reasons -- a dead bridge is exactly when
        someone wants the loop stopped."""
        token = self.require_token()
        unknown = sorted(set(opts) - set(self._CONTINUOUS_OPTIONAL))
        if unknown:
            raise ValueError(
                f"{self.name}: set_continuous got unknown parameter(s): {', '.join(unknown)}"
            )
        return self._command_call(
            "setContinuous", {"token": token, "enabled": bool(enabled), **opts}
        )

    # -- write control (command socket unless noted) --------------------------
    #
    # The first verb that puts VOLTAGE on a tip already on the surface (plan
    # Sec I stage 4, Asana 09). `loadPattern` arms nothing -- no claim, no
    # thread, no run record, `get_state()` does not move -- it only compiles
    # and validates, replacing `hub.pattern` for the next `startWrite`.
    # `startWrite` requires a held token like every other start verb;
    # `abortWrite` is **token-free**, like `abort` / `safePark` and for the
    # same reason -- an emergency stop must never be blocked by arbitration.
    # All three refresh the dead-man when they carry a valid token, command
    # socket only, same as the rest of this family.

    def load_pattern(
        self, source: str | None = None, *, objects: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Compile and validate a design. **Arms nothing** -- no claim, no
        thread, no run record, and ``get_state()`` does not move; it only
        replaces ``hub.pattern``, the state the next :meth:`start_write` acts
        on. The compile *is* the validation: a design that cannot be compiled
        is refused here, tip untouched, rather than at the first ARMFIRE.

        ``source`` is one of a design name inside the provider's
        ``data/designs``, a **file path on the instrument PC** (the wire
        door's own capability -- a script never has to copy its design into
        the service's tree first), or an inline SVG/GDS/OASIS document as
        text. Inline SVG is read on the same terms as the cockpit's own
        import: **1 unit = 1 nm, always**; closed outlines become filled
        shapes, open paths become wires; a design whose bounding box exceeds
        2000 um is refused before the flatten.

        The reply's ``objects`` is a **list**, one entry per object in
        compile order (``{index, name, id, kind, vertices_um, points,
        segments, strokes, profile?, properties}``) -- ``object_count``
        carries the plain count. ``id`` is the stable identifier
        :meth:`set_objects` and :meth:`start_write` address an object by
        (a name-derived string, not the positional ``index``, which shifts
        if the pattern is ever reloaded); ``properties`` is the object's
        current ``{voltage, speed_um_s, enabled, chiral, fill}`` block --
        ``chiral`` non-null only for a chiral wire, ``fill`` non-null only
        for a filled region -- the same shape :meth:`set_objects` merges
        into and :meth:`get_pattern` / :meth:`get_written` also report.

        **No size refusal, and no lift inside a stroke: a big object simply
        CHAINS at the DSP's out-wave cap, never refused and never split at
        8,192 points the way it used to be** (Joe's decisions, 2026-09-11;
        ``max_segment_points`` is GONE from this wire). The reply carries:

        - ``strokes`` -- **continuous tip paths**: one stroke is one transit,
          one ``litho_object_done`` and one :meth:`get_written` entry. More
          than one only for a filled shape that expands into several
          disconnected regions; a wire is one stroke however long.
        - ``segments`` -- **the true out-wave count**: one arm per stroke,
          plus one more per chain chunk where a stroke is over
          ``max_outwave_points``, per object in ``objects[i]["segments"]``
          and summed at the top level. There is deliberately no ``chunks``
          key -- that counted ``ceil(points / 87,380)``, a number nothing
          ever arms.
        - ``multi_segment_objects`` -- ``[{name, points, segments, strokes,
          chain_boundaries, max_outwave_points}]`` for each object **that
          chains**; empty for a normal design.
        - ``max_outwave_points`` (**87,000**, not the older 87,380) -- the
          DSP's per-out-wave cap, advisory so a script does not have to
          hard-code it.

        The two kinds of seam are different in kind: between two *strokes*
        the tip lifts, the bias goes to 0, and it costs a lift + move +
        set-down (``strokes`` > 1); at a *chain boundary* the tip **stays
        down** and the bias **stays live**, and it costs Igor re-binding
        banks for a dwell (``multi_segment_objects``, ``segments`` >
        ``strokes``). An object in ``multi_segment_objects`` is also named in
        a WARNING log line on the provider side -- not because the seam
        lifts, but because the chain path has never fired on the instrument
        -- see ``docs/FLEX_PROVIDER.md`` ("Write control") in the afm-litho
        repo. What still refuses a load: a design that cannot be read,
        cannot be compiled, has no drawable geometry, or spans more than
        2000 um -- the provider leaves whatever was previously loaded in
        place on any such refusal, so a half-replaced pattern never becomes
        the next :meth:`start_write`'s target.

        ``objects`` is the INLINE alternative to ``source``: a list of object
        specs built right here rather than a document to import -- a
        :func:`chiral_spec` wire, a :func:`rect_spec` region, or a hand-built
        dict of the same shape. **Mutually exclusive with** ``source``
        (exactly one, or a client-side ``ValueError``), and every entry goes
        through :func:`validate_object_spec` before anything is sent: an
        invalid spec is a ``ValueError`` in the caller's frame, and if one
        reaches the provider anyway it is ``-32602`` with the **previously
        loaded pattern left in place**. The reply has the same shape as a
        ``source`` load plus a per-object ``kind``, and for a chiral object a
        ``profile`` block (``lambda_um``, ``y_amp_um``, ``v0``, ``v_k``,
        ``phase_deg``, ``hand``, ``curvature_clamped``,
        ``y_amp_built_um`` and ``curvature_clamped_fraction``) -- the last
        three being the provider's own authoritative say on geometry it had to
        soften: WHETHER it clamped, the amplitude it actually built, and HOW
        MUCH of the path was clamped. Read off the reply, never assumed. Any
        object entry may also carry ``speed_achieved_um_s`` when the tick clock
        floored the speed that was asked for -- the wire was still written, but
        slower than requested, and a dose-per-length conclusion drawn from the
        requested number would be wrong.

        Refusals: ``-32602`` for an invalid spec, a region whose ``pitch_um``
        is over half its shorter side (an erase that would not erase --
        :func:`rect_spec` catches that one first), an extent over 2000 um, or
        more than 2,000,000 points in one object / 4,000,000 in the pattern --
        all before anything is rendered. A build or compile that outruns the
        verb's own bound is ``-32021`` :class:`Refused` with ``.reason`` of
        ``build_timeout`` / ``compile_timeout``. **Every one of them leaves
        the previously loaded pattern in place**, so a refused load never
        becomes a half-replaced target for the next write."""
        if (source is None) == (objects is None):
            raise ValueError(
                f"{self.name}: load_pattern takes exactly one of source= "
                f"(a design name, an instrument-PC path, or inline SVG/GDS/OASIS "
                f"text) or objects= (a list of inline object specs)"
            )
        token = self.require_token()
        if objects is not None:
            if isinstance(objects, (str, bytes, dict)) or not isinstance(objects, (list, tuple)):
                raise ValueError(
                    f"{self.name}: load_pattern objects= must be a list of object "
                    f"specs, got {type(objects).__name__}"
                )
            if not objects:
                raise ValueError(
                    f"{self.name}: load_pattern objects= is empty -- a pattern with "
                    f"no drawable geometry is a refusal on the provider too"
                )
            params: dict[str, Any] = {
                "token": token,
                "objects": [validate_object_spec(spec) for spec in objects],
            }
        else:
            params = {"token": token, "source": source}
        try:
            return self._command_call("loadPattern", params)
        except ZMQInstrumentError as e:
            data = e.data if isinstance(e.data, dict) else {}
            if e.code == INVALID_PARAMS and data.get("objects_over_cap") is not None:
                raise PatternTooLarge(str(e), code=e.code, data=e.data) from e
            raise

    def load_sample(self, file_name: str, *, fresh: bool = True) -> dict[str, Any]:
        """Load a sample scan file (e.g. 'SA40656B0000.ibw') into the twin."""
        token = self.require_token()
        try:
            return self._command_call(
                "loadSample",
                {"token": token, "file": file_name, "fresh": bool(fresh)},
                timeout=10.0,
            )
        except ZMQInstrumentError as e:
            if "method not found" in str(e).lower():
                import json
                import urllib.request
                req = urllib.request.Request(
                    "http://localhost:7461/api/sample/load",
                    data=json.dumps(
                        {"file": file_name, "fresh": bool(fresh)}
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    def set_objects(self, updates: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Merge property changes into an ALREADY-loaded pattern, by id --
        :meth:`load_pattern` compiles geometry; this changes what gets
        applied to it (``voltage``, ``speed_um_s``, ``enabled``, and the
        per-kind ``chiral`` / ``fill`` knobs) without recompiling, so a
        sweep can retune an object between writes rather than reloading the
        whole design each time. Requires a held token, like
        :meth:`load_pattern`.

        ``updates`` is ``{id: {field: value, ...}, ...}`` with **merge**
        semantics: only the fields named for each object change, everything
        else already on it is left alone -- a bare ``{"voltage": 8}`` never
        touches that object's ``chiral`` or ``fill`` block. Validated here
        only for shape (a non-empty ``dict`` of ``str`` id -> ``dict`` of
        field -> value); every id and field name is the provider's call to
        validate, not this driver's -- an unknown id or an unknown/invalid
        field is ``-32602`` naming ``data["id"]`` / ``data["field"]`` and
        refuses the **whole call**, leaving the pattern exactly as it was
        rather than a partial merge. A write in flight answers :class:`Busy`
        (-32020): a pattern currently being fired is not a safe time to
        change what it will apply.

        Returns the same object listing :meth:`load_pattern` /
        :meth:`get_pattern` report, with the merged properties reflected."""
        if not isinstance(updates, dict) or not updates:
            raise ValueError(
                f"{self.name}: set_objects updates= must be a non-empty dict of "
                f"id -> {{field: value}}, got {updates!r}"
            )
        for obj_id, fields in updates.items():
            if not isinstance(obj_id, str):
                raise ValueError(
                    f"{self.name}: set_objects updates= keys must be object ids "
                    f"(str), got {obj_id!r}"
                )
            if not isinstance(fields, dict):
                raise ValueError(
                    f"{self.name}: set_objects updates[{obj_id!r}] must be a dict "
                    f"of field -> value, got {type(fields).__name__}"
                )
        token = self.require_token()
        return self._command_call("setObjects", {"token": token, "updates": updates})

    def start_write(
        self,
        objects: str | list[int | str] = "all",
        *,
        setpoint: float | None = None,
        amp_gain: float | None = None,
        deadman_s: float | None = None,
    ) -> dict[str, Any]:
        """START+POLL lithography, sub-second by construction:
        ``{run_id, est_s, objects, segments, state, backend}``. Poll
        ``get_state()`` until it leaves ``writing``, then fetch
        :meth:`get_write_result`. Prefer :meth:`write` for a blocking call
        that already does both.

        ``objects`` is ``"all"`` (the default -- clears the per-session
        written set and writes every enabled object) or a list of integer
        indices *or* string **ids** (:meth:`load_pattern`'s ``id`` field,
        also what :meth:`set_objects` addresses) into the loaded design,
        written whether or not they have been written before -- the two
        address the same objects and may be mixed in one call. **No pattern
        loaded is a refusal, not a demo**
        (:class:`Refused`, ``.reason == "no_pattern"``) -- unlike the
        cockpit, the wire door never substitutes a demo design.

        ``setpoint`` is the litho tip-down deflection setpoint; ``amp_gain``
        is the external tip-bias amplifier gain (the DAC drives
        ``V_tip / amp_gain``). Both are hardware parameters, inert on the
        twin, but validated on both backends -- a typo is ``-32602`` rather
        than a surprise on the day it matters. ``deadman_s`` re-arms the
        commander's dead-man for the length of the write (clamped to
        ``[5, 300]``, same rule as :meth:`acquire_control`) -- it does not
        make a long write safe **on its own**; heartbeat anyway (see the
        write-control section of ``docs/FLEX_PROVIDER.md`` and
        :meth:`heartbeat_context`).

        ``segments`` is how many out-waves this write actually arms -- one
        ARMFIRE per stroke, plus one per chain chunk -- summed over the
        selected objects, so a script knows before it polls how many arms
        the write contains (see :meth:`load_pattern`). ``est_s`` folds in a
        per-STROKE transit allowance for disconnected strokes and a separate,
        smaller per-CHAIN-BOUNDARY dwell allowance for a chaining object, on
        top of the per-object estimate measured at :meth:`load_pattern` time
        -- a one-stroke object pays neither, however long it is -- treat
        ``est_s`` as a sleep hint, not a schedule."""
        token = self.require_token()
        params: dict[str, Any] = {"token": token, "objects": objects}
        if setpoint is not None:
            params["setpoint"] = float(setpoint)
        if amp_gain is not None:
            params["amp_gain"] = float(amp_gain)
        if deadman_s is not None:
            params["deadman_s"] = float(deadman_s)
        return self._command_call("startWrite", params)

    def abort_write(self) -> dict[str, Any]:
        """**Token-free** stop of a write plus a verified retract, through
        the same ``safe_park`` :meth:`abort` / :meth:`safe_park` use -- the
        tip comes OFF the surface, not merely stopped with a live Z loop.
        **The partial result survives**: :meth:`get_write_result` still
        returns ``aborted: true`` with whatever files the pass produced, and
        :meth:`get_written` lists only the objects that actually completed --
        never the one the abort cut through. That is what lets a script
        resume instead of re-dosing geometry it already wrote.

        The token is sent when this instance holds one (refreshing the
        dead-man like any other command-socket call) and omitted otherwise --
        the provider never requires it, for the same reason :meth:`abort` and
        :meth:`safe_park` do not."""
        params: dict[str, Any] = {"token": self._token} if self._token is not None else {}
        return self._command_call("abortWrite", params)

    # -- scan control: blocking convenience helpers ---------------------------
    #
    # The lockin_sweep idiom (README "Running scans from a script"): refuse
    # up front if the instrument is busy (a start verb's own Busy propagates
    # untouched -- nothing of ours started, so there is nothing to abort);
    # otherwise sleep a CAPPED estimate before the first poll, poll
    # get_state() on the READ socket every `poll` seconds until it leaves the
    # busy state, raise TimeoutError past `timeout`, and on any OTHER
    # BaseException while polling -- a timeout, Ctrl-C, anything where this
    # script still holds the token -- call abort() before re-raising. The
    # whole poll runs inside heartbeat_context() so a run longer than a third
    # of deadman_s does not park itself out from under the caller: get_state()
    # never refreshes the dead-man (it is a read-socket call), so without this
    # a long scan under a short dead-man would be parked mid-run by the very
    # watchdog these helpers are trying to outlast.
    #
    # -32011 control_revoked is NOT one of those "anything" cases and must
    # never reach the abort() branch: it means a human is now at the panel, or
    # the dead-man already parked server-side -- the script owns NOTHING here,
    # and abort() would be a token-free verified retract fired at a run a
    # human may be actively driving. It can arrive two ways: the poll loop
    # notices heartbeat.died directly (the common case, within ~one poll
    # period), or -- if the busy state happened to clear in the very same
    # instant -- Heartbeat.__exit__ raises its own wrapping RuntimeError after
    # a poll that returned normally. `_as_control_revoked` unwraps either
    # shape, so both are handled the same way: re-raised untouched, never
    # aborted.

    def _poll_until_state_leaves(
        self,
        busy_state: str,
        *,
        poll: float,
        timeout: float,
        verb: str,
        heartbeat: Heartbeat | None = None,
    ) -> str:
        """Poll :meth:`get_state` (read socket) until it is no longer
        ``busy_state``. Raises ``TimeoutError`` once ``timeout`` seconds have
        elapsed with the busy state still current, or the held token's
        :class:`ControlRevoked` the moment ``heartbeat`` notices it died --
        checked once per iteration, so at most one `poll` period late."""
        deadline = time.monotonic() + timeout
        state = self.get_state()
        while state == busy_state:
            if (
                heartbeat is not None
                and heartbeat.died
                and isinstance(heartbeat.last_error, ControlRevoked)
            ):
                raise heartbeat.last_error
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"{self.name}: {verb} still {busy_state!r} after {timeout:g}s"
                )
            time.sleep(poll)
            state = self.get_state()
        return state

    @staticmethod
    def _as_control_revoked(
        exc: BaseException, heartbeat: Heartbeat | None
    ) -> ControlRevoked | None:
        """Unwrap a revoked dead-man from either shape it can arrive in:
        raised directly by :meth:`_poll_until_state_leaves` (it noticed
        ``heartbeat.died`` first), or wrapped as the ``RuntimeError``
        :meth:`Heartbeat.__exit__` raises when the poll happened to leave the
        busy state in the very same instant control was revoked. ``None``
        when ``exc`` is neither."""
        if isinstance(exc, ControlRevoked):
            return exc
        if (
            heartbeat is not None
            and heartbeat.died
            and isinstance(heartbeat.last_error, ControlRevoked)
        ):
            return heartbeat.last_error
        return None

    def _run_polled(
        self,
        *,
        start_result: dict[str, Any],
        busy_state: str,
        poll: float,
        timeout: float,
        verb: str,
        on_abort: Callable[[], Any] | None = None,
        settle: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Shared polling body for :meth:`approach` / :meth:`scan` /
        :meth:`write`: sleep the capped estimate, poll inside
        :meth:`heartbeat_context`, and route the three ways the wait can end
        early -- a clean finish, a revoked token (re-raised untouched, see
        the section comment above), or anything else (timeout, Ctrl-C, a
        transient error -- ``on_abort()`` first, then re-raise the ORIGINAL
        exception even if that cleanup call itself fails).

        ``on_abort`` defaults to ``self.abort(scope=verb)`` (:meth:`approach`
        / :meth:`scan`); :meth:`write` passes :meth:`abort_write` instead, so
        a timeout or Ctrl-C mid-write gets the write-specific verified
        retract with a surviving partial result rather than the general
        :meth:`abort`.

        ``settle``, when given, is called **inside the same
        ``heartbeat_context()``**, immediately after the busy-state poll
        leaves -- :meth:`scan` / :meth:`write` pass their own
        ``_await_terminal_result`` fetch here rather than calling it after
        this method returns. That is not cosmetic: ``_await_terminal_result``
        is itself a bounded poll loop (:data:`SETTLE_CAP_S`), and running it
        after the ``with`` block had already exited left it -- and the
        provider round trips it makes -- completely unheartbeated, a gap a
        slow provider pump could stretch past a short ``deadman_s`` with the
        tip still on the surface. Its return value is returned by this
        method; ``None`` when no ``settle`` is given (:meth:`approach`'s
        shape, which has no terminal record to settle). A ``settle()``
        failure (most notably :meth:`_await_terminal_result`'s own "never
        settled" ``RuntimeError``) is routed through the exact same
        revoked-vs-cleanup handling as a busy-poll failure below."""
        hb: Heartbeat | None = None
        cleanup = on_abort or (lambda: self.abort(scope=verb))
        try:
            with self.heartbeat_context() as hb:
                time.sleep(min(float(start_result.get("est_s") or 0.0), PRE_POLL_SLEEP_CAP))
                self._poll_until_state_leaves(
                    busy_state, poll=poll, timeout=timeout, verb=verb, heartbeat=hb
                )
                if settle is not None:
                    return settle()
        except BaseException as exc:
            revoked = self._as_control_revoked(exc, hb)
            if revoked is not None:
                raise revoked from None
            try:
                cleanup()
            except BaseException as abort_exc:  # noqa: BLE001 - never mask the ORIGINAL
                self.log.error(
                    "%s cleanup: abort() failed (%s) -- the original exception still "
                    "propagates", verb, abort_exc,
                )
            raise
        return None

    def _await_terminal_result(
        self, fetch: Callable[[], dict[str, Any]], *, run_id: str | None, verb: str,
    ) -> dict[str, Any]:
        """Poll ``fetch`` (a bound ``get_scan_result`` / ``get_write_result``
        call) until the record it returns is settled -- ``completed`` or
        ``aborted`` -- tolerating the provider's own pump lagging a tick
        behind ``get_state()`` already having left the busy state (a
        ``getState`` read can observe the run's thread already dead a moment
        before the pump's own persistence/close step has actually run, which
        briefly reads back ``completed: false, aborted: false`` for a run
        that is, in fact, either still finishing or already done).

        Raises ``RuntimeError`` naming ``run_id`` and the last record's
        ``completed`` / ``aborted`` / ``error`` fields if the record never
        settles within :data:`SETTLE_CAP_S` -- a caller must never read a
        bare ``{completed: false, aborted: false}`` silently as a finished
        run just because :meth:`_poll_until_state_leaves` returned."""
        deadline = time.monotonic() + SETTLE_CAP_S
        result = fetch()
        while not result.get("completed") and not result.get("aborted"):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"{self.name}: {verb} {run_id!r} result never settled (neither "
                    f"completed nor aborted) within {SETTLE_CAP_S:g}s of leaving the "
                    f"busy state -- last record: completed={result.get('completed')!r}, "
                    f"aborted={result.get('aborted')!r}, error={result.get('error')!r}"
                )
            time.sleep(SETTLE_POLL_S)
            result = fetch()
        return result

    def approach(
        self, *, timeout: float = 60.0, poll: float = 0.5, **params: Any
    ) -> dict[str, Any]:
        """Blocking convenience: :meth:`start_approach` then poll to a
        terminal state, returning the final :meth:`get_status`.

        Requires a held token -- raised as a plain ``RuntimeError`` *before*
        anything is sent (:meth:`require_token`). Raises ``RuntimeError`` if
        the run ends in ``parked`` or ``fault``: a failed engage fires
        ``safe_park`` server-side, and this turns that into an exception a
        script can catch instead of a status string it has to remember to
        check. Raises :class:`ControlRevoked` untouched -- never ``abort()``
        -- if control was preempted or the dead-man expired mid-poll; see the
        section comment above.

        The returned status carries :data:`APPROACH_RESOLUTION_KEYS`
        (``free_air_v``, ``setpoint_relative_v``, ``setpoint``) copied from the
        ``startApproach`` reply whenever the provider sent them -- a RELATIVE
        engage (``setpoint_relative_v=``) resolves its absolute setpoint
        server-side, and that resolution is reported on the start reply alone.
        There is no ``getApproachResult`` to fetch it from afterwards, and
        polling to a terminal state must not be the thing that loses it. Keys
        the provider did not send are simply absent.

        Inherits :meth:`start_approach`'s hard stop on
        ``setpoint_relative_v=``: if the provider's reply doesn't echo
        :data:`APPROACH_RELATIVE_REQUIRED_KEYS`, :meth:`start_approach` itself
        withdraws and raises :class:`ProviderLacksCapability` before this
        method ever starts polling.
        """
        self.require_token()
        result = self.start_approach(**params)
        run_id = result.get("run_id")
        self._run_polled(
            start_result=result, busy_state="approaching", poll=poll, timeout=timeout,
            verb="approach",
        )
        status = self.get_status()
        for key in APPROACH_RESOLUTION_KEYS:
            if key in result:
                status[key] = result[key]
        if status.get("state") in ("parked", "fault"):
            raise RuntimeError(
                f"{self.name}: approach {run_id!r} ended in {status['state']!r} "
                f"-- see get_status() for detail"
            )
        return status

    def scan(
        self, *, timeout: float = 1800.0, poll: float = 1.0, inline: bool = False, **params: Any
    ) -> dict[str, Any]:
        """Blocking convenience: :meth:`start_scan` then poll to a terminal
        state, returning :meth:`get_scan_result`.

        Requires a held token, raised *before* anything is sent. Follows the
        same busy-refusal / heartbeat / abort-on-exception shape as
        :meth:`approach`, including raising :class:`ControlRevoked` untouched
        rather than aborting. Once ``get_state()`` leaves ``scanning``,
        :meth:`_await_terminal_result` polls ``get_scan_result`` until it
        settles (bounded, :data:`SETTLE_CAP_S`) rather than trusting the
        first fetch -- the provider's pump can briefly lag a tick behind
        thread death. Raises ``RuntimeError`` when the finished run reports
        ``aborted: true`` -- ``docs/FLEX_PROVIDER.md`` is explicit that
        ``completed and aborted`` is a normal combination on the wire (a
        stopped run still persists a whole, shorter frame), but a script
        driving ``scan()`` as a single blocking call wants an exception here,
        not a flag it has to remember to check afterwards.
        """
        self.require_token()
        result = self.start_scan(**params)
        run_id = result.get("run_id")
        res = self._run_polled(
            start_result=result, busy_state="scanning", poll=poll, timeout=timeout, verb="scan",
            settle=lambda: self._await_terminal_result(
                lambda: self.get_scan_result(run_id, inline=inline), run_id=run_id, verb="scan",
            ),
        )
        if res.get("aborted"):
            raise RuntimeError(f"{self.name}: scan {run_id!r} was aborted")
        return res

    def write(
        self,
        objects: str | list[int | str] = "all",
        *,
        timeout: float = 1800.0,
        poll: float = 0.5,
        inline: bool = True,
        **params: Any,
    ) -> dict[str, Any]:
        """Blocking convenience: :meth:`start_write` then poll to a terminal
        state, returning :meth:`get_write_result`.

        Requires a held token, raised *before* anything is sent -- a start
        verb's own :class:`Busy` propagates untouched (nothing started, so
        there is nothing to clean up). Follows the same
        heartbeat / abort-on-exception shape as :meth:`approach` /
        :meth:`scan` (:meth:`_run_polled`), including raising
        :class:`ControlRevoked` untouched rather than aborting -- but the
        cleanup call on a timeout or ``KeyboardInterrupt`` is
        :meth:`abort_write`, not the general :meth:`abort`, so the write's
        own cooperative stop-plus-verified-retract runs and the partial
        result stays retrievable.

        ``inline=True`` by default -- unlike :meth:`scan` -- because the
        ``trace`` (written path with tip voltage along it) is usually the
        whole point of writing from a script. Once ``get_state()`` leaves
        ``writing``, :meth:`_await_terminal_result` polls ``get_write_result``
        until it settles (bounded, :data:`SETTLE_CAP_S`) rather than trusting
        the first fetch -- the provider's pump can briefly lag a tick behind
        thread death, and a caller must never read a bare
        ``{completed: false, aborted: false}`` as a finished write; past the
        cap this raises ``RuntimeError`` itself, naming ``run_id`` and the
        last record seen. Raises ``RuntimeError`` if the finished run reports
        ``aborted: true`` or a non-null ``error``; the message notes that
        :meth:`get_write_result` still has the partial trace, the same way
        ``docs/FLEX_PROVIDER.md`` promises for :meth:`abort_write`.
        """
        self.require_token()
        result = self.start_write(objects, **params)
        run_id = result.get("run_id")
        res = self._run_polled(
            start_result=result, busy_state="writing", poll=poll, timeout=timeout,
            verb="write", on_abort=self.abort_write,
            settle=lambda: self._await_terminal_result(
                lambda: self.get_write_result(run_id, inline=inline), run_id=run_id, verb="write",
            ),
        )
        if res.get("aborted") or res.get("error"):
            detail = "was aborted" if res.get("aborted") else f"ended with an error: {res['error']}"
            raise RuntimeError(
                f"{self.name}: write {run_id!r} {detail} -- get_write_result({run_id!r}, "
                f"inline=True) still has whatever partial trace the run produced"
            )
        return res

    @contextmanager
    def session(
        self,
        client: str,
        *,
        deadman_s: float = 30,
        withdraw_on_deadman: bool = False,
        **acquire_kwargs: Any,
    ):
        """Acquire control on enter; on exit **always** try :meth:`withdraw`
        then :meth:`release_control`, each guarded individually so a cleanup
        failure never masks the body's own exception (or the other cleanup
        step)::

            with afm.session(client="overnight", deadman_s=60,
                             withdraw_on_deadman=True) as afm:
                afm.approach(setpoint=1.0, pgain=0.0, igain=10.0)
                afm.scan(size_um=2, pixels=256, lines=256, line_rate_hz=20)

        :meth:`withdraw` is deliberately **not** wrapped in the
        abort-on-exception idiom :meth:`approach` / :meth:`scan` /
        :meth:`write` use: it is already a single blocking, bounded call
        (~6.5 s, ``method_bounds["withdraw"]``). If it still raises, cleanup
        falls back to :meth:`safe_park` (``"session cleanup failed"``);
        either failure is logged, never re-raised, so it cannot bury an
        exception from the body. :meth:`release_control` already never
        raises on its own, but is guarded here too, for the same reason.

        **A write still in flight on exit gets** :meth:`abort_write` **first.**
        ``docs/FLEX_PROVIDER.md`` says :meth:`withdraw` retracts "from ANY
        state", which is true of the physical motion -- but on the provider
        it only ramps ``Output.Z`` to 0; it does not set the litho worker's
        own cooperative abort flags the way :meth:`abort_write` (and
        :meth:`abort`) do. Left to plain :meth:`withdraw`, a write in
        progress would have its Z loop yanked out from under it without the
        run record closing ``aborted: true`` -- the opposite of the
        surviving-partial-result contract the rest of this driver relies on.
        So cleanup checks :meth:`get_state` first and calls
        :meth:`abort_write` when it reads ``"writing"``, before the existing
        :meth:`withdraw` / :meth:`safe_park` sequence runs regardless. The
        check is best-effort like every other cleanup step here: a failure
        (a dead read socket, ``ControlRevoked``) is logged and falls straight
        through to :meth:`withdraw`, never re-raised.
        """
        self.acquire_control(
            client, deadman_s=deadman_s, withdraw_on_deadman=withdraw_on_deadman,
            **acquire_kwargs,
        )
        try:
            yield self
        finally:
            try:
                if self.get_state() == "writing":
                    self.abort_write()
            except BaseException as e:  # noqa: BLE001 - cleanup must not throw
                self.log.error(
                    "session cleanup: checking for/aborting an in-flight write failed "
                    "(%s); proceeding to withdraw() anyway", e
                )
            try:
                self.withdraw()
            except BaseException as e:  # noqa: BLE001 - cleanup must not throw
                self.log.error(
                    "session cleanup: withdraw() failed (%s); falling back to safe_park", e
                )
                try:
                    self.safe_park("session cleanup failed")
                except BaseException as e2:  # noqa: BLE001 - cleanup must not throw
                    self.log.error("session cleanup: safe_park() also failed: %s", e2)
            try:
                self.release_control()
            except BaseException as e:  # noqa: BLE001 - never masks the body's exception
                self.log.error("session cleanup: release_control() failed: %s", e)


#: Default per-beat wire timeout for the Heartbeat thread's OWN calls (not
#: :meth:`AFMLitho.timeout_for`'s bound-derived timeouts used everywhere
#: else). A heartbeat is not latency-critical -- it exists to outlast a
#: blocking third-party call, not to answer fast -- so it should tolerate a
#: busy service far longer than a normal command-socket call would.
#: :meth:`Heartbeat.__init__` clamps it to at most half the beat ``period``,
#: since a beat that can itself block longer than its own period defeats the
#: point of having one.
HEARTBEAT_TIMEOUT_S = 5.0

#: How soon a FAILED beat is retried, instead of waiting out the rest of the
#: normal ``period``. Waiting a full period after a miss is expensive: with
#: ``period == deadman_s / 3`` (the default :meth:`AFMLitho.heartbeat_context`
#: derivation), one missed beat then waiting a full period before retrying
#: burns a third of the whole dead-man window on a single dropped packet.
HEARTBEAT_RETRY_S = 1.0

#: The floor :meth:`Heartbeat.__init__` enforces on ``retry_s``. An
#: instantly-failing beat (a closed socket, a method that raises with no wire
#: I/O at all) must not turn the retry loop into a busy loop pegging a core.
MIN_RETRY_S = 0.1


class Heartbeat:
    """Keep something alive across a blocking call, from a background thread.

    A dead-man timer is refreshed by requests, so any *blocking third-party
    call* is a gap in the refresh. This is not hypothetical: FLEX's own
    ``lockin_sweep`` sleeps ``Sweep Time + Initial Wait`` **before** it starts
    polling, so a 60 s sweep blocks for at least 61 s -- longer than a
    ``deadman_s=60`` token survives. Wrap every blocking non-AFM call::

        with Heartbeat(afm, period=20):
            lockin.lockin_sweep(config, timeout=120)

    Each beat gets a generous, independent timeout (:data:`HEARTBEAT_TIMEOUT_S`
    by default, via the ``beat_timeout_s`` kwarg, clamped to ``period / 2``
    but never below :data:`MIN_TIMEOUT`) -- a heartbeat is not latency-
    critical, and the old behaviour of borrowing the same tight timeout an
    interactive command gets (service bound + margin, floored at 1 s) meant
    an ordinarily-slow-but-fine reply under load looked identical to a dead
    socket.

    The thread never raises *from itself* and never retracts anything; it only
    refreshes, and it **never stops trying on its own** while the block is
    open -- a beat that fails is retried after ``retry_s`` (default
    :data:`HEARTBEAT_RETRY_S`, far shorter than ``period``) rather than after
    a full period, and failures never end the loop by themselves: only
    :meth:`stop` (i.e. leaving the ``with`` block) does, because if the
    service is merely slow rather than gone, the next beat can still land and
    the token survives. But a refresher that dies silently is worse than no
    refresher: the caller would keep blocking, believing it holds the
    instrument, while the dead-man runs down. So:

    * a failing beat is a ``warning``;
    * once consecutive failures have **spanned at least ``deadman_s``** since
      the last successful beat -- read once from ``afm`` at construction time
      -- the token is surely gone server-side, and :attr:`died` is set with an
      ``error``. When ``deadman_s`` is unknown (a bare ``beat`` callable with
      no ``afm``, or an ``afm`` that never called :meth:`AFMLitho.acquire_control`),
      this falls back to the old ``tolerate``-consecutive-failures count;
    * :attr:`died` is **not a latch** for this path: if a later beat succeeds
      (the service recovered before the real dead-man expired anything),
      :attr:`died` clears and beating continues normally;
    * ``__exit__`` re-raises a ``RuntimeError`` only if :attr:`died` is still
      set when the block exits, unless the body is already unwinding an
      exception of its own (which is the more informative failure, and must
      not be masked). If beats failed but recovered before exit, ``__exit__``
      logs a ``warning`` naming how many beats failed and does not raise.

    **A -32011 ``control_revoked`` is different from a transient failure, and
    is treated differently.** It means a human took the instrument, or the
    dead-man already expired the token -- there is nothing left to refresh, so
    a revoked token is **fatal and terminal on the first beat**: logged as an
    error immediately, :attr:`died` is set right away (and stays set -- unlike
    the span/tolerate path above, the loop actually stops, since there is
    nothing to recover from), and ``__exit__`` raises a ``RuntimeError``
    naming the lost control.

    The beat is a *callable*: when the instrument holds no token (this
    build's read-only surfaces, or before :meth:`AFMLitho.acquire_control`),
    it defaults to ``afm.get_state`` -- the same read socket, the same round
    trip. Once a token is held, the default becomes ``lambda:
    afm.heartbeat(timeout=...)`` (the clamped ``beat_timeout_s`` above),
    refreshing the dead-man for real; an explicit ``beat`` callable always
    overrides this and is responsible for its own timeout.
    :meth:`AFMLitho.heartbeat_context` builds one with ``period = deadman_s /
    3`` (two missed beats of slack).

    Args:
        afm: the instrument to beat -- used for the default callable, its
            logger, and (once) its ``_deadman_s`` for span-based death.
        beat: what to call on each tick. Defaults to ``afm.heartbeat`` when
            ``afm`` holds a token, else ``afm.get_state``.
        period: seconds between beats when the last beat succeeded.
        tolerate: consecutive-failures fallback used only when ``afm``'s
            ``deadman_s`` is unknown. A -32011 ``control_revoked`` bypasses
            this entirely.
        beat_timeout_s: per-beat wire timeout for the DEFAULT beat callable
            (ignored when an explicit ``beat`` is given), clamped to at most
            ``period / 2``.
        retry_s: seconds before retrying after a FAILED beat, instead of
            waiting out the rest of ``period``.
    """

    def __init__(
        self,
        afm: AFMLitho | None = None,
        beat: Callable[[], Any] | None = None,
        *,
        period: float = 10.0,
        tolerate: int = 3,
        beat_timeout_s: float = HEARTBEAT_TIMEOUT_S,
        retry_s: float = HEARTBEAT_RETRY_S,
    ):
        if tolerate < 1:
            raise ValueError("tolerate must be at least 1")
        if retry_s < MIN_RETRY_S:
            raise ValueError(
                f"retry_s must be at least {MIN_RETRY_S}s -- an instantly-failing beat "
                f"must not busy-loop"
            )
        if beat_timeout_s < MIN_TIMEOUT:
            raise ValueError(f"beat_timeout_s must be at least MIN_TIMEOUT ({MIN_TIMEOUT}s)")
        if beat is None:
            if afm is None:
                raise ValueError("Heartbeat needs an instrument or a beat callable")
            if getattr(afm, "token", None):
                # Never below MIN_TIMEOUT even when period/2 is tighter (a
                # short deadman_s -- e.g. 5s -> period 1.67s -> period/2
                # 0.83s -- would otherwise floor the beat's own timeout below
                # what the driver ever floors an ordinary call to).
                effective_timeout = max(MIN_TIMEOUT, min(beat_timeout_s, period / 2))
                beat = lambda: afm.heartbeat(timeout=effective_timeout)  # noqa: E731
            else:
                beat = afm.get_state
        self.afm = afm
        self.beat = beat
        self.period = period
        self.tolerate = tolerate
        self.beat_timeout_s = beat_timeout_s
        self.retry_s = retry_s
        #: ``afm``'s dead-man window, read once here -- ``None`` when unknown
        #: (no ``afm``, or control was never acquired), which is exactly when
        #: death falls back to the ``tolerate`` count instead.
        self.deadman_s: float | None = getattr(afm, "_deadman_s", None) if afm is not None else None
        self.log = getattr(afm, "log", None) or logging.getLogger("afm.heartbeat")
        #: beats completed without raising -- the number a test asserts on.
        self.beats = 0
        #: consecutive failures right now; reset by any successful beat.
        self.failures = 0
        #: TOTAL failed beats this run (not reset by a recovery) -- what
        #: __exit__ reports in its recovery warning.
        self.failed_beats = 0
        #: the most recent exception a beat raised, if any.
        self.last_error: BaseException | None = None
        self._died = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: float = 0.0

    @property
    def alive(self) -> bool:
        """Is the refresher still beating?"""
        return self._thread is not None and self._thread.is_alive()

    @property
    def died(self) -> bool:
        """Did the refresher give up on its own (rather than being stopped)?"""
        return self._died.is_set()

    def _run(self) -> None:
        self._last_success = time.monotonic()
        while True:
            wait = self.retry_s if self.failures else self.period
            if self._stop.wait(wait):
                return
            try:
                self.beat()
            except BaseException as e:  # noqa: BLE001 - a beat thread never raises
                self.last_error = e
                if getattr(e, "code", None) == CONTROL_REVOKED:
                    # Control is GONE -- a human took the instrument, or the
                    # dead-man already expired the token. There is nothing
                    # left to refresh and nothing to recover from, so this is
                    # fatal AND terminal on the first beat: stop the loop
                    # (unlike the transient path below, which keeps trying).
                    self.log.error(
                        "heartbeat STOPPING: control was revoked (-32011) -- %s", e)
                    self._died.set()
                    return
                self.failures += 1
                self.failed_beats += 1
                elapsed = time.monotonic() - self._last_success
                self.log.warning(
                    "heartbeat beat failed (%d consecutive, %d total, %.1fs since last "
                    "success) -- retrying in %gs: %s",
                    self.failures, self.failed_beats, elapsed, self.retry_s, e)
                if not self._died.is_set():
                    if self.deadman_s is not None:
                        given_up = elapsed >= self.deadman_s
                    else:
                        given_up = self.failures >= self.tolerate
                    if given_up:
                        self.log.error(
                            "heartbeat: the token is surely gone (%s) -- nothing has "
                            "refreshed it in %.1fs; still retrying every %gs in case the "
                            "service recovers: %s",
                            (f"{elapsed:.1f}s >= deadman_s={self.deadman_s:.1f}s"
                             if self.deadman_s is not None
                             else f"{self.failures} consecutive failures >= tolerate="
                                  f"{self.tolerate}"),
                            elapsed, self.retry_s, e)
                        self._died.set()
                # No `return`: a failed beat -- even one that just tipped
                # `died` -- never ends the loop by itself. Only `stop()`
                # (leaving the `with` block) does, because the service may
                # still recover.
                continue
            if self._died.is_set():
                self._died.clear()
            self.failures = 0
            self.beats += 1
            self._last_success = time.monotonic()

    def start(self) -> Heartbeat:
        if self._thread is not None:
            raise RuntimeError("Heartbeat already started")
        self._stop.clear()
        self._died.clear()
        self._thread = threading.Thread(target=self._run, name="afm-heartbeat", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is None:
            return
        # A beat can now legitimately block up to ~beat_timeout_s (default
        # 5s, or whatever an explicit `beat` callable takes) before it even
        # notices `_stop`, so the join has to cover one such call plus one
        # retry-spaced re-check, not a hardcoded 2s that predates
        # beat_timeout_s existing at all.
        join_timeout = self.beat_timeout_s + self.retry_s + 1.0
        self._thread.join(timeout=join_timeout)
        if self._thread.is_alive():
            # Still running past its own timeout budget: do NOT clear the
            # thread reference (that would silently forget a beat thread that
            # is still out there, possibly still mutating self.* right now)
            # and do not touch `died`/`failed_beats` here -- __exit__ must not
            # read them until a join has actually completed.
            self.log.error(
                "heartbeat: the beat thread did not stop within %.1fs of being asked "
                "to -- a beat is still in flight past its own timeout budget; leaving "
                "the thread handle (see `alive`) instead of forgetting it", join_timeout)
            return
        self._thread = None

    def __enter__(self) -> Heartbeat:
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
        if self._thread is not None:
            # stop() could not join the thread -- it may still be running and
            # mutating `died`/`failed_beats`/`last_error` right now, so this
            # branch must not read any of them. Report the stuck thread
            # itself, distinctly from a normal died/recovered outcome.
            if exc_type is None:
                raise RuntimeError(
                    "heartbeat: the beat thread did not stop -- a beat is still in "
                    "flight past its own timeout; heartbeat state is unreliable and "
                    "the instrument may or may not still be refreshed"
                )
            return
        if self._died.is_set() and exc_type is None:
            if getattr(self.last_error, "code", None) == CONTROL_REVOKED:
                raise RuntimeError(
                    "heartbeat lost control: the token was revoked (-32011 "
                    "control_revoked) -- a human took the instrument, or the "
                    "dead-man expired it; the instrument was not being refreshed "
                    "for part of this block"
                ) from self.last_error
            raise RuntimeError(
                f"heartbeat died: no beat succeeded for at least "
                f"{self.deadman_s if self.deadman_s is not None else self.tolerate}"
                f"{'s' if self.deadman_s is not None else ' consecutive failed beats'}; "
                f"the instrument was not being refreshed for part of this block"
            ) from self.last_error
        if self.failed_beats and not self._died.is_set():
            self.log.warning(
                "heartbeat: %d beat(s) failed during this block but the instrument "
                "recovered before it exited -- nothing to do", self.failed_beats)