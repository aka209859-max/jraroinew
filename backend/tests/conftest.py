import pytest
from backend.config.database import get_connection

@pytest.fixture
def db_connection():
    conn = get_connection()
    yield conn
    conn.close()
