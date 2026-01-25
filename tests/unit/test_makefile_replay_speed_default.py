from __future__ import annotations

import re
from pathlib import Path


def _extract_replay_target_block(makefile_text: str) -> str:
    """
    Return the Makefile block from 'replay:' up to (but not including) the next
    top-level target.
    """
    # Match from a line starting with "replay:" until the next line that looks
    # like another top-level make target ("foo:"), or end-of-file.
    match = re.search(
        r"(?ms)^[ \t]*replay:\n(?P<body>.*?)(?=^[A-Za-z0-9_.-]+:\s*\n|\Z)",
        makefile_text,
    )
    assert match is not None, "Expected to find a 'replay:' target in Makefile"
    return "replay:\n" + match.group("body")


def test_replay_speed_message_matches_default_speed_flag() -> None:
    """
    Regression test:

    - When SPEED is empty, replay uses --speed 120 (default), so the message
      must NOT claim TURBO.
    - TURBO messaging must only be for explicit SPEED=0.
    """
    makefile_text = Path("Makefile").read_text(encoding="utf-8")
    replay_block = _extract_replay_target_block(makefile_text)

    # Default speed used when SPEED is empty.
    assert "--speed 120" in replay_block

    # Message must explicitly describe default as 120x (and not TURBO).
    assert 'echo "  Speed: DEFAULT (120x)"' in replay_block

    # TURBO message must exist, but must not be triggered by empty SPEED.
    assert 'echo "  Speed: TURBO (no delays, maximum speed)"' in replay_block
    assert '[ -z "$(SPEED)" ] || [ "$(SPEED)" = "0" ]' not in replay_block
