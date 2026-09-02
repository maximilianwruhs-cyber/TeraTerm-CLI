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
    # Multi-word header must not become a command
    assert "Available" not in sends
    assert "commands" not in sends


def test_extract_at_plus_and_header():
    raw = "Commands: AT+RST AT+GMR\nAT+CSQ - signal quality\n"
    cmds = extract_commands(raw, productive_nudges=[])
    sends = [c.send for c in cmds]
    assert "AT+RST" in sends
    assert "AT+GMR" in sends
    assert "AT+CSQ" in sends
    assert "Commands" not in sends
    by_send = {c.send: c for c in cmds}
    assert by_send["AT+CSQ"].summary == "signal quality"
    assert by_send["AT+CSQ"].source == "parsed_help"
    assert by_send["AT+GMR"].id == "at_gmr"


def test_extract_bullet_line():
    raw = "- reset - reboot board\n* status: show status\n"
    cmds = extract_commands(raw, productive_nudges=[])
    sends = [c.send for c in cmds]
    assert "reset" in sends
    assert "status" in sends


def test_id_collision_suffix():
    # Two different sends that slug to the same base id
    raw = "AT+GMR - modem rev\nat gmr - spaced variant\n"
    # spaced variant won't parse as one token; force collision via nudges + parse
    cmds = extract_commands("AT+GMR - modem rev\n", productive_nudges=["at/gmr"])
    ids = [c.id for c in cmds]
    assert "at_gmr" in ids
    assert "at_gmr_2" in ids
    assert len(ids) == len(set(ids))


def test_extract_rejects_prose_stopwords():
    raw = (
        "Usage: help [command]\n"
        "Error: unknown command\n"
        "Commands\n"
        "Available: list\n"
        "reset - reboot board\n"
    )
    cmds = extract_commands(raw, productive_nudges=[])
    sends = [c.send for c in cmds]
    assert "Usage" not in sends
    assert "Error" not in sends
    assert "Commands" not in sends
    assert "Available" not in sends
    assert "reset" in sends
