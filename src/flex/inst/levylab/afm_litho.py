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
command socket (with the eager ``ACK`` connect check every LevyLab ZMQ
instrument does); a second :class:`~flex_afm._link.JsonRpcLink` opens the read
socket, and every ``get*`` / polling call goes there. That is the whole point
of the split: a 5 Hz ``getState`` loop must not stall behind a blocking
command once mutating verbs land.

Both links are :class:`~flex_afm._link.JsonRpcLink`, **this repo's** subclass
of FLEX v1's :class:`flex.inst.base.Instrument` -- so an ``AFMLitho`` still IS
a FLEX instrument (``idn()`` / ``help()`` / ``close()``, and v1's
``CESession``-style code can hold one), but with the per-call timeout, the
socket reset after a missed reply, the unique request ids and the ``error`` ->
exception mapping v1 does not have. See :mod:`flex_afm._link` for the full
list of what is added and why.

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
helper. A design over the 87,380-point out-wave cap raises
:class:`PatternTooLarge`. ``startMeasure`` / ``executePass`` are still named
by the provider and answer ``-32601 "not implemented in this build"`` -- see
:data:`RESERVED_VERBS`.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
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
    """-32602 ``invalid_params`` from :meth:`AFMLitho.load_pattern`: at least
    one object in the design exceeds the 87,380-point out-wave cap.
    ``.objects`` (``data["objects_over_cap"]``) lists the offenders as
    ``[{name, points, cap}, ...]``, so a script can report *which* object is
    too big instead of bisecting the design by hand. The provider leaves the
    previously loaded design (if any) in place on this refusal -- a script
    that catches this can keep writing whatever was loaded before.

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
        timeout: fallback for every per-call timeout. ``None`` uses the
            link's own 5 s default.
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
        # `timeout` is omitted entirely when None so JsonRpcLink's own default
        # stays the single source of that number -- a restated copy here would
        # fork silently the day the link's default changes.
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
        """The loaded design, one entry per object, with point *counts*."""
        return self._read_call("getPattern")

    def get_written(self) -> dict[str, Any]:
        """What this session has actually written."""
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
        """The held token, or automatically acquire control if not already held."""
        if self._token is None:
            try:
                self.acquire_control(self.name, deadman_s=60.0)
            except Exception as exc:
                raise RuntimeError(
                    f"{self.name}: no control token held and auto-acquire failed ({exc})"
                ) from exc
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
        not just :class:`ZMQInstrumentError`: ``JsonRpcLink.call`` also
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

    def heartbeat(self, token: str | None = None) -> dict[str, Any]:
        """Refresh the dead-man. Uses the stored token when ``token`` is
        omitted (via :meth:`require_token`, so a script holding no token gets
        an immediate, clear ``RuntimeError`` rather than a wire round trip).

        Raises :class:`ControlRevoked` (-32011) if the token was ours and is
        not any more -- a human took the instrument, or the dead-man expired
        it. **Do not blindly re-acquire** on that exception.
        """
        tok = token if token is not None else self.require_token()
        return self._command_call("heartbeat", {"token": tok})

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
        ``self.heartbeat()``. Wrap any blocking third-party call while
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
        keeps the dead-man alive."""
        token = self.require_token()
        params: dict[str, Any] = {"token": token}
        if setpoint is not None:
            params["setpoint"] = float(setpoint)
        if pgain is not None:
            params["pgain"] = float(pgain)
        if igain is not None:
            params["igain"] = float(igain)
        if settle_s is not None:
            params["settle_s"] = float(settle_s)
        if mode is not None:
            params["mode"] = mode
        return self._command_call("startApproach", params)

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

    def load_pattern(self, source: str) -> dict[str, Any]:
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

        Raises :class:`PatternTooLarge` (-32602, ``.objects``) if any object
        exceeds the 87,380-point out-wave cap -- the provider leaves whatever
        was previously loaded in place on this refusal, so a half-replaced
        pattern never becomes the next :meth:`start_write`'s target."""
        token = self.require_token()
        try:
            return self._command_call("loadPattern", {"token": token, "source": source})
        except ZMQInstrumentError as e:
            data = e.data if isinstance(e.data, dict) else {}
            if e.code == INVALID_PARAMS and data.get("objects_over_cap") is not None:
                raise PatternTooLarge(str(e), code=e.code, data=e.data) from e
            raise

    def load_sample(self, file_name: str, *, fresh: bool = True) -> dict[str, Any]:
        """Load a sample scan file (e.g. 'SA40656B0000.ibw') into the twin."""
        token = self.require_token()
        try:
            return self._command_call("loadSample", {"token": token, "file": file_name, "fresh": bool(fresh)}, timeout=10.0)
        except ZMQInstrumentError as e:
            if "method not found" in str(e).lower():
                import json
                import urllib.request
                req = urllib.request.Request(
                    "http://localhost:7461/api/sample/load",
                    data=json.dumps({"file": file_name, "fresh": bool(fresh)}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    def start_write(
        self,
        objects: str | list[int] = "all",
        *,
        setpoint: float | None = None,
        amp_gain: float | None = None,
        deadman_s: float | None = None,
    ) -> dict[str, Any]:
        """START+POLL lithography, sub-second by construction:
        ``{run_id, est_s, objects, state, backend}``. Poll ``get_state()``
        until it leaves ``writing``, then fetch :meth:`get_write_result`.
        Prefer :meth:`write` for a blocking call that already does both.

        ``objects`` is ``"all"`` (the default -- clears the per-session
        written set and writes every enabled object) or a list of integer
        **indices** into the loaded design, written whether or not they have
        been written before. **No pattern loaded is a refusal, not a demo**
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
        :meth:`heartbeat_context`)."""
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
        """
        self.require_token()
        result = self.start_approach(**params)
        run_id = result.get("run_id")
        self._run_polled(
            start_result=result, busy_state="approaching", poll=poll, timeout=timeout,
            verb="approach",
        )
        status = self.get_status()
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
        objects: str | list[int] = "all",
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


class Heartbeat:
    """Keep something alive across a blocking call, from a background thread.

    A dead-man timer is refreshed by requests, so any *blocking third-party
    call* is a gap in the refresh. This is not hypothetical: FLEX's own
    ``lockin_sweep`` sleeps ``Sweep Time + Initial Wait`` **before** it starts
    polling, so a 60 s sweep blocks for at least 61 s -- longer than a
    ``deadman_s=60`` token survives. Wrap every blocking non-AFM call::

        with Heartbeat(afm, period=20):
            lockin.lockin_sweep(config, timeout=120)

    The thread never raises *from itself* and never retracts anything; it only
    refreshes. But a refresher that dies silently is worse than no refresher:
    the caller would keep blocking, believing it holds the instrument, while
    the dead-man runs down. So:

    * a failing beat is a ``warning``, and up to ``tolerate`` **consecutive**
      failures are absorbed -- one dropped packet mid-sweep is not a reason to
      hand the instrument back;
    * exhausting them stops the loop with an ``error``, and sets
      :attr:`died`;
    * ``__exit__`` re-raises that as a ``RuntimeError`` in the *caller's*
      thread, unless the body is already unwinding an exception of its own
      (which is the more informative failure, and must not be masked).

    **A -32011 ``control_revoked`` is different from a transient failure, and
    is treated differently.** It means a human took the instrument, or the
    dead-man already expired the token -- there is nothing left to refresh,
    and the ``tolerate`` counter is not the right response (waiting out three
    "consecutive failures" just delays telling the script the truth). So a
    revoked token is **fatal on the first beat**: logged as an error
    immediately, :attr:`died` is set right away, and ``__exit__`` raises a
    ``RuntimeError`` naming the lost control. A plain timeout or transient
    wire error still gets the ``tolerate``-consecutive-failures grace above.

    The beat is a *callable*: when the instrument holds no token (this
    build's read-only surfaces, or before :meth:`AFMLitho.acquire_control`),
    it defaults to ``afm.get_state`` -- the same read socket, the same round
    trip. Once a token is held, the default becomes ``lambda:
    afm.heartbeat()``, refreshing the dead-man for real; an explicit ``beat``
    callable always overrides this. :meth:`AFMLitho.heartbeat_context` builds
    one with ``period = deadman_s / 3`` (two missed beats of slack).

    Args:
        afm: the instrument to beat -- used for the default callable and for
            its logger.
        beat: what to call on each tick. Defaults to ``afm.heartbeat`` when
            ``afm`` holds a token, else ``afm.get_state``.
        period: seconds between beats.
        tolerate: consecutive *transient* failures absorbed before giving up.
            A -32011 ``control_revoked`` bypasses this entirely.
    """

    def __init__(
        self,
        afm: AFMLitho | None = None,
        beat: Callable[[], Any] | None = None,
        *,
        period: float = 10.0,
        tolerate: int = 3,
    ):
        if beat is None:
            if afm is None:
                raise ValueError("Heartbeat needs an instrument or a beat callable")
            beat = (lambda: afm.heartbeat()) if getattr(afm, "token", None) else afm.get_state
        if tolerate < 1:
            raise ValueError("tolerate must be at least 1")
        self.afm = afm
        self.beat = beat
        self.period = period
        self.tolerate = tolerate
        self.log = getattr(afm, "log", None) or logging.getLogger("afm.heartbeat")
        #: beats completed without raising -- the number a test asserts on.
        self.beats = 0
        #: consecutive failures right now; reset by any successful beat.
        self.failures = 0
        #: the most recent exception a beat raised, if any.
        self.last_error: BaseException | None = None
        self._died = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def alive(self) -> bool:
        """Is the refresher still beating?"""
        return self._thread is not None and self._thread.is_alive()

    @property
    def died(self) -> bool:
        """Did the refresher give up on its own (rather than being stopped)?"""
        return self._died.is_set()

    def _run(self) -> None:
        while not self._stop.wait(self.period):
            try:
                self.beat()
            except BaseException as e:  # noqa: BLE001 - a beat thread never raises
                self.last_error = e
                if getattr(e, "code", None) == CONTROL_REVOKED:
                    # Control is GONE -- a human took the instrument, or the
                    # dead-man already expired the token. There is nothing
                    # left for `tolerate` to wait out, so this is fatal on the
                    # first beat, not the `tolerate`-th.
                    self.log.error(
                        "heartbeat STOPPING: control was revoked (-32011) -- %s", e)
                    self._died.set()
                    return
                self.failures += 1
                self.log.warning("heartbeat beat failed (%d/%d): %s",
                                 self.failures, self.tolerate, e)
                if self.failures >= self.tolerate:
                    self.log.error(
                        "heartbeat STOPPING after %d consecutive failures -- nothing is "
                        "refreshing the instrument any more: %s", self.failures, e)
                    self._died.set()
                    return
                continue
            self.failures = 0
            self.beats += 1

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
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def __enter__(self) -> Heartbeat:
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
        if self._died.is_set() and exc_type is None:
            if getattr(self.last_error, "code", None) == CONTROL_REVOKED:
                raise RuntimeError(
                    "heartbeat lost control: the token was revoked (-32011 "
                    "control_revoked) -- a human took the instrument, or the "
                    "dead-man expired it; the instrument was not being refreshed "
                    "for part of this block"
                ) from self.last_error
            raise RuntimeError(
                f"heartbeat died after {self.tolerate} consecutive failed beats; "
                f"the instrument was not being refreshed for part of this block"
            ) from self.last_error
