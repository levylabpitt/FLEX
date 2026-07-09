"""VISA instruments (GPIB, USB, RS-232 via VISA, TCPIP INSTR/SOCKET)."""

from __future__ import annotations

import pyvisa

from flex.instrument import Instrument


class VISAInstrument(Instrument):
    """Base class for instruments controlled through VISA.

    Args:
        name: Instrument name used in logs, snapshots, and experiments.
        resource: VISA resource string, e.g. ``"GPIB0::12::INSTR"``.
        timeout: Seconds to wait for responses.
        read_termination / write_termination: Message terminators.
        backend: Optional VISA library spec (e.g. ``"@py"`` for pyvisa-py).
    """

    def __init__(
        self,
        name: str,
        resource: str,
        *,
        timeout: float = 5.0,
        read_termination: str = "\n",
        write_termination: str = "\n",
        backend: str = "",
        **kwargs,
    ):
        super().__init__(name, **kwargs)
        self._address = resource
        self._manager = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
        try:
            self._resource = self._manager.open_resource(
                resource,
                timeout=int(timeout * 1000),
                read_termination=read_termination,
                write_termination=write_termination,
            )
        except Exception:
            self.log.error("Could not open VISA resource %s", resource)
            raise
        self.log.info("Connected: %s", resource)

    @property
    def timeout(self) -> float:
        return self._resource.timeout / 1000

    @timeout.setter
    def timeout(self, seconds: float) -> None:
        self._resource.timeout = int(seconds * 1000)

    def write(self, cmd: str) -> None:
        self.log.debug("write: %s", cmd)
        self._resource.write(cmd)

    def read(self) -> str:
        response = self._resource.read().strip()
        self.log.debug("read: %s", response)
        return response

    def query(self, cmd: str) -> str:
        self.log.debug("query: %s", cmd)
        response = self._resource.query(cmd).strip()
        self.log.debug("reply: %s", response)
        return response

    def idn(self) -> dict[str, str | None]:
        """Parse the standard ``*IDN?`` reply. Override for non-SCPI instruments."""
        fields = [f.strip() or None for f in self.query("*IDN?").split(",")]
        fields += [None] * (4 - len(fields))
        return dict(zip(("vendor", "model", "serial", "firmware"), fields[:4], strict=True))

    def close(self) -> None:
        resource = getattr(self, "_resource", None)
        if resource is not None:
            self.log.info("Closing %s", self._address)
            resource.close()
            self._resource = None
