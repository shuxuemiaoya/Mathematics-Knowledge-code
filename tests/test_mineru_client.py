import io
import zipfile
from types import SimpleNamespace

import pytest

from math_knowledge_tools.mineru.core.client import MinerUClient


def test_download_and_extract_zip_rejects_path_traversal(tmp_path):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("../evil.txt", "nope")

    client = MinerUClient()
    client._retry_request = lambda *args, **kwargs: SimpleNamespace(content=payload.getvalue())

    with pytest.raises(ValueError):
        client.download_and_extract_zip("https://example.test/archive.zip", tmp_path)
