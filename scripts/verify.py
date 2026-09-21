"""One offline verification entry point; never invokes a paid provider."""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path = ROOT) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def check_boundaries() -> None:
    prohibited = {
        "contracts": {
            "fastapi",
            "sqlalchemy",
            "averis.api",
            "averis.persistence",
            "averis.intelligence",
            "averis.jev",
        },
        "domain": {
            "fastapi",
            "sqlalchemy",
            "averis.api",
            "averis.persistence",
            "averis.intelligence",
            "averis.jev",
        },
        "numeric_evidence": {
            "fastapi",
            "sqlalchemy",
            "averis.persistence",
            "averis.jev",
            "averis.intelligence",
        },
        "verification": {
            "fastapi",
            "sqlalchemy",
            "averis.api",
            "averis.persistence",
            "averis.intelligence",
            "averis.jev",
        },
        "documents": {
            "fastapi",
            "averis.intelligence",
            "averis.jev",
            "averis.processing",
            "averis.workflow",
        },
        "word_structure": {
            "fastapi",
            "sqlalchemy",
            "averis.intelligence",
            "averis.jev",
            "averis.processing",
            "averis.workflow",
        },
        "email_intake": {"fastapi", "averis.api", "averis.worker"},
        "workflow": {"fastapi", "averis.api", "averis.worker", "averis.jev"},
        "processing": {"fastapi", "averis.api", "averis.worker"},
        "runner": {"fastapi", "averis.api", "averis.worker", "averis.intelligence"},
        "jev": {
            "fastapi",
            "sqlalchemy",
            "averis.api",
            "averis.persistence",
            "averis.processing",
            "averis.workflow",
            "averis.routes",
            "averis.http_context",
        },
        "intelligence": {
            "fastapi",
            "sqlalchemy",
            "averis.api",
            "averis.persistence",
            "averis.processing",
            "averis.workflow",
            "averis.routes",
            "averis.http_context",
            "averis.jev",
        },
    }
    for module in (
        "review",
        "case_status",
        "api_responses",
        "pipeline",
        "fields",
        "versions",
        "ocr",
        "pairing",
    ):
        prohibited[module] = {
            "fastapi",
            "sqlalchemy",
            "averis.api",
            "averis.persistence",
            "averis.processing",
            "averis.workflow",
            "averis.routes",
            "averis.http_context",
            "averis.jev",
        }
    # Domain and pipeline must not load Jev or parser libraries.
    prohibited["jev_prompts"] = set(prohibited["jev"])
    prohibited["jev_classification"] = set(prohibited["jev"])
    prohibited["deepseek"] = set(prohibited["jev"])
    prohibited["processing"].update({"averis.jev", "averis.deepseek"})
    prohibited["processing_components"] = set(prohibited["pipeline"])
    for forbidden in prohibited.values():
        if "averis.jev" in forbidden:
            forbidden.add("typesafe_sdk")
            forbidden.add("averis.jev_prompts")
            forbidden.add("averis.processing_setup")
            forbidden.add("averis.jev_classification")
            forbidden.add("averis.deepseek")
    prohibited["processing"].discard("averis.processing_setup")
    parser_libraries = {
        "pdfplumber",
        "pypdfium2",
        "docx",
        "openpyxl",
        "pytesseract",
        "PIL",
        "pillow",
        "rapidocr",
        "onnxruntime",
        "cv2",
    }
    for path in (ROOT / "backend/src/averis").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            imports = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else (
                    [name.name for name in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
            )
            for name in imports:
                if any(
                    name == p or name.startswith(p + ".")
                    for p in prohibited.get(path.stem, set())
                ):
                    raise SystemExit(
                        f"Module boundary violation: {path.name} imports {name}"
                    )
                if path.stem in {"domain", "pipeline"} and (
                    name == "averis.jev"
                    or name.startswith("averis.jev.")
                    or name.split(".")[0] in parser_libraries
                ):
                    raise SystemExit(
                        f"Module boundary violation: {path.name} loads Jev/parser {name}"
                    )
                if path.stem not in {"cli", "evaluation_dataset"} and name in {
                    "averis.evaluation_dataset",
                    "averis.cli",
                }:
                    raise SystemExit(
                        f"Runtime cannot import evaluation data: {path.name}"
                    )
    print("Module boundaries passed", flush=True)


def check_contracts(pnpm: str) -> None:
    from averis.api import create_app
    from averis.config import Settings

    schema = create_app(Settings()).openapi()
    expected = json.loads(
        (ROOT / "frontend/openapi.json").read_text(encoding="utf-8-sig")
    )
    if schema != expected:
        raise SystemExit(
            "OpenAPI drift. Export app.openapi() and run pnpm generate:api."
        )
    with tempfile.TemporaryDirectory(prefix="averis-contract-") as directory:
        output = Path(directory) / "api.ts"
        run(
            pnpm,
            "exec",
            "openapi-typescript",
            "openapi.json",
            "-o",
            str(output),
            cwd=ROOT / "frontend",
        )
        current = (ROOT / "frontend/src/lib/generated/api.ts").read_text(
            encoding="utf-8"
        )
        if output.read_text(encoding="utf-8") != current:
            raise SystemExit("Generated frontend types drift. Run pnpm generate:api.")


def check_test_database() -> None:
    """Fail promptly when the explicitly configured integration database is offline."""
    url = os.environ.get("AVERIS_TEST_DATABASE_URL")
    if not url:
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import SQLAlchemyError

    if make_url(url).get_backend_name() != "postgresql":
        raise SystemExit("AVERIS_TEST_DATABASE_URL must point to PostgreSQL.")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise SystemExit(
            "The configured PostgreSQL test database is unavailable. "
            "Start the database and rerun verification."
        ) from None
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-only", action="store_true")
    options = parser.parse_args()
    check_boundaries()
    run(
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--config",
        "pyproject.toml",
        "--check",
        "src",
        "tests",
        "../scripts",
        "migrations",
        cwd=ROOT / "backend",
    )
    run(
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--config",
        "pyproject.toml",
        "src",
        "tests",
        "../scripts",
        "migrations",
        cwd=ROOT / "backend",
    )
    run(sys.executable, "-m", "pyright", cwd=ROOT / "backend")
    check_test_database()
    run(sys.executable, "-m", "pytest", "-q", cwd=ROOT / "backend")
    if not options.backend_only:
        pnpm = shutil.which("pnpm")
        if pnpm is None:
            raise SystemExit("Install pnpm 10.26.2 to check the frontend")
        check_contracts(pnpm)
        for command in ("format:check", "typecheck", "lint", "test", "build"):
            run(pnpm, command, cwd=ROOT / "frontend")
    print("Verification passed; paid inference was not enabled.", flush=True)


if __name__ == "__main__":
    main()
