from tt_agent_hw.commands_extract import extract_commands, slug_id


def test_slug_id():
    assert slug_id("AT+GMR") == "at_gmr"
    assert slug_id("help") == "help"


def test_extract_nudge_and_parsed():
    raw = "Available commands:\nreset - reboot board\nstatus: show status\n"
    cmds = extract_commands(raw, productive_nudges=["help", "?"])
    sends = [c.send for c in cmds]
    assert "help" in sends
    assert "?" in sends
    assert "reset" in sends
    assert "status" in sends
    assert all(c.id for c in cmds)
