from typing import NoReturn

from fastapi import HTTPException


def _err(status: int, code: str, msg: str) -> NoReturn:
    raise HTTPException(status_code=status, detail={"error_code": code, "message": msg})
