"""Immutable original storage; object keys are never supplied by a browser."""

import re
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from averis.config import Settings

MAX_CONTENT_BYTES = 10 * 1024 * 1024
SEED_PREFIX = "seeds/"
_SEED_DIGEST = re.compile(r"[0-9a-f]{64}")
_SEED_REFERENCE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


class Storage:
    """Store immutable originals and share content-addressed demo seeds safely."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = Path(settings.storage_dir).resolve()
        self.client = (
            boto3.client(  # pyright: ignore[reportUnknownMemberType] -- unrelated service overloads lack stubs; S3 methods are typed
                "s3",
                endpoint_url=settings.r2_endpoint,
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                region_name="auto",
            )
            if settings.storage_backend == "r2"
            else None
        )

    @staticmethod
    def _validate_content(content: bytes) -> str:
        if not content or len(content) > MAX_CONTENT_BYTES:
            raise ValueError("Attachment must contain 1 byte to 10 MB")
        return sha256(content).hexdigest()

    @staticmethod
    def _validate_seed_reference(reference: str) -> None:
        if not _SEED_REFERENCE.fullmatch(reference):
            raise ValueError("Seed reference must be a canonical UUID")

    @staticmethod
    def _canonical_seed_key(key: str) -> str:
        if not key.startswith(SEED_PREFIX):
            return key
        parts = key.split("/")
        if len(parts) not in {2, 3} or not _SEED_DIGEST.fullmatch(parts[1]):
            raise ValueError("Invalid seed storage key")
        if len(parts) == 3:
            Storage._validate_seed_reference(parts[2])
        return f"{SEED_PREFIX}{parts[1]}"

    def _local_target(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return target

    def put(self, content: bytes) -> tuple[str, str]:
        digest = self._validate_content(content)
        key = f"originals/{uuid4()}/{digest}"
        if self.client:
            self.client.put_object(
                Bucket=self.settings.r2_bucket,
                Key=key,
                Body=content,
                ContentType="application/octet-stream",
            )
        else:
            target = self._local_target(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as file:
                file.write(content)
        return key, digest

    def put_seed(self, content: bytes, reference: str) -> tuple[str, str]:
        """Persist one immutable seed and return a unique workspace reference.

        The canonical ``seeds/<sha256>`` object is shared across demo workspaces;
        ``reference`` keeps each workspace's metadata row independently addressable.
        """
        digest = self._validate_content(content)
        self._validate_seed_reference(reference)
        canonical = f"{SEED_PREFIX}{digest}"
        if self.client:
            try:
                self.client.head_object(Bucket=self.settings.r2_bucket, Key=canonical)
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code not in {"404", "NoSuchKey", "NotFound"}:
                    raise
                self.client.put_object(
                    Bucket=self.settings.r2_bucket,
                    Key=canonical,
                    Body=content,
                    ContentType="application/octet-stream",
                )
        else:
            target = self._local_target(canonical)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                try:
                    with target.open("xb") as file:
                        file.write(content)
                except FileExistsError:
                    pass
        return f"{canonical}/{reference}", digest

    def read(self, key: str) -> bytes:
        resolved_key = self._canonical_seed_key(key)
        if self.client:
            response = self.client.get_object(
                Bucket=self.settings.r2_bucket, Key=resolved_key
            )
            body = response["Body"]
            try:
                content = body.read(MAX_CONTENT_BYTES + 1)
            finally:
                body.close()
        else:
            with self._local_target(resolved_key).open("rb") as file:
                content = file.read(MAX_CONTENT_BYTES + 1)
        self._validate_content(content)
        return content

    def delete(self, key: str) -> None:
        if key.startswith(SEED_PREFIX):
            self._canonical_seed_key(key)
            return
        if self.client:
            self.client.delete_object(Bucket=self.settings.r2_bucket, Key=key)
        else:
            self._local_target(key).unlink(missing_ok=True)
