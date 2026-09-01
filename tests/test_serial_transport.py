from tt_agent_hw.serial_transport import FakeSerialTransport


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
