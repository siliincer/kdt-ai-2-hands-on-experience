"""Mock 은행 데이터.

DB 도입 전 단계라 Python dict/list로만 계좌·감사로그를 보관한다.
tool은 이 모듈을 직접 import하지 않고 BankClient(agent/src/agent/bank_client.py)를
경유한다. 추후 실제 원장 연동 시 클라이언트 구현만 교체하면 된다.
"""

from datetime import date, timedelta


def _rel_date(days_ago: int) -> str:
    """오늘 기준 N일 전 날짜(ISO). 프로세스 시작 시점 기준으로 고정된다."""
    return (date.today() - timedelta(days=days_ago)).isoformat()


# user_id -> 계좌 목록
MOCK_ACCOUNTS = {
    "user_001": [
        {
            "account_id": "acc_001",
            "account_name": "입출금통장",
            "balance": 1250000,
            "currency": "KRW",
            "is_default": True,
            "alias": None,
        },
        {
            "account_id": "acc_002",
            "account_name": "생활비통장",
            "balance": 430000,
            "currency": "KRW",
            "is_default": False,
            "alias": None,
        },
    ]
}

# user_id -> 송금 수취인 목록
# last_transfer_at: 마지막 송금 일시. None이면 송금 이력이 없는 신규 수취인으로,
# new_recipient_warning 가드레일 규칙의 recipient_is_new 신호가 된다.
MOCK_RECIPIENTS = {
    "user_001": [
        {
            "recipient_id": "rec_001",
            "name": "김철수",
            "bank": "국민은행",
            "account_number": "123-456-789012",
            "last_transfer_at": "2026-06-15T10:30:00",
        },
        {
            "recipient_id": "rec_002",
            "name": "이영희",
            "bank": "신한은행",
            "account_number": "110-123-456789",
            "last_transfer_at": None,
        },
    ]
}

# user_id -> 거래내역 목록. date는 프로세스 시작 시점 기준 상대 계산이라
# "이번 달"/"지난달" 등 상대 기간 조회가 언제 돌려도 항상 일치한다.
MOCK_TRANSACTIONS = {
    "user_001": [
        {
            "transaction_id": "txn_h001",
            "account_id": "acc_001",
            "date": _rel_date(2),
            "type": "spending",
            "amount": 5000,
            "merchant": "스타벅스",
        },
        {
            "transaction_id": "txn_h002",
            "account_id": "acc_001",
            "date": _rel_date(5),
            "type": "spending",
            "amount": 32000,
            "merchant": "이마트",
        },
        {
            "transaction_id": "txn_h003",
            "account_id": "acc_002",
            "date": _rel_date(3),
            "type": "spending",
            "amount": 12000,
            "merchant": "스타벅스",
        },
        {
            "transaction_id": "txn_h004",
            "account_id": "acc_002",
            "date": _rel_date(10),
            "type": "income",
            "amount": 2500000,
            "merchant": "급여",
        },
        {
            "transaction_id": "txn_h005",
            "account_id": "acc_001",
            "date": _rel_date(35),
            "type": "spending",
            "amount": 45000,
            "merchant": "올리브영",
        },
        {
            "transaction_id": "txn_h006",
            "account_id": "acc_002",
            "date": _rel_date(40),
            "type": "spending",
            "amount": 8000,
            "merchant": "택시",
        },
    ]
}

# write_audit_log Tool이 기록을 쌓는 인메모리 감사 로그
AUDIT_LOG: list = []
