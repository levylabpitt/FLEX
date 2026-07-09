"""Templates for `flex new driver` and `flex new package`."""

from __future__ import annotations

from pathlib import Path

_PROTOCOLS = {
    "visa": ("VISAInstrument", 'resource: str = "GPIB0::1::INSTR"', "resource"),
    "tcp": ("TCPInstrument", 'host: str = "localhost", port: int = 5025', "host, port"),
    "serial": ("SerialInstrument", 'port: str = "COM1"', "port"),
    "zmq": ("ZMQInstrument", 'address: str = "tcp://localhost:29170"', "address"),
}

_DRIVER = '''"""FLEX driver for {name}."""

from flex_protocols import {base}


class {name}({base}):
    def __init__(self, name: str = "{lower}", {init_args}, **kwargs):
        super().__init__(name, {forward}, **kwargs)

        # Declare parameters: name, commands (or getter/setter), unit.
        # self.voltage = self.add_parameter(
        #     "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {{}}",
        #     get_parser=float, unit="V",
        # )

    # Add instrument methods here. Conform to a capability protocol
    # (flex.instrument.capabilities) where one fits, e.g. get_temperature().
'''

_PYPROJECT = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
description = "FLEX drivers for {label}"
requires-python = ">=3.11"
dependencies = ["flex-core", "flex-protocols"]

[project.entry-points."flex.drivers"]
{name} = "{module}:CATALOG"

[tool.hatch.build.targets.wheel]
packages = ["src/{module}"]
"""

_PKG_INIT = '''"""FLEX drivers for {label}."""

# Driver catalog: {{driver name: "module:Class"}} — the package manager lists
# these and `flex enable <name>` activates them individually.
CATALOG: dict[str, str] = {{
    # "{prefix}.mydevice": "{module}.mydevice:MyDevice",
}}
'''


def driver_template(name: str, protocol: str) -> str:
    if protocol not in _PROTOCOLS:
        raise ValueError(f"Unknown protocol '{protocol}'. Choose from: {', '.join(_PROTOCOLS)}")
    base, init_args, forward = _PROTOCOLS[protocol]
    return _DRIVER.format(
        name=name, base=base, lower=name.lower(), init_args=init_args, forward=forward
    )


def create_package(name: str, out: Path) -> Path:
    module = name.replace("-", "_")
    label = name.removeprefix("flex-drivers-").removeprefix("flex-")
    root = out / name
    src = root / "src" / module
    src.mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        _PYPROJECT.format(name=name, module=module, label=label), encoding="utf-8"
    )
    (src / "__init__.py").write_text(
        _PKG_INIT.format(label=label, module=module, prefix=label), encoding="utf-8"
    )
    (src / "py.typed").touch()
    return root
