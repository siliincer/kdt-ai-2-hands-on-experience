import uuid
from datetime import datetime, timezone
from typing import NoReturn

from fastapi import HTTPException


def get_uuid() -> str:
    return str(uuid.uuid4())


def get_now() -> datetime:
    return datetime.now(timezone.utc)


def throw_err(status: int, code: str, msg: str) -> NoReturn:
    raise HTTPException(status_code=status, detail={"error_code": code, "message": msg})
