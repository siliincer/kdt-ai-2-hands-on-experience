_ANALYTICS_PREFIX = "/api/v1/analytics"
# 계정계(owner-side) 쓰기 경로. 읽기=정보계, 쓰기=계정계(결정 C).
_ACCOUNTS_PATH = "/api/v1/accounts"
_TRANSFERS_PATH = "/api/v1/transfers"

# fake-money sandbox: 신규 계좌 데모 시드 잔액.
_SIGNUP_SEED_BALANCE = 1_000_000

# 계좌 추가(/add_account)에서 허용하는 은행명. FE 은행 선택지(shared/constants/banks.ts)와
# 동일하게 유지한다 — UI 에 없는 은행이 데이터로 들어가는 불일치를 막는다.
SUPPORTED_BANK_NAMES: tuple[str, ...] = (
    "KDT은행",
    "카카오뱅크",
    "토스뱅크",
    "케이뱅크",
    "신한은행",
    "국민은행",
    "하나은행",
    "우리은행",
    "농협은행",
    "SC제일은행",
)
