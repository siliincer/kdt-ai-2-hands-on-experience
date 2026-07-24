from __future__ import annotations

import security.redteam.runner.compare as compare


def test_legacy_comparison_fails_closed_and_points_to_agent_v3(
    capsys,
) -> None:
    assert compare.main() == 2

    output = capsys.readouterr().out

    assert "legacy" in output
    assert "reference_cli" in output
    assert "Agent V3" in output
