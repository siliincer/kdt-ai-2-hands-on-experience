from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["argon2"],  # 해싱 알고리즘
    deprecated="auto",  # 오래된 알고리즘 자동 사용 중단
)


def get_password_hash(password: str) -> str:
    """
    사용자가 입력한 평문 비밀번호를 Argon2 알고리즘으로 해싱합니다.
    회원가입 시 호출하여 DB에 결과값을 저장합니다.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    사용자가 입력한 평문 비밀번호와 DB에 저장된 해시값을 비교합니다.
    로그인 시 호출하여 인증 여부를 판단합니다.
    """
    return pwd_context.verify(plain_password, hashed_password)
