"""Cooldown tests: fake PPMS and lock-in, so the ramp, the limits and the abort warning run without hardware."""

import itertools
import json
import types

import pytest

from flex.instrument import SimulatedInstrument
from flex_exp import cooldown as cd


class FakePPMS(SimulatedInstrument):
    def __init__(self, temperature=300.0):
        super().__init__("ppms")
        self.temperature, self.target, self.sets = temperature, temperature, []

    def set_temperature(self, setpoint, rate=None):
        self.target = setpoint
        self.sets.append((setpoint, rate))

    def get_temperature(self, channel=0):
        return self.temperature

    def get_temperature_status(self, channel=0):  # each reading moves the ramp on, 40 K at a time
        gap = self.target - self.temperature
        self.temperature += max(-40.0, min(40.0, gap))
        return {"temperature": self.temperature, "status": "Stable" if self.temperature == self.target else "Tracking"}


class FakeLockin(SimulatedInstrument):
    def __init__(self, fail_after=None):
        super().__init__("lockin")
        self.calls, self.amplitude, self.reads, self.fail_after = [], None, 0, fail_after

    def set_ao_function(self, channel, value):
        self.calls.append(("function", channel, value))

    def set_ao_frequency(self, channel, value):
        self.calls.append(("frequency", channel, value))

    def set_ao_amplitude(self, channel, value):
        self.amplitude = value
        self.calls.append(("amplitude", channel, value))

    def get_state(self):
        return "idle"

    def set_state(self, value):
        self.calls.append(("state", value))

    def get_lockin_results(self, channel, params=("X", "Y")):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            raise KeyboardInterrupt  # what an abort looks like inside the script
        return {"X": {1: 2.0, 2: 5.0, 3: 0.0}[channel], "Y": 0.1}


@pytest.fixture(autouse=True)
def quick(tmp_path, monkeypatch):
    (tmp_path / "flex.toml").write_text(f'[data]\nroot = "{tmp_path.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setenv("FLEX_CONFIG", str(tmp_path / "flex.toml"))
    monkeypatch.setattr(cd, "SETTLE", 0.0)


def station(temperature=300.0, **lockin):
    return types.SimpleNamespace(ppms=FakePPMS(temperature), lockin=FakeLockin(**lockin))


def data(capsys):
    return [json.loads(line[5:]) for line in capsys.readouterr().out.splitlines() if line.startswith("DATA ")]


def test_ramps_to_the_target_and_logs_the_channel_ratio(capsys):
    s = station()
    result = cd.cooldown(s, numerator=2, denominator=1, target=100.0, rate=2.0, interval=0.2, sample="S1")
    assert s.ppms.sets == [(100.0, 2.0)]
    rows = data(capsys)
    assert [r["T"] for r in rows] == [260.0, 220.0, 180.0, 140.0, 100.0]
    assert all(r["G"] == 2.5 for r in rows)  # X(ch 2) / X(ch 1) = 5 / 2
    assert result["points"] == 5 and result["T"] == 100.0 and result["G"] == 2.5
    assert s.lockin.amplitude == 0  # the excitation is switched off afterwards
    assert ("amplitude", 1, 0.01) in s.lockin.calls and ("state", "start") in s.lockin.calls


def test_a_zero_denominator_leaves_the_ratio_empty(capsys):
    cd.cooldown(station(), numerator=1, denominator=3, target=250.0, rate=2.0, interval=0.2)
    assert [r["G"] for r in data(capsys)] == [None, None]


@pytest.mark.parametrize("params, message", [
    (dict(target=1.0, rate=2.0), "Target 1 is outside"),
    (dict(target=100.0, rate=50.0), "Rate 50 is outside"),
    (dict(target=100.0, rate=2.0, amplitude=1.0), "Amplitude 1 V must be above 0"),
    (dict(target=100.0, rate=2.0, amplitude=0.0), "Amplitude 0 V must be above 0"),
    (dict(target=100.0, rate=2.0, interval=0.01), "at least"),
    (dict(target=300.0, rate=2.0), "below the current temperature"),
    (dict(target=100.0, rate=2.0, denominator=2), "different channels"),
])
def test_unsafe_requests_are_refused_before_anything_moves(params, message):
    s = station()
    with pytest.raises(ValueError, match=message):
        cd.cooldown(s, **{"numerator": 2, "denominator": 1, **params})
    assert s.ppms.sets == [] and s.lockin.calls == []


def test_a_stopped_run_switches_the_excitation_off_and_warns_the_ppms_still_ramps(capsys):
    s = station(fail_after=4)  # two readings of two channels, then the abort
    with pytest.raises(KeyboardInterrupt):
        cd.cooldown(s, numerator=2, denominator=1, target=100.0, rate=2.0, interval=0.2)
    assert s.lockin.amplitude == 0
    out = capsys.readouterr().out
    assert "WARNING: stopped before reaching 100 K. The PPMS is still ramping to 100 K at 2 K/min" in out


def test_a_ramp_that_never_arrives_times_out_with_the_warning(capsys, monkeypatch):
    s = station()
    s.ppms.get_temperature_status = lambda channel=0: {"temperature": 250.0, "status": "Tracking"}
    clock = itertools.count(0, 400)  # every look at the clock is 400 s later, so the limit passes quickly
    monkeypatch.setattr(cd.time, "monotonic", lambda: float(next(clock)))
    with pytest.raises(TimeoutError, match="did not reach 100 K"):
        cd.cooldown(s, numerator=2, denominator=1, target=100.0, rate=2.0, interval=0.2)
    assert "WARNING: stopped before reaching 100 K" in capsys.readouterr().out
