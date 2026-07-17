"""mock-financial-service(계정계/정보계) 연동 계층.

financial_client: HTTP I/O 경계(뷰 모델을 모른다).
ui_service 가 이 계층을 통해 계정계 데이터를 조회하고 UI 뷰로 조립한다.
"""

from ...core.load_environment_var import settings
from .financial_client import (
    FinancialServiceClient,
    FinancialServiceError,
    close_financial_client,
    financial_service_error_handler,
    get_financial_client,
)


def is_financial_http_mode() -> bool:
    """계정계 데이터 소스가 http(실서비스)인지. 아니면 mock(내장 픽스처).

    여러 서비스에 흩어져 있던 `_use_http` 를 하나로 모은다.
    """
    return settings.FINANCIAL_CLIENT.strip().lower() == "http"


__all__ = [
    "FinancialServiceClient",
    "FinancialServiceError",
    "close_financial_client",
    "financial_service_error_handler",
    "get_financial_client",
    "is_financial_http_mode",
]
