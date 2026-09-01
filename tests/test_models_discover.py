from tt_agent_hw.models import BaudAttempt, DeviceProfile, DiscoveredCommand


def test_device_profile_roundtrip():
    p = DeviceProfile(
        schema_version=1,
        com=7,
        port_name="COM7",
        baud=9600,
        framing={"bytesize": 8, "parity": "N", "stopbits": 1},
        usb_hint={"friendly_name": "USB Serial Port (COM7)"},
        fingerprint={"banner": "hi", "help_raw_path": "artifacts/help_raw.txt", "help_raw_sha256": ""},
        commands=[DiscoveredCommand(id="help", send="help", summary="nudge", source="nudge")],
        nudges_tried=["cr", "help"],
        baud_tried=[BaudAttempt(baud=9600, bytes_rx=10, score=0.8)],
        confidence=0.8,
        discovered_at="2026-09-01T00:00:00Z",
        run_id="run_abc",
        tool_version="0.2.0",
    )
    data = p.to_dict()
    p2 = DeviceProfile.from_dict(data)
    assert p2.com == 7
    assert p2.commands[0].id == "help"
    assert p2.baud_tried[0].baud == 9600
