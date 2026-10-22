"""FastAPI Application Entrypoint, Middleware, and Health Probes."""

import uuid
from typing import Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.app.api.v1.api import api_router
from backend.app.core.config import settings
from backend.app.db.session import engine

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    """Assigns unique X-Request-ID to each incoming request."""
    request_id = request.headers.get("X-Request-ID", f"req_{uuid.uuid4().hex[:12]}")
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Uniform JSON error formatting for HTTPExceptions."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.detail if isinstance(exc.detail, str) and "_" in exc.detail else "HTTP_ERROR",
                "message": str(exc.detail),
                "details": None,
                "request_id": request_id,
            },
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Uniform JSON error formatting for schema validation failures (422)."""
    request_id = getattr(request.state, "request_id", None)
    details = []
    for error in exc.errors():
        field_loc = " -> ".join(str(loc) for loc in error.get("loc", []))
        details.append({
            "field": field_loc,
            "issue": error.get("msg", "Invalid input value"),
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "One or more input fields failed validation constraints",
                "details": details,
                "request_id": request_id,
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler preventing internal stack trace leaks (500)."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing the request",
                "details": None,
                "request_id": request_id,
            },
        },
    )


# Health Probes
@app.get("/health", tags=["system"])
def health_liveness():
    """Liveness probe confirming API service responsiveness."""
    return {"status": "ok", "project": settings.PROJECT_NAME}


@app.get("/health/ready", tags=["system"])
def health_readiness():
    """Readiness probe validating database engine connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": str(e)},
        )


# API Routers
app.include_router(api_router, prefix=settings.API_V1_STR)

# Serve Frontend Production Build if compiled
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dist, "index.html"))

    @app.get("/scanner")
    async def serve_scanner():
        scanner_html = os.path.join(os.path.dirname(__file__), "../../frontend/public/scanner.html")
        if os.path.exists(scanner_html):
            return FileResponse(scanner_html)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

