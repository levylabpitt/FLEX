import pytest

from flex_protocols import ZMQInstrument, ZMQInstrumentError
from flex_protocols.testing import FakeIFServer


@pytest.fixture
def server():
    with FakeIFServer(
        {
            "getResults": {"X": [1.0, 2.0]},
            "setAO_DC": lambda params: params,
            "explode": lambda params: (_ for _ in ()).throw(RuntimeError("hardware fault")),
        }
    ) as s:
        yield s


def test_call_roundtrip(server):
    with ZMQInstrument("dev", server.address) as inst:
        assert inst.call("getResults") == {"X": [1.0, 2.0]}
        assert inst.call("setAO_DC", {"Channel": 1, "DC": 0.5}) == {"Channel": 1, "DC": 0.5}

    methods = [r["method"] for r in server.requests]
    assert methods == ["ACK", "getResults", "setAO_DC"]
    ids = [r["id"] for r in server.requests]
    assert len(set(ids)) == len(ids)  # unique request ids


def test_idn_and_help(server):
    with ZMQInstrument("dev", server.address) as inst:
        idn = inst.idn()
        assert idn["model"] == "FakeIF"
        assert idn["serial"] == "0000"
        assert "getResults" in inst.help()


def test_error_response_raises(server):
    with ZMQInstrument("dev", server.address) as inst:
        with pytest.raises(ZMQInstrumentError, match="hardware fault"):
            inst.call("explode")
        with pytest.raises(ZMQInstrumentError, match="Unknown method"):
            inst.call("noSuchMethod")
        # errors leave the connection usable
        assert inst.call("getResults") == {"X": [1.0, 2.0]}


def test_timeout_then_recovery(server):
    """The v1 REQ socket deadlocked after one timeout; v2 must recover."""
    with ZMQInstrument("dev", server.address, timeout=0.2) as inst:
        server.delay = 1.0
        with pytest.raises(TimeoutError, match="did not answer"):
            inst.call("getResults")
        server.delay = 0.0
        # the late reply from the timed-out request must not confuse the next call
        assert inst.call("getResults", timeout=3.0) == {"X": [1.0, 2.0]}


def test_connect_check_fails_fast():
    with pytest.raises(TimeoutError):
        ZMQInstrument("dev", "tcp://127.0.0.1:9", timeout=0.2)  # nothing listening


def test_no_connect_check():
    inst = ZMQInstrument("dev", "tcp://127.0.0.1:9", timeout=0.2, connect_check=False)
    inst.close()
