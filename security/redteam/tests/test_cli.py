from security.redteam.models import Verdict
from security.redteam.runner.cli import EXIT_CODES


def test_exit_codes_distinguish_security_failure_from_execution_error():
    assert EXIT_CODES == {
        Verdict.PASS: 0,
        Verdict.FAIL: 1,
        Verdict.ERROR: 2,
    }
