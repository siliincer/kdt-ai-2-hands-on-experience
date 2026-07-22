"""
scripts폴더에서 공통적으로 쓰이는 헬퍼 함수, 상수 모음
"""

BACKEND = "http://localhost:8000"
AGENT = "http://localhost:8001"
FINANCIAL = "http://localhost:8002"


def _ok(msg: str) -> None:
    print(f"  \033[32mPASS\033[0m {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[31mFAIL\033[0m {msg}")


def _info(msg: str) -> None:
    print(f"  ...  {msg}")


def _as_str(x: str | bytes) -> str:
    """redis 응답이 bytes/str 어느 쪽이든 str 로 통일한다."""
    return x.decode() if isinstance(x, bytes) else x
