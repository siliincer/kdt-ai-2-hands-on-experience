#!/usr/bin/env python
"""EOD 마감 배치 CLI — OS cron이 자정에 이 스크립트를 호출하는 것으로
실제 스케줄러를 대체 시뮬레이션한다.

사용 (crontab -e 예시, 매일 자정 실행):
    0 0 * * * cd /path/to/mock-financial-service && \
      .venv/bin/python scripts/run_daily_close.py >> logs/daily_close.log 2>&1

같은 영업일에 여러 번 실행해도 안전(idempotent) — 이미 마감된 계좌는 스킵.
"""

import sys
from datetime import date

sys.path.insert(0, "src")

from financial_service.crud import run_daily_closing  # noqa: E402
from financial_service.database import SessionLocal  # noqa: E402


def main() -> int:
    business_date: date | None = None
    if len(sys.argv) > 1:
        business_date = date.fromisoformat(sys.argv[1])  # backfill: YYYY-MM-DD

    db = SessionLocal()
    try:
        resolved_date, snapshots = run_daily_closing(db, business_date)
    finally:
        db.close()

    print(
        f"[daily-close] business_date={resolved_date} "
        f"accounts_closed={len(snapshots)}"
    )
    for row in snapshots:
        print(
            f"  account_id={row.account_id} closing_balance={row.closing_balance} "
            f"sum_credit={row.sum_credit} sum_debit={row.sum_debit}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
