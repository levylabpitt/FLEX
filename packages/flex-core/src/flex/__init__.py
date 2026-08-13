"""FLEX: Framework for Laboratory EXperiments.

The ``flex`` namespace re-exports the user-facing API of the standard
installation. Names that live in the optional flex-exp package are loaded
lazily with a helpful error if the package is missing.
"""

from importlib import import_module

__version__ = "2.0.0a1"

_LAZY = {
    # flex-core
    "get_logger": "flex.log",
    "EventBus": "flex.events",
    "FlexConfig": "flex.config",
    "load_config": "flex.config",
    "Instrument": "flex.instrument",
    "Parameter": "flex.instrument",
    "SimulatedInstrument": "flex.instrument",
    "VISAInstrument": "flex.protocols",
    "TCPInstrument": "flex.protocols",
    "SerialInstrument": "flex.protocols",
    "ZMQInstrument": "flex.protocols",
    # flex-exp
    "Experiment": "flex_exp",
    "Measurement": "flex_exp",
    "Scan": "flex_exp",
    "sweep": "flex_exp",
    "CESession": "flex_exp",
}

_PACKAGE_OF = {"flex_exp": "flex-exp"}


def __getattr__(name: str):
    if name in _LAZY:
        module = _LAZY[name]
        try:
            return getattr(import_module(module), name)
        except ImportError as e:
            pkg = _PACKAGE_OF.get(module.split(".")[0])
            if pkg:
                raise ImportError(
                    f"flex.{name} requires the '{pkg}' package. Install it with: pip install {pkg}"
                ) from e
            raise
    raise AttributeError(f"module 'flex' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
