"""Mock 은행 데이터.

DB 도입 전 단계라 Python dict/list로만 계좌·감사로그를 보관한다.
tool은 이 모듈을 직접 import하지 않고 BankClient(agent/src/agent/bank_client.py)를
경유한다. 추후 실제 원장 연동 시 클라이언트 구현만 교체하면 된다.
"""

# user_id -> 계좌 목록
MOCK_ACCOUNTS = {
    "user_001": [
        {
            "account_id": "acc_001",
            "account_name": "입출금통장",
            "balance": 1250000,
            "currency": "KRW",
            "is_default": True,
        },
        {
            "account_id": "acc_002",
            "account_name": "생활비통장",
            "balance": 430000,
            "currency": "KRW",
            "is_default": False,
        },
    ]
}

# user_id -> 송금 수취인 목록
MOCK_RECIPIENTS = {
    "user_001": [
        {
            "recipient_id": "rec_001",
            "name": "김철수",
            "bank": "국민은행",
            "account_number": "123-456-789012",
        },
        {
            "recipient_id": "rec_002",
            "name": "이영희",
            "bank": "신한은행",
            "account_number": "110-123-456789",
        },
    ]
}

# write_audit_log Tool이 기록을 쌓는 인메모리 감사 로그
AUDIT_LOG: list = []
