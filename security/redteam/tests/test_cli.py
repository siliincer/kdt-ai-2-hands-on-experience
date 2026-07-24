from __future__ import annotations

import security.redteam.runner.cli as cli


def test_legacy_cli_fails_closed_and_points_to_agent_v3(
    capsys,
) -> None:
    assert cli.main() == 2

    output = capsys.readouterr().out

    assert "legacy" in output
    assert "reference_cli" in output
    assert "Agent V3" in output
