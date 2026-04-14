import pytest
from fastapi.testclient import TestClient

from backend.config.database import get_connection
from backend.main import app


@pytest.fixture
def db_connection():
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture
def client():
    return TestClient(app)
