"""mock-financial-service(계정계/정보계) 연동 계층.

financial_client: HTTP I/O 경계(뷰 모델을 모른다).
ui_service 가 이 계층을 통해 계정계 데이터를 조회하고 UI 뷰로 조립한다.
"""

from .financial_client import (
    FinancialServiceClient,
    FinancialServiceError,
    close_financial_client,
    financial_service_error_handler,
    get_financial_client,
)

# 계정계는 항상 http(실서비스)로 연동한다(mock 일원화, 작업 B). 과거의
# is_financial_http_mode()/mock 분기는 제거됐다.

__all__ = [
    "FinancialServiceClient",
    "FinancialServiceError",
    "close_financial_client",
    "financial_service_error_handler",
    "get_financial_client",
]
