import socket
import threading

import pytest

from flex_protocols import TCPInstrument


@pytest.fixture
def echo_server():
    """A one-connection TCP server that answers *IDN? and echoes otherwise."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve():
        conn, _ = server.accept()
        with conn:
            buffer = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line == b"*IDN?":
                        conn.sendall(b"FLEX,fake-tcp,001,1.0\n")
                    else:
                        conn.sendall(line + b"\n")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield port
    server.close()


def test_query_and_idn(echo_server):
    with TCPInstrument("fake", "127.0.0.1", echo_server) as inst:
        assert inst.query("hello") == "hello"
        assert inst.idn() == {"vendor": None, "model": "TCPInstrument", "serial": None, "firmware": None}
        assert inst.address == f"tcp://127.0.0.1:{echo_server}"


def test_parameters_over_tcp(echo_server):
    with TCPInstrument("fake", "127.0.0.1", echo_server) as inst:
        echo = inst.add_parameter("echo", get_cmd="21.5", get_parser=float)
        assert echo() == 21.5


def test_connection_refused():
    with pytest.raises(OSError):
        TCPInstrument("nope", "127.0.0.1", 1)  # port 1: nothing listening
