import base64
import os
from uuid import uuid4

import pytest

from rag_lab.core.security import Cipher


@pytest.fixture
def cipher():
    return Cipher(base64.b64encode(b"s" * 32).decode())


@pytest.fixture
def tenant():
    return uuid4()


@pytest.fixture
def db_repo(cipher):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for isolated pgvector integration checks")
    from sqlalchemy.engine import make_url

    from rag_lab.db.repository import Repository

    if not make_url(url).database.endswith("_test"):
        pytest.fail("Integration database name must end in _test")
    repo = Repository(url, cipher)
    yield repo
    repo.engine.dispose()
