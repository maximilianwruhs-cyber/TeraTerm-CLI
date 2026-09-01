import pytest

from tt_agent_hw.serial_transport import FakeSerialTransport, PyserialTransport


def test_fake_returns_scripted_rx_for_help():
    fake = FakeSerialTransport(
        port="COM7",
        baud=9600,
        script={
            9600: [
                (b"help", b"Available commands:\r\nhelp - show help\r\n"),
            ]
        },
    )
    fake.open()
    fake.write(b"help\r")
    rx = fake.read(4096)
    assert b"Available commands" in rx
    fake.close()


def test_pyserial_open_rejects_unsupported_parity():
    transport = PyserialTransport(port="COM7", baud=9600, parity="X")
    with pytest.raises(ValueError, match="unsupported parity"):
        transport.open()
