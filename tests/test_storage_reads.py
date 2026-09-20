"""Original reads enforce storage bounds and release remote connections."""

from io import BytesIO
from types import SimpleNamespace

import pytest

from averis.config import Settings
from averis.storage import MAX_CONTENT_BYTES, Storage


@pytest.mark.parametrize("oversized", [False, True])
def test_remote_body_closes_on_success_and_rejected_size(tmp_path, oversized):
    content = b"x" * (MAX_CONTENT_BYTES + 1) if oversized else b"document"
    storage = Storage(Settings(_env_file=None, storage_dir=str(tmp_path)))
    body = BytesIO(content)
    storage.client = SimpleNamespace(get_object=lambda **_kwargs: {"Body": body})
    if len(content) > MAX_CONTENT_BYTES:
        with pytest.raises(ValueError, match="10 MB"):
            storage.read("originals/test")
    else:
        assert storage.read("originals/test") == content
    assert body.closed


def test_local_oversized_original_is_rejected(tmp_path):
    storage = Storage(Settings(_env_file=None, storage_dir=str(tmp_path)))
    (tmp_path / "oversized").write_bytes(b"x" * (MAX_CONTENT_BYTES + 1))
    with pytest.raises(ValueError, match="10 MB"):
        storage.read("oversized")
