from flex.comms import COMMS, NoComms
from flex.ecosystem import FlexConfig


def test_no_comms_is_a_noop():
    comms = NoComms()
    assert comms.notify_start(experiment=None) is None
    comms.notify_end(experiment=None, state=None)  # must not raise
    comms.close()  # must not raise


def test_none_is_the_only_core_backend():
    assert COMMS == {"none": "flex.comms:NoComms"}


def test_build_comms_defaults_to_none():
    cfg = FlexConfig()
    assert isinstance(cfg.build_comms(), NoComms)


def test_build_comms_resolves_configured_backend():
    cfg = FlexConfig.model_validate({"comms": {"backend": "none"}})
    assert isinstance(cfg.build_comms(), NoComms)
