import logging

from flex.log import add_file_log, enable_console, get_logger, remove_log_handler


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


def test_file_log_roundtrip(tmp_path):
    logfile = tmp_path / "logs" / "exp.log"
    handler = add_file_log(logfile)
    get_logger("test").debug("hello file")
    remove_log_handler(handler)
    assert "hello file" in logfile.read_text(encoding="utf-8")
    # detached: further messages are not written
    get_logger("test").debug("after detach")
    assert "after detach" not in logfile.read_text(encoding="utf-8")
