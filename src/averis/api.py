"""Same-origin public application. Identity and case rules live outside transport."""
import mimetypes
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import BoundedSemaphore
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from averis.config import Settings
from averis.demo import seed
from averis.domain import (
    Action,
    CasePage,
    CaseView,
    SessionView,
)
from averis.intake import import_email as persist_import
from averis.persistence import (
    BrowserSession,
    Case,
    Database,
    Document,
    Workspace,
    uid,
    utcnow,
)
from averis.processing import Processor, aware
from averis.storage import Storage
from averis.workflow import Conflict, Workflow, take_quota, view_of

COOKIE = "averis_session"


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
        upload = path == "/api/imports" or path.endswith("/revisions")
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
            await JSONResponse(status_code=413, content={"detail": "Request exceeds transport size limit"})(scope, receive, send)


class ActorInput(BaseModel):
    actor: str


class ImportEmail(BaseModel):
    subject: str = Field(min_length=1, max_length=1000)
    sender: str = Field(max_length=320)
    body: str = Field(max_length=100_000)


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    config = settings or Settings()
    db = database or Database(config.database_url)
    storage = Storage(config)
    workflow = Workflow(db, storage)
    processor = Processor(db, config, storage)
    preview_slot = BoundedSemaphore(1)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        config.validate_deployment()
        if config.env != "production":
            db.create_local_schema()
        yield

    application = FastAPI(title="Averis Shipping Verification", version="0.2.0", lifespan=lifespan)
    application.add_middleware(_RequestLimit)
    application.state.db = db
    application.state.config = config
    application.state.processor = processor

    def identity(request: Request) -> BrowserSession:
        raw = request.cookies.get(COOKIE, "")
        digest = sha256(raw.encode()).hexdigest()
        with db.session() as session:
            actor = session.get(BrowserSession, digest)
            if actor is None or aware(actor.expires_at) <= utcnow():
                raise HTTPException(401, "Enter a demo workspace to continue")
            return actor

    def mutation(request: Request, actor: Annotated[BrowserSession, Depends(identity)]) -> BrowserSession:
        if request.headers.get("origin") != config.origin:
            raise HTTPException(403, "Origin not allowed")
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), actor.csrf):
            raise HTTPException(403, "Refresh your session before making changes")
        return actor

    def session_view(actor: BrowserSession) -> SessionView:
        return SessionView(actor=actor.actor, csrf_token=actor.csrf, expires_at=actor.expires_at.isoformat(),
                           live_enabled=config.live_enabled and config.budget_verified)

    @application.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/api/imports" or request.url.path.endswith("/revisions"):
            if not config.operator_token or not secrets.compare_digest(request.headers.get("x-operator-token", ""), config.operator_token):
                return JSONResponse(status_code=403, content={"detail": "Uploads require operator authorization"})
            try:
                actor = identity(request)
                mutation(request, actor)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 21 * 1024 * 1024):
                return JSONResponse(status_code=413, content={"detail": "Upload request too large"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ValueError)
    async def invalid(_: Request, exc: ValueError):
        return JSONResponse(status_code=409 if isinstance(exc, Conflict) else 422, content={"detail": str(exc)})

    @application.exception_handler(KeyError)
    async def missing(_: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": "Resource not found"})

    @application.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "live_processing_enabled": config.live_enabled,
                "budget_verification_enabled": config.budget_verified}

    @application.post("/api/demo/session", response_model=SessionView)
    def start(request: Request, response: Response) -> SessionView:
        if request.headers.get("origin") != config.origin:
            raise HTTPException(403, "Origin not allowed")
        raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(hours=24)
        client = sha256((request.client.host if request.client else "unknown").encode()).hexdigest()[:24]
        with db.session() as session, session.begin():
            take_quota(session, f"sessions:day:{utcnow().date()}", 100)
            take_quota(session, f"sessions:hour:{utcnow().strftime('%Y%m%d%H')}:{client}", 10)
            workspace = Workspace(id=uid(), expires_at=expires)
            session.add(workspace)
            actor = BrowserSession(token_hash=sha256(raw.encode()).hexdigest(), workspace_id=workspace.id,
                                   actor="John Tan", csrf=csrf, expires_at=expires)
            session.add(actor)
            seed(session, workspace, storage)
        response.set_cookie(COOKIE, raw, max_age=86400, httponly=True, secure=config.env == "production",
                            samesite="lax", path="/")
        return session_view(actor)

    @application.get("/api/session", response_model=SessionView)
    def current(actor: Annotated[BrowserSession, Depends(identity)]) -> SessionView:
        return session_view(actor)

    @application.post("/api/session/actor", response_model=SessionView)
    def switch(payload: ActorInput, actor: Annotated[BrowserSession, Depends(mutation)]) -> SessionView:
        if payload.actor not in SessionView.model_fields["reviewers"].default:
            raise HTTPException(422, "Unknown demo reviewer")
        with db.session() as session, session.begin():
            row = session.get(BrowserSession, actor.token_hash)
            if row is None:
                raise HTTPException(401, "Session expired")
            row.actor = payload.actor
            return session_view(row)

    @application.post("/api/session/logout")
    def logout(response: Response, actor: Annotated[BrowserSession, Depends(mutation)]) -> dict[str, bool]:
        with db.session() as session, session.begin():
            row = session.get(BrowserSession, actor.token_hash)
            if row:
                session.delete(row)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @application.get("/api/cases", response_model=CasePage)
    def cases(actor: Annotated[BrowserSession, Depends(identity)], view: str = "all", q: str = "",
              page: int = 1, page_size: int = 25, category: str = "", assignee: str = "") -> CasePage:
        if page < 1 or not 1 <= page_size <= 100 or len(q) > 200:
            raise HTTPException(422, "Invalid pagination or search")
        with db.session() as session:
            query = select(Case).where(Case.workspace_id == actor.workspace_id)
            if q:
                query = query.where(Case.subject.ilike(f"%{q}%"))
            if category:
                query = query.where(Case.category == category)
            if assignee:
                query = query.where(Case.assignee == assignee)
            if view == "mismatches":
                query = query.where(Case.has_mismatch.is_(True))
            elif view == "review":
                query = query.where(Case.needs_review.is_(True))
            elif view in {"waiting", "completed"}:
                query = query.where(Case.workflow == view)
            elif view != "all":
                raise HTTPException(422, "Unknown inbox view")
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            items = [view_of(row) for row in session.scalars(query.order_by(Case.received_at.desc()).offset((page-1)*page_size).limit(page_size))]
        return CasePage(items=items, total=total, page=page, page_size=page_size)

    @application.get("/api/cases/{case_id}", response_model=CaseView)
    def case(case_id: str, actor: Annotated[BrowserSession, Depends(identity)]) -> CaseView:
        with db.session() as session:
            row = session.scalar(select(Case).where(Case.id == case_id, Case.workspace_id == actor.workspace_id))
            if row is None:
                raise HTTPException(404, "Case not found")
            return view_of(row)

    @application.post("/api/cases/{case_id}/actions", response_model=CaseView)
    def action(case_id: str, payload: Action, actor: Annotated[BrowserSession, Depends(mutation)]) -> CaseView:
        result, run_id = workflow.apply(actor.workspace_id, case_id, actor.actor, payload,
            config.live_enabled and config.budget_verified, actor.token_hash)
        if run_id:
            processor.dispatch(run_id)
        return result

    def document(doc_id: str, actor: BrowserSession) -> Document:
        with db.session() as session:
            row = session.scalar(select(Document).where(Document.id == doc_id, Document.workspace_id == actor.workspace_id))
            if row is None:
                raise HTTPException(404, "Document not found")
            return row

    @application.get("/api/documents/{doc_id}/content")
    def content(doc_id: str, actor: Annotated[BrowserSession, Depends(identity)]) -> Response:
        row = document(doc_id, actor)
        mime = mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
        safe_name = Path(row.filename).name.replace('"', "").replace("\r", "").replace("\n", "")
        return Response(storage.read(row.object_key), media_type=mime,
                        headers={"Content-Disposition": "inline; filename*=UTF-8''" + quote(safe_name, safe="")})

    @application.get("/api/documents/{doc_id}/preview")
    def preview(doc_id: str, actor: Annotated[BrowserSession, Depends(identity)], page: int = 1) -> Response:
        row = document(doc_id, actor)
        from averis.documents import DocumentPreviewError, render_preview_bounded
        if not preview_slot.acquire(blocking=False):
            raise HTTPException(429, "A preview is being prepared. Try again shortly.")
        try:
            rendered = render_preview_bounded(row.filename, storage.read(row.object_key), page=page)
        except DocumentPreviewError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            preview_slot.release()
        return Response(rendered, media_type="image/png")

    @application.post("/api/imports", response_model=CaseView)
    async def import_email(request: Request, actor: Annotated[BrowserSession, Depends(mutation)],
                           email: Annotated[str, Form()], files: Annotated[list[UploadFile], File()]) -> CaseView:
        if not config.operator_token or not secrets.compare_digest(request.headers.get("x-operator-token", ""), config.operator_token):
            raise HTTPException(403, "Arbitrary uploads require operator authorization")
        payload = ImportEmail.model_validate_json(email)
        if len(files) > 8:
            raise HTTPException(422, "At most eight attachments per email")
        attachments: list[tuple[str, bytes]] = []
        total_bytes = 0
        for file in files:
            chunks: list[bytes] = []
            size = 0
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                total_bytes += len(chunk)
                if total_bytes > 20 * 1024 * 1024:
                    raise HTTPException(413, "Email attachments exceed the combined 20 MB limit")
                if size > 10 * 1024 * 1024:
                    raise HTTPException(413, "Attachment exceeds 10 MB")
                chunks.append(chunk)
            name = Path(file.filename or "attachment").name
            if Path(name).suffix.lower() not in {".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"}:
                raise HTTPException(422, "Unsupported attachment type")
            attachments.append((name, b"".join(chunks)))
        result = persist_import(
            db,
            storage,
            actor.workspace_id,
            actor.actor,
            payload.subject,
            payload.sender,
            payload.body,
            attachments,
        )
        if result.run_id:
            processor.dispatch(result.run_id)
        return result.view
    @application.post("/api/cases/{case_id}/revisions", response_model=CaseView)
    async def revision_upload(case_id: str, request: Request, actor: Annotated[BrowserSession, Depends(mutation)],
                              expected_revision: Annotated[int, Form()], document_id: Annotated[str, Form()],
                              reason: Annotated[str, Form()], file: Annotated[UploadFile, File()]) -> CaseView:
        if not config.operator_token or not secrets.compare_digest(request.headers.get("x-operator-token", ""), config.operator_token):
            raise HTTPException(403, "Arbitrary revisions require operator authorization")
        data = bytearray()
        while chunk := await file.read(64 * 1024):
            data.extend(chunk)
            if len(data) > 10 * 1024 * 1024:
                raise HTTPException(413, "Attachment exceeds 10 MB")
        filename = Path(file.filename or "attachment").name
        if Path(filename).suffix.lower() not in {".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(422, "Unsupported attachment type")
        view, run_id = workflow.attach_revision(actor.workspace_id, case_id, actor.actor, expected_revision,
                                                document_id, filename, bytes(data), reason)
        processor.dispatch(run_id)
        return view

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        root = Path(config.frontend_dir).resolve()
        relative = path or "index.html"
        if relative.startswith(("api/", "internal/")):
            raise HTTPException(404, "Not found")
        for candidate in (root / relative, root / f"{relative}.html", root / relative / "index.html"):
            resolved = candidate.resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                return FileResponse(resolved)
        raise HTTPException(404, "Frontend build unavailable. Run pnpm build in apps/web.")

    return application


app = create_app()
