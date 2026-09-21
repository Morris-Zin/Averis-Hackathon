"""Bulk ingestion parses organizer-style input safely and imports per email."""

import io
import json
import stat
import zipfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from averis.api import create_app
from averis.bulk_ingest import (
    MAX_ARCHIVE_ENTRIES,
    MAX_EMAILS_PER_REQUEST,
    parse_archive,
    parse_email_files,
)
from averis.config import Settings
from averis.email_intake import BulkEmailRequest, import_many
from averis.persistence import Base, Case, Database, Workspace, utcnow
from averis.storage import Storage


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def email_json(email_id: str, attachments: list[str]) -> bytes:
    return json.dumps(
        {
            "email_id": email_id,
            "from": "sender@example.test",
            "subject": f"Documents for {email_id}",
            "body": "Please check the attached documents.",
            "attachments": attachments,
        }
    ).encode()


def organizer_archive() -> bytes:
    return make_zip(
        {
            "inbox/email_001.json": email_json(
                "email_001",
                ["attachments/email_001_SI.txt", "attachments/email_001_BL.txt"],
            ),
            "attachments/email_001_SI.txt": b"Shipping instruction SYNTH-001",
            "attachments/email_001_BL.txt": b"Draft bill of lading SYNTH-001",
        }
    )


def test_archive_parses_organizer_layout_with_exact_paths():
    plan = parse_archive(organizer_archive())

    assert [record.ref for record in plan.records] == ["email_001"]
    (record,) = plan.records
    # Attachments sort by filename so the import digest is order-stable.
    assert [name for name, _ in record.attachments] == [
        "email_001_BL.txt",
        "email_001_SI.txt",
    ]
    assert record.missing_attachments == ()
    assert plan.failures == ()


def test_archive_resolves_unique_basename_without_guessing():
    data = make_zip(
        {
            "inbox/email_001.json": email_json("email_001", ["email_001_SI.txt"]),
            "attachments/email_001_SI.txt": b"Shipping instruction",
        }
    )

    (record,) = parse_archive(data).records
    assert [name for name, _ in record.attachments] == ["email_001_SI.txt"]


def test_archive_keeps_missing_references_honest():
    data = make_zip(
        {
            "inbox/email_001.json": email_json(
                "email_001", ["attachments/missing_SI.txt"]
            ),
        }
    )

    plan = parse_archive(data)

    (record,) = plan.records
    assert record.attachments == ()
    assert record.missing_attachments == ("attachments/missing_SI.txt",)


def test_archive_does_not_assign_other_emails_attachments():
    data = make_zip(
        {
            "inbox/email_001.json": email_json(
                "email_001", ["attachments/email_001_SI.txt"]
            ),
            "inbox/email_002.json": email_json("email_002", []),
            "attachments/email_001_SI.txt": b"Shipping instruction",
        }
    )

    plan = parse_archive(data)

    second = next(record for record in plan.records if record.ref == "email_002")
    assert second.attachments == ()
    assert second.missing_attachments == ()


def test_archive_ambiguous_basename_fails_only_that_email():
    data = make_zip(
        {
            "inbox/email_001.json": email_json("email_001", ["shared.txt"]),
            "inbox/email_002.json": email_json("email_002", []),
            "a/shared.txt": b"first",
            "b/shared.txt": b"second",
        }
    )

    plan = parse_archive(data)

    assert [record.ref for record in plan.records] == ["email_002"]
    (failure,) = plan.failures
    assert failure.ref == "email_001"
    assert "several" in failure.error


def test_archive_rejects_traversal_member():
    with pytest.raises(ValueError, match="unsafe"):
        parse_archive(make_zip({"../evil.txt": b"evil"}))


def test_archive_rejects_absolute_member():
    with pytest.raises(ValueError, match="unsafe"):
        parse_archive(make_zip({"/abs.txt": b"absolute"}))


def test_archive_rejects_duplicate_members():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inbox/email_001.json", email_json("email_001", []))
        archive.writestr("inbox/email_001.json", email_json("email_001", []))
    with pytest.raises(ValueError, match="duplicate"):
        parse_archive(buffer.getvalue())


def test_archive_rejects_oversized_entry():
    data = make_zip(
        {
            "inbox/email_001.json": email_json("email_001", ["big.txt"]),
            "big.txt": b"x" * (10 * 1024 * 1024 + 1),
        }
    )
    with pytest.raises(ValueError, match="10 MB"):
        parse_archive(data)


def test_archive_rejects_too_many_entries():
    members = {f"file_{index}.txt": b"x" for index in range(MAX_ARCHIVE_ENTRIES + 1)}
    with pytest.raises(ValueError, match="smaller archives"):
        parse_archive(make_zip(members))


def test_archive_supports_full_organizer_scale_within_byte_bounds():
    members = {
        f"inbox/email_{index:03d}.json": email_json(f"email_{index:03d}", [])
        for index in range(520)
    }

    plan = parse_archive(make_zip(members))

    assert len(plan.records) == 520
    assert plan.failures == ()


def test_archive_rejects_drive_relative_member():
    with pytest.raises(ValueError, match="unsafe"):
        parse_archive(make_zip({"C:foo.txt": b"drive-relative"}))


def test_archive_rejects_unreadable_member_as_client_error(monkeypatch):
    real_read = zipfile.ZipFile.read

    def fail_on_attachment(self, name):
        member = getattr(name, "filename", name)
        if member == "attachments/email_001_SI.txt":
            raise RuntimeError("File is encrypted")
        return real_read(self, name)

    monkeypatch.setattr(zipfile.ZipFile, "read", fail_on_attachment)
    with pytest.raises(ValueError, match="cannot be read"):
        parse_archive(organizer_archive())


def test_archive_rejects_symlink_member():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inbox/email_001.json", email_json("email_001", []))
        link = zipfile.ZipInfo("attachments/link.txt")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "targets/real.txt")
    with pytest.raises(ValueError, match="symlink"):
        parse_archive(buffer.getvalue())


def test_archive_without_email_json_fails():
    with pytest.raises(ValueError, match="no email JSON"):
        parse_archive(make_zip({"attachments/note.txt": b"note"}))


def test_archive_rejects_too_many_emails():
    members = {
        f"inbox/email_{index:03d}.json": email_json(f"email_{index:03d}", [])
        for index in range(MAX_EMAILS_PER_REQUEST + 1)
    }
    with pytest.raises(ValueError, match="smaller archives"):
        parse_archive(make_zip(members))


def test_invalid_email_json_is_a_per_file_failure():
    data = make_zip(
        {
            "inbox/good.json": email_json("good", []),
            "inbox/bad.json": b'{"email_id": 42}',
        }
    )

    plan = parse_archive(data)

    assert [record.ref for record in plan.records] == ["good"]
    (failure,) = plan.failures
    assert failure.ref == "inbox/bad.json"
    assert "invalid" in failure.error


def test_unsupported_attachment_type_fails_only_that_email():
    data = make_zip(
        {
            "inbox/email_001.json": email_json("email_001", ["run.exe"]),
            "run.exe": b"binary",
        }
    )

    plan = parse_archive(data)

    assert plan.records == ()
    (failure,) = plan.failures
    assert "Unsupported attachment type" in failure.error


def test_too_many_attachments_fails_only_that_email():
    refs = [f"doc_{index}.txt" for index in range(9)]
    members = {"inbox/email_001.json": email_json("email_001", refs)}
    members.update({name: b"x" for name in refs})

    plan = parse_archive(make_zip(members))

    assert plan.records == ()
    assert "eight attachments" in plan.failures[0].error


def test_combined_attachment_bytes_share_single_email_limit():
    refs = ["one.txt", "two.txt", "three.txt"]
    pool = [(name, bytes(7 * 1024 * 1024)) for name in refs]

    plan = parse_email_files([("email_001.json", email_json("email_001", refs))], pool)

    assert plan.records == ()
    assert "20 MB or less" in plan.failures[0].error


def test_attachment_order_is_normalized_for_stable_dedup():
    first = make_zip(
        {
            "inbox/email_001.json": email_json("email_001", ["b.txt", "a.txt"]),
            "a.txt": b"alpha",
            "b.txt": b"beta",
        }
    )
    second = make_zip(
        {
            "b.txt": b"beta",
            "a.txt": b"alpha",
            "inbox/email_001.json": email_json("email_001", ["a.txt", "b.txt"]),
        }
    )

    one = parse_archive(first).records[0]
    two = parse_archive(second).records[0]

    assert (
        one.attachments == two.attachments == (("a.txt", b"alpha"), ("b.txt", b"beta"))
    )


def test_repeated_reference_to_one_file_collapses():
    data = make_zip(
        {
            "inbox/email_001.json": email_json(
                "email_001", ["attachments/si.txt", "si.txt"]
            ),
            "attachments/si.txt": b"Shipping instruction",
        }
    )

    (record,) = parse_archive(data).records

    assert [name for name, _ in record.attachments] == ["si.txt"]


def test_loose_json_mode_matches_pool_by_filename():
    plan = parse_email_files(
        [
            ("first.json", email_json("first", ["si.txt", "gone.txt"])),
            ("second.json", email_json("second", [])),
        ],
        [("si.txt", b"Shipping instruction")],
    )

    assert [record.ref for record in plan.records] == ["first", "second"]
    assert [name for name, _ in plan.records[0].attachments] == ["si.txt"]
    assert plan.records[0].missing_attachments == ("gone.txt",)
    assert plan.failures == ()


def test_loose_json_mode_rejects_duplicate_filenames():
    with pytest.raises(ValueError, match="Duplicate attachment"):
        parse_email_files(
            [("first.json", email_json("first", ["si.txt"]))],
            [("si.txt", b"one"), ("dir/si.txt", b"two")],
        )


@pytest.fixture
def bulk_intake(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'bulk-intake.db'}",
        storage_backend="local",
        storage_dir=str(tmp_path / "objects"),
    )
    db = Database(settings.database_url)
    Base.metadata.create_all(db.engine)
    with db.session() as session, session.begin():
        session.add(
            Workspace(id="workspace-1", expires_at=utcnow() + timedelta(days=1))
        )
    return db, Storage(settings)


def bulk_request(ref="email_001"):
    return BulkEmailRequest(
        ref=ref,
        subject="Bulk test",
        sender="tester@example.test",
        body="Please review.",
        attachments=(("si.txt", b"Shipping instruction"),),
        missing_attachments=("gone.txt",),
    )


def test_import_many_keeps_validated_failure_detail(bulk_intake, monkeypatch):
    db, storage = bulk_intake
    monkeypatch.setattr(
        "averis.email_intake.import_email",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("Workspace quota detail")
        ),
    )

    (item,) = import_many(
        db, storage, "workspace-1", "John Tan", [bulk_request()]
    ).items

    assert item.status == "failed"
    assert item.error == "Workspace quota detail"
    assert item.missing_attachments == ("gone.txt",)


def test_import_many_returns_stable_message_for_unexpected_failures(
    bulk_intake, monkeypatch
):
    db, storage = bulk_intake
    monkeypatch.setattr(
        "averis.email_intake.import_email",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("connection conninfo=secret password=hunter2")
        ),
    )

    (item,) = import_many(
        db, storage, "workspace-1", "John Tan", [bulk_request()]
    ).items

    assert item.status == "failed"
    assert item.error == "The email could not be imported. Try again."
    assert "secret" not in (item.error or "")
    assert "hunter2" not in (item.error or "")


def test_import_many_partial_success_keeps_valid_records(bulk_intake):
    db, storage = bulk_intake

    outcome = import_many(
        db,
        storage,
        "workspace-1",
        "John Tan",
        [bulk_request("first"), bulk_request("first")],
    )

    assert [item.status for item in outcome.items] == ["accepted", "duplicate"]
    assert len(outcome.run_ids) == 1
    assert outcome.items[1].case_id == outcome.items[0].case_id


@pytest.fixture
def bulk_client(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'bulk.db'}",
        storage_dir=str(tmp_path / "objects"),
        live_enabled=True,
        budget_verified=True,
    )
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        session = client.post(
            "/api/demo/session", headers={"origin": settings.origin}
        ).json()
        headers = {"origin": settings.origin, "x-csrf-token": session["csrf_token"]}
        yield client, headers


def mixed_archive() -> bytes:
    return make_zip(
        {
            "inbox/good.json": email_json(
                "good", ["attachments/good_SI.txt", "attachments/gone.txt"]
            ),
            "inbox/plain.json": email_json("plain", []),
            "inbox/bad.json": b"not json",
            "attachments/good_SI.txt": b"Shipping instruction SYNTH",
        }
    )


def post_archive(client, headers, data: bytes):
    return client.post(
        "/api/bulk-imports",
        headers=headers,
        files=[("archive", ("emails.zip", data, "application/zip"))],
    )


def test_bulk_preview_lists_valid_and_invalid_without_persisting(bulk_client):
    client, headers = bulk_client

    response = client.post(
        "/api/bulk-imports/preview",
        headers=headers,
        files=[("archive", ("emails.zip", mixed_archive(), "application/zip"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] == 2
    assert body["invalid"] == 1
    assert client.get("/api/cases").json()["total"] == 8


def test_bulk_commit_reports_mixed_results_and_links(bulk_client):
    client, headers = bulk_client

    response = post_archive(client, headers, mixed_archive())

    assert response.status_code == 200
    body = response.json()
    assert (body["accepted"], body["duplicates"], body["failed"]) == (2, 0, 1)
    accepted = [item for item in body["items"] if item["status"] == "accepted"]
    assert all(item["case_id"] for item in accepted)
    good = next(item for item in accepted if item["ref"] == "good")
    assert good["attachments"] == 1
    assert good["missing_attachments"] == ["attachments/gone.txt"]
    failed = next(item for item in body["items"] if item["status"] == "failed")
    assert failed["error"]
    for item in accepted:
        assert client.get(f"/api/cases/{item['case_id']}").status_code == 200


def test_bulk_retry_reports_duplicates_without_new_cases(bulk_client):
    client, headers = bulk_client
    first = post_archive(client, headers, mixed_archive()).json()
    before = client.get("/api/cases").json()["total"]

    second = post_archive(client, headers, mixed_archive()).json()

    assert (second["accepted"], second["duplicates"], second["failed"]) == (0, 2, 1)
    good_retry = next(item for item in second["items"] if item["ref"] == "good")
    assert good_retry["status"] == "duplicate"
    assert good_retry["missing_attachments"] == ["attachments/gone.txt"]
    assert client.get("/api/cases").json()["total"] == before
    first_ids = {
        item["case_id"] for item in first["items"] if item["case_id"] is not None
    }
    second_ids = {
        item["case_id"] for item in second["items"] if item["case_id"] is not None
    }
    assert first_ids == second_ids


def test_bulk_commit_case_count_uses_database(bulk_client):
    client, headers = bulk_client
    with client.app.state.db.session() as session:
        before = len(session.scalars(select(Case)).all())
    post_archive(client, headers, mixed_archive())
    with client.app.state.db.session() as session:
        assert len(session.scalars(select(Case)).all()) == before + 2


def test_bulk_commit_requires_session_and_live_processing(bulk_client):
    client, headers = bulk_client
    data = mixed_archive()

    assert post_archive(client, {"origin": headers["origin"]}, data).status_code == 403
    client.app.state.config.live_enabled = False
    assert post_archive(client, headers, data).status_code == 422
    client.app.state.config.live_enabled = True
    client.cookies.clear()
    assert post_archive(client, headers, data).status_code == 401


def test_bulk_commit_rejects_conflicting_modes(bulk_client):
    client, headers = bulk_client

    response = client.post(
        "/api/bulk-imports",
        headers=headers,
        files=[
            ("archive", ("emails.zip", mixed_archive(), "application/zip")),
            ("emails", ("one.json", email_json("one", []), "application/json")),
        ],
    )

    assert response.status_code == 422
    assert "not both" in response.json()["detail"]


def test_bulk_commit_supports_loose_json_files(bulk_client):
    client, headers = bulk_client

    response = client.post(
        "/api/bulk-imports",
        headers=headers,
        files=[
            ("emails", ("one.json", email_json("one", ["si.txt"]), "application/json")),
            ("emails", ("two.json", email_json("two", []), "application/json")),
            ("files", ("si.txt", b"Shipping instruction", "text/plain")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["accepted"], body["duplicates"], body["failed"]) == (2, 0, 0)
    one = next(item for item in body["items"] if item["ref"] == "one")
    assert one["attachments"] == 1
