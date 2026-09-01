from tt_agent_hw.scoring import SILENCE_FLOOR, STRONG_SCORE, score_rx


def test_empty_is_zero():
    assert score_rx(b"") == 0.0


def test_help_text_scores_high():
    s = score_rx(b"Available commands:\r\nhelp - show help\r\nOK>\r\n")
    assert s >= STRONG_SCORE


def test_binary_noise_low():
    s = score_rx(bytes(range(256)) * 2)
    assert s < SILENCE_FLOOR or s < 0.3
