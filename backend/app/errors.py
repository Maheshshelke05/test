import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Standard error: {"error": {code, message, fields, request_id}}."""

    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


def not_found(what: str = "Resource") -> ApiError:
    # Used for both "missing" and "not in your scope" so we never leak existence.
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def forbidden(message: str = "You do not have permission for this action") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def _body(request: Request, code: str, message: str, fields: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "fields": fields or {},
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(_body(request, exc.code, exc.message, exc.fields), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = {".".join(str(p) for p in e["loc"][1:]) or "body": e["msg"] for e in exc.errors()}
        return JSONResponse(_body(request, "VALIDATION_ERROR", "Invalid request", fields), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(_body(request, "HTTP_ERROR", str(exc.detail)), status_code=exc.status_code)
