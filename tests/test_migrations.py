"""Verify the committed migrations, not only ORM-created test tables."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_fresh_postgres_migrations_match_application_metadata(monkeypatch):
    url = os.getenv("AVERIS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AVERIS_TEST_DATABASE_URL is not configured")
    schema = f"averis_migration_{uuid4().hex[:16]}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        scoped = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
        monkeypatch.setenv(
            "AVERIS_DATABASE_URL", scoped.render_as_string(hide_password=False)
        )
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        command.check(config)
        with admin.connect() as connection:
            assert (
                connection.scalar(
                    text(f'SELECT count(*) FROM "{schema}".alembic_version')
                )
                == 1
            )
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
