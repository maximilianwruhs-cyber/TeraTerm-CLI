from dataclasses import replace

import pytest

from tt_agent_hw.models import BaudAttempt, DeviceProfile, DiscoveredCommand
from tt_agent_hw.profile_store import load_profile, save_profile


@pytest.fixture
def sample_profile() -> DeviceProfile:
    return DeviceProfile(
        schema_version=1,
        com=7,
        port_name="COM7",
        baud=9600,
        framing={"bytesize": 8, "parity": "N", "stopbits": 1},
        usb_hint={"friendly_name": "USB Serial Port (COM7)"},
        fingerprint={
            "banner": "hi",
            "help_raw_path": "artifacts/help_raw.txt",
            "help_raw_sha256": "",
        },
        commands=[
            DiscoveredCommand(id="help", send="help", summary="nudge", source="nudge")
        ],
        nudges_tried=["cr", "help"],
        baud_tried=[BaudAttempt(baud=9600, bytes_rx=10, score=0.8)],
        confidence=0.8,
        discovered_at="2026-09-01T00:00:00Z",
        run_id="run_abc",
        tool_version="0.2.0",
    )


def test_save_profile_backs_up_previous(tmp_path, sample_profile):
    path = save_profile(tmp_path, sample_profile)
    assert path.name == "COM7.json"
    p2 = replace(sample_profile, baud=115200, confidence=0.9)
    save_profile(tmp_path, p2)
    assert (tmp_path / "profiles" / "COM7.prev.json").is_file()
    loaded = load_profile(tmp_path, 7)
    assert loaded.baud == 115200
