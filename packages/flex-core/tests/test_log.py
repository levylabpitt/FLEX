import logging

from flex.log import add_file_log, enable_console, get_logger, is_interactive, remove_log_handler


def test_namespaced_loggers():
    assert get_logger().name == "flex"
    assert get_logger("inst.lockin").name == "flex.inst.lockin"


def test_root_logger_untouched():
    before = list(logging.getLogger().handlers)
    enable_console()
    assert logging.getLogger().handlers == before


def test_console_idempotent():
    h1 = enable_console()
    h2 = enable_console(logging.WARNING)
    assert h1 is h2
    assert h2.level == logging.WARNING


def test_console_defaults_quieter_when_interactive(monkeypatch):
    """Routine INFO chatter is fine in a terminal but clutters a notebook
    cell; interactive sessions default to WARNING unless a level is given
    explicitly."""
    import flex.log as log_module

    log_module._console_handler = None
    monkeypatch.setattr(log_module, "is_interactive", lambda: True)
    handler = enable_console()
    assert handler.level == logging.WARNING
    log_module._console_handler = None


def test_is_interactive_false_outside_ipython():
    assert is_interactive() is False


def test_file_log_roundtrip(tmp_path):
    logfile = tmp_path / "logs" / "exp.log"
    handler = add_file_log(logfile)
    get_logger("test").debug("hello file")
    remove_log_handler(handler)
    assert "hello file" in logfile.read_text(encoding="utf-8")
    # detached: further messages are not written
    get_logger("test").debug("after detach")
    assert "after detach" not in logfile.read_text(encoding="utf-8")
