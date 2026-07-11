"""Smoke tests for every LevyLab driver against FakeIFServer.

Each test asserts that the ported snake_case methods emit the exact v1
JSON-RPC method names and param-dict key spellings.
"""

import pytest

from flex_drivers.levylab import capabilities
from flex_drivers.levylab.aerotech import Aerotech
from flex_drivers.levylab.cryostation import Cryostation
from flex_drivers.levylab.krohn_hite import KrohnHite7008
from flex_drivers.levylab.lockin import Lockin
from flex_drivers.levylab.opticool import Opticool
from flex_drivers.levylab.oxford import Oxford1820, OxfordVRM
from flex_drivers.levylab.ppms import PPMS
from flex_drivers.levylab.tc import TC_CF, TC_MNK
from flex_drivers.levylab.transport_server import TransportServer
from flex_protocols.testing import FakeIFServer

HANDLERS = {
    # Lockin
    "getAO": [{"Y": [0.25]}],
    "getAI": {"AI": 1.23},
    "setAO_Amplitude": "ok",
    "setAO_DC": "ok",
    "setAO_Frequency": "ok",
    "setAO_Phase": "ok",
    "setAO_Function": "ok",
    "getResults": {
        "Results (Dictionary)": [
            {"key": "AI1.Ref1.X", "value": 0.5},
            {"key": "AI1.Mean", "value": 0.1},
        ]
    },
    "setState": "ok",
    "getState": "idle",
    "setSweepTime": "ok",
    "setSamplingFsMode": "ok",
    "getSweepWaveforms": {"waveforms": []},
    "setSweep": "ok",
    # Krohn-Hite
    "setAllChannels": "ok",
    "setChannel": "ok",
    "getChannel": {"channel": 3, "gain": "10"},
    # Transport Server
    "startTransport": "started",
    "stopTransport": "stopped",
    "getStatus": {"Status": "idle"},
    "setExptFolder": "ok",
    "getExptFolder": {"folder": "C:/data/expt1"},
    "setExptComments": "ok",
    "getExptComments": {"comments": "cooldown 42"},
    "setExptParam": "ok",
    "setRefreshTime": "ok",
    "setSweepConfig": "ok",
    "getSweepConfig": {"sweepTime": 10},
    # Temperature / Magnet apps
    "getTemperature": 1.5,
    "setTemperature": "ok",
    "getTemperatureTarget": 2.0,
    "getMagnet": 0.5,
    "setMagnet": "ok",
    "getMagnetTarget": 1.0,
    "getLHeLevel": 42.0,
    "getHeater": 0.001,
}


@pytest.fixture
def server():
    with FakeIFServer(dict(HANDLERS)) as s:
        yield s


def last(server):
    request = server.requests[-1]
    return request["method"], request["params"]


# -- Lockin -------------------------------------------------------------------


def test_lockin_get_ao_ai(server):
    with Lockin(address=server.address) as li:
        assert li.get_ao(2) == [{"Y": [0.25]}]
        assert last(server) == ("getAO", {"channel": 2})
        assert li.get_ai(3) == {"AI": 1.23}
        assert last(server) == ("getAI", {"channel": 3})


def test_lockin_set_ao_family(server):
    with Lockin(address=server.address) as li:
        li.set_ao_amplitude(1, 0.01)
        assert last(server) == ("setAO_Amplitude", {"Channel": 1, "Amplitude": 0.01})
        li.set_ao_dc(2, 0.5)
        assert last(server) == ("setAO_DC", {"Channel": 2, "DC": 0.5})
        li.set_ao_frequency(1, 13.0)
        assert last(server) == ("setAO_Frequency", {"Channel": 1, "Frequency": 13.0})
        li.set_ao_phase(1, 90.0)
        assert last(server) == ("setAO_Phase", {"Channel": 1, "Phase": 90.0})
        li.set_ao_function(1, "Sine")
        assert last(server) == ("setAO_Function", {"Channel": 1, "Function": "Sine"})


def test_lockin_set_ao_function_validation(server):
    with Lockin(address=server.address) as li:
        before = len(server.requests)
        with pytest.raises(ValueError, match="Invalid value: Sawtooth"):
            li.set_ao_function(1, "Sawtooth")
        assert len(server.requests) == before  # nothing was sent


def test_lockin_daq_capability_alias(server):
    with Lockin(address=server.address) as li:
        assert isinstance(li, capabilities.DAQ)
        li.set_ao(4, -0.1)  # canonical DAQ setter drives the DC offset
        assert last(server) == ("setAO_DC", {"Channel": 4, "DC": -0.1})


def test_lockin_state_and_results(server):
    with Lockin(address=server.address) as li:
        li.set_state("start")
        assert last(server) == ("setState", {"State": "start"})
        assert li.get_state() == "idle"
        assert li.get_results()["Results (Dictionary)"][0]["key"] == "AI1.Ref1.X"
        assert li.get_lockin_result(1, "X", ref=1) == 0.5
        assert li.get_lockin_result(1, "Mean") == 0.1
        assert li.get_lockin_result(2, "Theta") is None


def test_lockin_sweep_config(server):
    config = {
        "Sweep Time (s)": 1.0,
        "Initial Wait (s)": 2,
        "Return to Start": False,
        "Channels": [
            {
                "Enable?": True,
                "Channel": 1,
                "Start": 0.0,
                "End": 1.0,
                "Pattern": "Ramp /",
                "Table": [],
            }
        ],
    }
    with Lockin(address=server.address) as li:
        li.set_sweep(config)
        assert last(server) == ("setSweep", config)
        li.set_sweep_time(12.5)
        assert last(server) == ("setSweepTime", 12.5)  # v1 sends a bare value
        li.set_sampling_mode("Continuous")
        assert last(server) == ("setSamplingFsMode", "Continuous")
        assert li.get_sweep_waveforms() == {"waveforms": []}


# -- Krohn-Hite 7008 -----------------------------------------------------------


def test_krohn_hite_channels(server):
    config = [
        {"channel": 1, "gain": "10", "input": "DIFF", "shunt": "10M", "couple": "AC", "filter": "OFF"}
    ]
    with KrohnHite7008(address=server.address) as kh:
        kh.set_kh_channel(config)
        assert last(server) == ("setAllChannels", {"allChannelProperties": config})
        kh.set_kh_channel_single(config)
        assert last(server) == ("setChannel", {"allChannelProperties": config})
        assert kh.get_channel(3) == {"channel": 3, "gain": "10"}
        assert last(server) == ("getChannel", {"channel": 3})


# -- Transport Server ----------------------------------------------------------


def test_transport_server_start_stop_status(server):
    with TransportServer(address=server.address) as ts:
        assert ts.start_transport("LockinSweep") == "started"
        assert last(server) == ("startTransport", {"method": "LockinSweep"})
        with pytest.raises(ValueError, match="Invalid value: FooVI"):
            ts.start_transport("FooVI")
        ts.stop_transport()
        assert last(server) == ("stopTransport", {})
        assert ts.get_status() == "idle"
        assert last(server) == ("getStatus", {})


def test_transport_server_expt_metadata(server):
    with TransportServer(address=server.address) as ts:
        ts.set_expt_folder("C:/data/expt1")
        assert last(server) == ("setExptFolder", {"folder": "C:/data/expt1"})
        assert ts.get_expt_folder() == "C:/data/expt1"
        ts.set_expt_comments("cooldown 42")
        assert last(server) == ("setExptComments", {"comments": "cooldown 42"})
        assert ts.get_expt_comments() == "cooldown 42"
        assert ts.get_expt_details() == ("C:/data/expt1", "cooldown 42")


def test_transport_server_expt_param_validation(server):
    with TransportServer(address=server.address) as ts:
        ts.set_expt_param("Vg (V)", [0.1, 0.2])
        assert last(server) == ("setExptParam", {"Vg (V)": [0.1, 0.2]})
        ts.set_expt_param("mixed", [1, 0.5])
        assert last(server) == ("setExptParam", {"mixed": [1, 0.5]})
        ts.set_expt_param("label", "abc")
        assert last(server) == ("setExptParam", {"label": "abc"})
        with pytest.raises(TypeError, match="must be str, int, float, or list"):
            ts.set_expt_param("bad", [1, None])
        with pytest.raises(TypeError, match="must be str, int, float, or list"):
            ts.set_expt_param("bad", {"nested": 1})
        with pytest.raises(TypeError, match="must be str, int, float, or list"):
            ts.set_expt_param("bad", True)


def test_transport_server_refresh_and_sweep_config(server):
    with TransportServer(address=server.address) as ts:
        ts.set_refresh_time(200.0)
        assert last(server) == ("setRefreshTime", {"Refresh Time (ms)": 200.0})
        sweep = {"sweepTime": 10, "initialWaitTime": 1}
        ts.set_sweep_config(sweep)
        assert last(server) == ("setSweepConfig", sweep)
        assert ts.get_sweep_config() == {"sweepTime": 10}


# -- PPMS ----------------------------------------------------------------------


def test_ppms_temperature(server):
    with PPMS(address=server.address) as ppms:
        assert ppms.get_temperature() == 1.5
        assert last(server) == ("getTemperature", [0])
        ppms.set_temperature(300.0, 10.0, channel=1)
        assert last(server) == (
            "setTemperature",
            {"temperature": 300.0, "rate": 10.0, "channel": 1},
        )
        ppms.set_temperature(2.0, rate=1.0)  # capability-style keyword rate
        assert last(server) == ("setTemperature", {"temperature": 2.0, "rate": 1.0, "channel": 0})
        with pytest.raises(ValueError, match="requires a ramp rate"):
            ppms.set_temperature(2.0)
        assert ppms.get_temperature_target(2) == 2.0
        assert last(server) == ("getTemperatureTarget", [2])


def test_ppms_magnet_and_level(server):
    with PPMS(address=server.address) as ppms:
        assert ppms.get_magnet() == 0.5
        assert last(server) == ("getMagnet", {})
        ppms.set_magnet(1.0, 0.01)
        assert last(server) == (
            "setMagnet",
            {"field": 1.0, "rate": 0.01, "axis": "Z", "mode": "Persistent"},
        )
        assert ppms.get_magnet_target() == 1.0
        assert last(server) == ("getMagnetTarget", ["Z"])
        # canonical capability aliases
        assert ppms.get_field() == 0.5
        ppms.set_field(2.0, rate=0.02)
        assert last(server) == (
            "setMagnet",
            {"field": 2.0, "rate": 0.02, "axis": "Z", "mode": "Persistent"},
        )
        with pytest.raises(ValueError, match="requires a ramp rate"):
            ppms.set_field(2.0)
        assert ppms.get_lhe_level() == 42.0
        assert last(server) == ("getLHeLevel", {})


def test_ppms_capabilities_and_parameters(server):
    with PPMS(address=server.address) as ppms:
        assert isinstance(ppms, capabilities.Temperature)
        assert isinstance(ppms, capabilities.Magnet)
        assert ppms.parameters["temperature"].unit == "K"
        assert ppms.parameters["field"].unit == "T"


# -- Opticool ------------------------------------------------------------------


def test_opticool(server):
    with Opticool(address=server.address) as oc:
        assert isinstance(oc, capabilities.Temperature)
        assert isinstance(oc, capabilities.Magnet)
        assert oc.get_temperature(1) == 1.5
        assert last(server) == ("getTemperature", [1])
        oc.set_magnet(0.1, 0.01)
        assert last(server) == (
            "setMagnet",
            {"field": 0.1, "rate": 0.01, "axis": "Z", "mode": "Persistent"},
        )
        assert oc.get_lhe_level() == 42.0


# -- Cryostation ---------------------------------------------------------------


def test_cryostation(server):
    with Cryostation(address=server.address) as cryo:
        assert isinstance(cryo, capabilities.Temperature)
        assert cryo.get_temperature(1) == 1.5
        assert last(server) == ("getTemperature", [1])
        assert cryo.get_temperature_target() == 2.0
        assert last(server) == ("getTemperatureTarget", [0])
        with pytest.raises(NotImplementedError, match="does not support set_temperature"):
            cryo.set_temperature(4.2, 1.0)


# -- Oxford magnets --------------------------------------------------------------


def test_oxford1820(server):
    with Oxford1820(address=server.address) as ox:
        assert isinstance(ox, capabilities.Magnet)
        assert ox.get_magnet() == 0.5
        assert last(server) == ("getMagnet", {})
        ox.set_magnet(0.5, 0.05)
        assert last(server) == (
            "setMagnet",
            {"field": 0.5, "rate": 0.05, "axis": "Z", "mode": "Persistent"},
        )


def test_oxford_vrm(server):
    with OxfordVRM(address=server.address) as ox:
        assert isinstance(ox, capabilities.Magnet)
        assert ox.get_magnet_target() == 1.0
        assert last(server) == ("getMagnetTarget", ["Z"])
        ox.set_field(0.3, rate=0.01)
        assert last(server) == (
            "setMagnet",
            {"field": 0.3, "rate": 0.01, "axis": "Z", "mode": "Persistent"},
        )


# -- Leiden TCs ------------------------------------------------------------------


@pytest.mark.parametrize("cls", [TC_CF, TC_MNK])
def test_leiden_tc(server, cls):
    with cls(address=server.address) as tc:
        assert isinstance(tc, capabilities.Temperature)
        assert tc.get_temperature(0) == 1.5
        assert last(server) == ("getTemperature", [0])
        assert tc.get_heater(1) == 0.001
        assert last(server) == ("getHeater", [1])
        with pytest.raises(NotImplementedError, match="passive cooling system"):
            tc.set_temperature(0.05)


# -- Aerotech (stub) --------------------------------------------------------------


def test_aerotech_is_unavailable():
    with pytest.raises(NotImplementedError, match="Driver not available"):
        Aerotech()
