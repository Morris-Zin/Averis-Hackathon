"""Composition root, transport limits and same-origin static application."""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from averis.config import Settings
from averis.http_context import (
    COOKIE,
    ApplicationServices,
    get_services,
    identity,
    mutation,
)
from averis.persistence import Database
from averis.processing import Processor
from averis.routes import router
from averis.storage import Storage
from averis.workflow import Conflict, Workflow

__all__ = ["COOKIE", "app", "create_app"]


class _PayloadTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(413, "Request exceeds transport size limit")


class _RequestLimit:
    """Bound incoming bodies before parsing or attachment spooling."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        upload = path in {"/api/imports", "/api/manual-imports"} or path.endswith(
            "/revisions"
        )
        limit = 21 * 1024 * 1024 if upload else 256 * 1024
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise _PayloadTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLarge:
            await JSONResponse(
                status_code=413,
                content={"detail": "Request exceeds transport size limit"},
            )(scope, receive, send)


async def security_headers(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    config = get_services(request).config
    public_import = request.url.path == "/api/manual-imports"
    if (
        public_import
        or request.url.path == "/api/imports"
        or request.url.path.endswith("/revisions")
    ):
        if not public_import and (
            not config.operator_token
            or not secrets.compare_digest(
                request.headers.get("x-operator-token", ""), config.operator_token
            )
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Uploads require operator authorization"},
            )
        try:
            actor = identity(request)
            mutation(request, actor)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        if public_import and not (config.live_enabled and config.budget_verified):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Live processing is currently unavailable. Please try again later."
                },
            )
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 21 * 1024 * 1024):
            return JSONResponse(
                status_code=413, content={"detail": "Upload request too large"}
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


async def invalid(_: Request, exc: Exception):
    return JSONResponse(
        status_code=409 if isinstance(exc, Conflict) else 422,
        content={"detail": str(exc)},
    )


async def missing(_: Request, exc: Exception):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})


def create_app(
    settings: Settings | None = None, database: Database | None = None
) -> FastAPI:
    config = settings or Settings()
    db = database or Database(config.database_url)
    storage = Storage(config)
    services = ApplicationServices(
        config, db, storage, Workflow(db, storage), Processor(db, config, storage)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        config.validate_deployment()
        if config.env != "production":
            db.create_local_schema()
        yield

    application = FastAPI(
        title="Averis Shipping Verification", version="0.2.0", lifespan=lifespan
    )
    application.state.services = services
    # Preserve operator/test integration handles; route code uses typed Services.
    application.state.db = db
    application.state.config = config
    application.state.processor = services.processor
    application.add_middleware(_RequestLimit)
    application.middleware("http")(security_headers)
    application.add_exception_handler(ValueError, invalid)
    application.add_exception_handler(KeyError, missing)
    application.include_router(router)

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        root = Path(config.frontend_dir).resolve()
        relative = path or "index.html"
        if relative.startswith(("api/", "internal/")):
            raise HTTPException(404, "Not found")
        for candidate in (
            root / relative,
            root / f"{relative}.html",
            root / relative / "index.html",
        ):
            resolved = candidate.resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                return FileResponse(resolved)
        raise HTTPException(
            404, "Frontend build unavailable. Run pnpm build in apps/web."
        )

    return application


app = create_app()
