"""HTTP translation only; durable processing and review decisions are backend-owned."""

import mimetypes
import secrets
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from averis.api_responses import CasePageResponse, CaseResponse, QueueCaseResponse
from averis.bulk_ingest import (
    MAX_ARCHIVE_BYTES,
    MAX_EMAIL_JSON_BYTES,
    MAX_FILE_BYTES,
    BulkPlan,
    parse_archive,
    parse_email_files,
)
from averis.case_queries import InvalidCaseQuery, list_cases
from averis.demo import seed
from averis.domain import REVIEWERS, Action, CaseView, SessionView
from averis.email_intake import BulkEmailRequest, BulkOutcome, import_many
from averis.email_intake import import_email as persist_import
from averis.http_context import (
    COOKIE,
    ApplicationServices,
    Services,
    identity,
    mutation,
    session_view,
)
from averis.persistence import (
    BrowserSession,
    Case,
    Document,
    Workspace,
    uid,
    utcnow,
)
from averis.storage import MAX_CONTENT_BYTES
from averis.workflow import view_of

router = APIRouter()


class ActorInput(BaseModel):
    actor: str


class ImportEmail(BaseModel):
    subject: str = Field(min_length=1, max_length=1000)
    sender: str = Field(max_length=320)
    body: str = Field(max_length=100_000)


class BulkPreviewEmail(BaseModel):
    ref: str
    subject: str = ""
    sender: str = ""
    attachments: list[str] = Field(default_factory=list)
    missing_attachments: list[str] = Field(default_factory=list)
    error: str | None = None


class BulkPreviewResponse(BaseModel):
    emails: list[BulkPreviewEmail]
    valid: int
    invalid: int


class BulkItemResult(BaseModel):
    ref: str
    status: Literal["accepted", "duplicate", "failed"]
    case_id: str | None = None
    subject: str = ""
    attachments: int = 0
    missing_attachments: list[str] = Field(default_factory=list)
    error: str | None = None


class BulkImportResponse(BaseModel):
    items: list[BulkItemResult]
    accepted: int
    duplicates: int
    failed: int


def document(
    services: ApplicationServices, doc_id: str, actor: BrowserSession
) -> Document:
    with services.db.session() as session:
        row = session.scalar(
            select(Document).where(
                Document.id == doc_id, Document.workspace_id == actor.workspace_id
            )
        )
        if row is None:
            raise HTTPException(404, "Document not found")
        return row


@router.get("/health")
def health(services: Services) -> dict[str, object]:
    return {
        "status": "ok",
        "live_processing_enabled": services.config.live_enabled,
        "budget_verification_enabled": services.config.budget_verified,
    }


@router.post("/api/demo/session", response_model=SessionView)
def start(services: Services, request: Request, response: Response) -> SessionView:
    if request.headers.get("origin") != services.config.origin:
        raise HTTPException(403, "Origin not allowed")
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(hours=24)
    with services.db.session() as session, session.begin():
        workspace = Workspace(id=uid(), expires_at=expires)
        session.add(workspace)
        actor = BrowserSession(
            token_hash=sha256(raw.encode()).hexdigest(),
            workspace_id=workspace.id,
            actor="John Tan",
            csrf=csrf,
            expires_at=expires,
        )
        session.add(actor)
        seed(session, workspace, services.storage)
    response.set_cookie(
        COOKIE,
        raw,
        max_age=86400,
        httponly=True,
        secure=services.config.env == "production",
        samesite="lax",
        path="/",
    )
    return session_view(actor, services.config)


@router.get("/api/session", response_model=SessionView)
def current(
    services: Services, actor: Annotated[BrowserSession, Depends(identity)]
) -> SessionView:
    return session_view(actor, services.config)


@router.post("/api/session/actor", response_model=SessionView)
def switch(
    services: Services,
    payload: ActorInput,
    actor: Annotated[BrowserSession, Depends(mutation)],
) -> SessionView:
    if payload.actor not in REVIEWERS:
        raise HTTPException(422, "Unknown demo reviewer")
    with services.db.session() as session, session.begin():
        row = session.get(BrowserSession, actor.token_hash)
        if row is None:
            raise HTTPException(401, "Session expired")
        row.actor = payload.actor
        return session_view(row, services.config)


@router.post("/api/session/logout")
def logout(
    services: Services,
    response: Response,
    actor: Annotated[BrowserSession, Depends(mutation)],
) -> dict[str, bool]:
    with services.db.session() as session, session.begin():
        row = session.get(BrowserSession, actor.token_hash)
        if row:
            session.delete(row)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/api/cases", response_model=CasePageResponse)
def cases(
    services: Services,
    actor: Annotated[BrowserSession, Depends(identity)],
    view: str = "all",
    q: str = "",
    page: int = 1,
    page_size: int = 25,
    category: str = "",
    assignee: str = "",
) -> CasePageResponse:
    try:
        result = list_cases(
            services.db,
            actor.workspace_id,
            view=view,
            q=q,
            page=page,
            page_size=page_size,
            category=category,
            assignee=assignee,
        )
    except InvalidCaseQuery as exc:
        raise HTTPException(422, str(exc)) from exc
    return CasePageResponse(
        items=[QueueCaseResponse.from_case(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        counts=result.counts,
    )


@router.get("/api/cases/{case_id}", response_model=CaseResponse)
def case(
    services: Services,
    case_id: str,
    actor: Annotated[BrowserSession, Depends(identity)],
) -> CaseView:
    with services.db.session() as session:
        row = session.scalar(
            select(Case).where(
                Case.id == case_id, Case.workspace_id == actor.workspace_id
            )
        )
        if row is None:
            raise HTTPException(404, "Case not found")
        return view_of(row)


@router.post("/api/cases/{case_id}/actions", response_model=CaseResponse)
def action(
    services: Services,
    case_id: str,
    payload: Action,
    actor: Annotated[BrowserSession, Depends(mutation)],
) -> CaseView:
    result, run_id = services.workflow.apply(
        actor.workspace_id,
        case_id,
        actor.actor,
        payload,
        services.config.live_enabled and services.config.budget_verified,
    )
    if run_id:
        services.processor.dispatch(run_id)
    return result


@router.get("/api/documents/{doc_id}/content")
def content(
    services: Services, doc_id: str, actor: Annotated[BrowserSession, Depends(identity)]
) -> Response:
    row = document(services, doc_id, actor)
    mime = mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
    safe_name = (
        Path(row.filename).name.replace('"', "").replace("\r", "").replace("\n", "")
    )
    return Response(
        services.storage.read(row.object_key),
        media_type=mime,
        headers={
            "Content-Disposition": "inline; filename*=UTF-8''"
            + quote(safe_name, safe="")
        },
    )


@router.get("/api/documents/{doc_id}/preview")
def preview(
    services: Services,
    doc_id: str,
    actor: Annotated[BrowserSession, Depends(identity)],
    page: int = 1,
) -> Response:
    row = document(services, doc_id, actor)
    from averis.documents import DocumentPreviewError, render_preview_bounded

    # The comparison opens SI and BL together. Keep rendering serial, but let
    # the companion request wait for the bounded renderer instead of failing
    # every ordinary two-document review immediately.
    if not services.preview_slot.acquire(timeout=20):
        raise HTTPException(429, "A preview is being prepared. Try again shortly.")
    try:
        rendered = render_preview_bounded(
            row.filename, services.storage.read(row.object_key), page=page
        )
    except DocumentPreviewError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        services.preview_slot.release()
    return Response(rendered, media_type="image/png")


async def _read_attachments(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    """Apply the same filename, count and byte limits to imports and revisions."""
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
                raise HTTPException(
                    413, "Email attachments exceed the combined 20 MB limit"
                )
            if size > MAX_CONTENT_BYTES:
                raise HTTPException(413, "Attachment exceeds 10 MB")
            chunks.append(chunk)
        name = Path(file.filename or "attachment").name
        if Path(name).suffix.lower() not in {
            ".txt",
            ".pdf",
            ".docx",
            ".xlsx",
            ".png",
            ".jpg",
            ".jpeg",
        }:
            raise HTTPException(422, "Unsupported attachment type")
        attachments.append((name, b"".join(chunks)))
    return attachments


@router.post("/api/imports", response_model=CaseResponse)
@router.post("/api/manual-imports", response_model=CaseResponse)
async def import_email(
    services: Services,
    request: Request,
    actor: Annotated[BrowserSession, Depends(mutation)],
    email: Annotated[str, Form()],
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> CaseView:
    public_import = request.url.path == "/api/manual-imports"
    if not public_import and (
        not services.config.operator_token
        or not secrets.compare_digest(
            request.headers.get("x-operator-token", ""), services.config.operator_token
        )
    ):
        raise HTTPException(403, "Arbitrary uploads require operator authorization")
    payload = ImportEmail.model_validate_json(email)
    attachments = await _read_attachments(files or [])
    result = await run_in_threadpool(
        persist_import,
        services.db,
        services.storage,
        actor.workspace_id,
        actor.actor,
        payload.subject,
        payload.sender,
        payload.body,
        attachments,
        purpose="demo" if public_import else "development",
    )
    if result.run_id:
        await run_in_threadpool(services.processor.dispatch, result.run_id)
    return result.view


async def _read_upload_bytes(file: UploadFile, cap: int, label: str) -> bytes:
    """Stream one bulk part with an explicit byte bound before parsing."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > cap:
            raise HTTPException(413, f"{label} exceeds its size limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def _parse_bulk_plan(
    archive: UploadFile | None,
    emails: list[UploadFile] | None,
    files: list[UploadFile] | None,
) -> BulkPlan:
    """Parse one bulk request without persisting anything.

    Exactly one source mode is accepted: a ZIP archive, or loose email JSON
    files with optional loose attachments. Upload bytes stream with explicit
    bounds on the event loop; CPU/decompression work runs in a worker thread.
    Failures are per-email; only an unreadable archive or an empty selection
    fails the whole request. Count and byte bounds live in the parser module.
    """
    email_files = emails or []
    loose_files = files or []
    if archive is not None and email_files:
        raise HTTPException(
            422, "Send either a ZIP archive or email JSON files, not both"
        )
    if archive is not None:
        data = await _read_upload_bytes(archive, MAX_ARCHIVE_BYTES, "Archive")
        try:
            return await run_in_threadpool(parse_archive, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if not email_files:
        raise HTTPException(422, "Upload a ZIP archive or at least one email JSON file")
    parsed_emails = [
        (
            Path(item.filename or "email.json").name,
            await _read_upload_bytes(item, MAX_EMAIL_JSON_BYTES, "Email JSON"),
        )
        for item in email_files
    ]
    parsed_files = [
        (
            Path(item.filename or "attachment").name,
            await _read_upload_bytes(item, MAX_FILE_BYTES, "Attachment"),
        )
        for item in loose_files
    ]
    try:
        return await run_in_threadpool(parse_email_files, parsed_emails, parsed_files)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _bulk_response(plan: BulkPlan, outcome: BulkOutcome) -> BulkImportResponse:
    """Project a batch outcome to HTTP; per-email rows keep missing refs."""
    items = [
        BulkItemResult(
            ref=item.ref,
            status=item.status,
            case_id=item.case_id,
            subject=item.subject,
            attachments=item.attachment_count,
            missing_attachments=list(item.missing_attachments),
            error=item.error,
        )
        for item in outcome.items
    ]
    items.extend(
        BulkItemResult(ref=failure.ref, status="failed", error=failure.error)
        for failure in plan.failures
    )
    return BulkImportResponse(
        items=items,
        accepted=sum(1 for item in items if item.status == "accepted"),
        duplicates=sum(1 for item in items if item.status == "duplicate"),
        failed=sum(1 for item in items if item.status == "failed"),
    )


@router.post("/api/bulk-imports/preview", response_model=BulkPreviewResponse)
async def bulk_preview(
    services: Services,
    actor: Annotated[BrowserSession, Depends(mutation)],
    archive: Annotated[UploadFile | None, File()] = None,
    emails: Annotated[list[UploadFile] | None, File()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> BulkPreviewResponse:
    plan = await _parse_bulk_plan(archive, emails, files)
    previews = [
        BulkPreviewEmail(
            ref=record.ref,
            subject=record.subject,
            sender=record.sender,
            attachments=[filename for filename, _ in record.attachments],
            missing_attachments=list(record.missing_attachments),
        )
        for record in plan.records
    ]
    previews.extend(
        BulkPreviewEmail(ref=failure.ref, error=failure.error)
        for failure in plan.failures
    )
    return BulkPreviewResponse(
        emails=previews, valid=len(plan.records), invalid=len(plan.failures)
    )


@router.post("/api/bulk-imports", response_model=BulkImportResponse)
async def bulk_import(
    services: Services,
    actor: Annotated[BrowserSession, Depends(mutation)],
    archive: Annotated[UploadFile | None, File()] = None,
    emails: Annotated[list[UploadFile] | None, File()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> BulkImportResponse:
    plan = await _parse_bulk_plan(archive, emails, files)
    outcome = await run_in_threadpool(
        import_many,
        services.db,
        services.storage,
        actor.workspace_id,
        actor.actor,
        [
            BulkEmailRequest(
                ref=record.ref,
                subject=record.subject,
                sender=record.sender,
                body=record.body,
                attachments=record.attachments,
                missing_attachments=record.missing_attachments,
            )
            for record in plan.records
        ],
        purpose="demo",
    )
    for run_id in outcome.run_ids:
        await run_in_threadpool(services.processor.dispatch, run_id)
    return _bulk_response(plan, outcome)


@router.post("/api/cases/{case_id}/revisions", response_model=CaseResponse)
async def revision_upload(
    services: Services,
    case_id: str,
    request: Request,
    actor: Annotated[BrowserSession, Depends(mutation)],
    expected_revision: Annotated[int, Form()],
    document_id: Annotated[str, Form()],
    reason: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> CaseView:
    if not services.config.operator_token or not secrets.compare_digest(
        request.headers.get("x-operator-token", ""), services.config.operator_token
    ):
        raise HTTPException(403, "Arbitrary revisions require operator authorization")
    [(filename, data)] = await _read_attachments([file])
    view, run_id = await run_in_threadpool(
        services.workflow.attach_revision,
        actor.workspace_id,
        case_id,
        actor.actor,
        expected_revision,
        document_id,
        filename,
        data,
        reason,
    )
    await run_in_threadpool(services.processor.dispatch, run_id)
    return view
