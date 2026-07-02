"""Test exception handlers to verify they return correct response format."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.core.exceptions import exception_handlers


@pytest.fixture
def app():
    """Create a test FastAPI app with exception handlers."""
    app = FastAPI()

    # Register all exception handlers
    for exc_class, handler in exception_handlers.items():
        app.add_exception_handler(exc_class, handler)

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestValueErrorHandler:
    """Test ValueError exception handler."""

    def test_value_error_response(self, app, client):
        """Test ValueError returns BAD_REQUEST (400) with correct code."""

        @app.get("/value-error")
        def raise_value_error():
            raise ValueError("Invalid input")

        response = client.get("/value-error")

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "BAD_REQUEST"
        assert "잘못된 입력값입니다" in data["error"]["message"]
        assert "Invalid input" in data["error"]["message"]


class TestRuntimeErrorHandler:
    """Test RuntimeError exception handler."""

    def test_runtime_error_response(self, app, client):
        """Test RuntimeError returns RUNTIME_ERROR (500) with correct message."""

        @app.get("/runtime-error")
        def raise_runtime_error():
            raise RuntimeError("Something went wrong")

        response = client.get("/runtime-error")

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "RUNTIME_ERROR"
        assert data["error"]["message"] == "서버 오류가 발생했습니다."


class TestHTTPExceptionHandler:
    """Test HTTPException exception handler."""

    def test_http_exception_404(self, app, client):
        """Test HTTPException with 404 status."""

        @app.get("/not-found")
        def raise_not_found():
            raise HTTPException(status_code=404, detail="Resource not found")

        response = client.get("/not-found")

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "HTTP_ERROR"
        assert data["error"]["message"] == "Resource not found"

    def test_http_exception_403(self, app, client):
        """Test HTTPException with 403 status."""

        @app.get("/forbidden")
        def raise_forbidden():
            raise HTTPException(status_code=403, detail="Access denied")

        response = client.get("/forbidden")

        assert response.status_code == 403
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "HTTP_ERROR"
        assert data["error"]["message"] == "Access denied"

    def test_http_exception_500(self, app, client):
        """Test HTTPException with 500 status."""

        @app.get("/server-error")
        def raise_server_error():
            raise HTTPException(status_code=500, detail="Internal server error")

        response = client.get("/server-error")

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "HTTP_ERROR"
        assert data["error"]["message"] == "Internal server error"


class TestRequestValidationErrorHandler:
    """Test RequestValidationError exception handler."""

    def test_request_validation_error(self, app, client):
        """Test RequestValidationError returns 422 with validation details."""
        from pydantic import BaseModel

        class InputModel(BaseModel):
            name: str
            age: int

        @app.post("/validate-request")
        def validate_request(data: InputModel):
            return {"message": "OK"}

        # Send invalid data (age should be int, not string)
        response = client.post(
            "/validate-request", json={"name": "John", "age": "invalid"}
        )

        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "REQUEST_VALIDATION_ERROR"
        assert data["error"]["message"] == "요청 형식이 올바르지 않습니다."
        assert "details" in data["error"]
        assert len(data["error"]["details"]) > 0


class TestResponseValidationErrorHandler:
    """Test ResponseValidationError exception handler."""

    def test_response_validation_error(self, app, client):
        """Test ResponseValidationError returns 500 with correct code."""
        from pydantic import BaseModel

        class OutputModel(BaseModel):
            message: str
            count: int

        @app.get("/validate-response", response_model=OutputModel)
        def validate_response():
            # Return data that doesn't match the response model
            return {"message": "OK", "count": "invalid"}  # count should be int

        response = client.get("/validate-response")

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "RESPONSE_VALIDATION_ERROR"
        assert (
            data["error"]["message"]
            == "서버 응답 형식이 API 스키마와 일치하지 않습니다."
        )
        assert "details" in data["error"]


class TestExceptionResponseStructure:
    """Test the structure of error responses."""

    def test_error_response_has_required_fields(self, app, client):
        """Test that error response always has required fields."""

        @app.get("/test-error")
        def test_error():
            raise ValueError("Test")

        response = client.get("/test-error")
        data = response.json()

        assert "success" in data
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_validation_error_has_details(self, app, client):
        """Test that validation errors include details."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            field: str

        @app.post("/test-validation")
        def test_validation(data: TestModel):
            return {"status": "ok"}

        response = client.post("/test-validation", json={"field": 123})
        data = response.json()

        assert "details" in data["error"]
        assert isinstance(data["error"]["details"], list)
