from pathlib import Path

from tt_agent_hw.ports import PortInfo, list_ports, parse_com_number, resolve_default_com


def test_parse_com_number():
    assert parse_com_number("COM7") == 7
    assert parse_com_number("com12") == 12
    assert parse_com_number("not") is None


def test_list_ports_marks_profile(tmp_path: Path):
    prof = tmp_path / "profiles"
    prof.mkdir()
    (prof / "COM7.json").write_text("{}", encoding="utf-8")

    class Fake:
        device = "COM7"
        description = "USB Serial Port"
        hwid = "FTDIBUS\\VID_0403"

    ports = list_ports(runtime_dir=tmp_path, enumerator=lambda: [Fake()])
    assert ports[0].com == 7
    assert ports[0].has_profile is True


def test_resolve_default_com_single_usb():
    ports = [
        PortInfo("COM3", 3, "Standard Serial over Bluetooth link", "BTHENUM\\x", False),
        PortInfo("COM7", 7, "USB Serial Port", "FTDIBUS\\x", False),
    ]
    assert resolve_default_com(ports) == 7
