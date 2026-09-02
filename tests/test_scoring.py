from tt_agent_hw.scoring import SILENCE_FLOOR, STRONG_SCORE, console_evidence, score_rx


def test_empty_is_zero():
    assert score_rx(b"") == 0.0


def test_help_text_scores_high():
    s = score_rx(b"Available commands:\r\nhelp - show help\r\nOK>\r\n")
    assert s >= STRONG_SCORE


def test_binary_noise_low():
    s = score_rx(bytes(range(256)) * 2)
    assert s < SILENCE_FLOOR or s < 0.3


def test_console_evidence_requires_markers():
    assert console_evidence(b"") is False
    assert console_evidence(b"A" * 64) is False
    assert console_evidence(b"Available commands:\r\nhelp\r\n") is True
    assert console_evidence(b"ready>\r\n") is True
