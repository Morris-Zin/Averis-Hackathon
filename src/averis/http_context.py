"""Application dependencies and the single HTTP authentication boundary."""

import secrets
from dataclasses import dataclass, field
from hashlib import sha256
from threading import BoundedSemaphore
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request

from averis.config import Settings
from averis.domain import SessionView
from averis.persistence import BrowserSession, Database, utcnow
from averis.processing import Processor, aware
from averis.storage import Storage
from averis.workflow import Workflow

COOKIE = "averis_session"


@dataclass(frozen=True)
class ApplicationServices:
    config: Settings
    db: Database
    storage: Storage
    workflow: Workflow
    processor: Processor
    preview_slot: BoundedSemaphore = field(default_factory=lambda: BoundedSemaphore(1))


def get_services(request: Request) -> ApplicationServices:
    # Starlette's state is dynamically typed; only create_app installs this value.
    return cast(ApplicationServices, request.app.state.services)


Services = Annotated[ApplicationServices, Depends(get_services)]


def identity(request: Request) -> BrowserSession:
    db = get_services(request).db
    raw = request.cookies.get(COOKIE, "")
    digest = sha256(raw.encode()).hexdigest()
    with db.session() as session:
        actor = session.get(BrowserSession, digest)
        if actor is None or aware(actor.expires_at) <= utcnow():
            raise HTTPException(401, "Enter a demo workspace to continue")
        return actor


def mutation(
    request: Request, actor: Annotated[BrowserSession, Depends(identity)]
) -> BrowserSession:
    config = get_services(request).config
    if request.headers.get("origin") != config.origin:
        raise HTTPException(403, "Origin not allowed")
    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), actor.csrf):
        raise HTTPException(403, "Refresh your session before making changes")
    return actor


def session_view(actor: BrowserSession, config: Settings) -> SessionView:
    return SessionView(
        actor=actor.actor,
        csrf_token=actor.csrf,
        expires_at=actor.expires_at.isoformat(),
        live_enabled=config.live_enabled and config.budget_verified,
    )
