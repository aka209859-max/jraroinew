from backend.config.database import get_connection

def test_database_connection():
    conn = get_connection()
    assert conn is not None
    conn.close()

def test_jvd_se_exists(db_connection):
    import pandas as pd
    df = pd.read_sql("SELECT COUNT(*) as cnt FROM jvd_se LIMIT 1", db_connection)
    assert df["cnt"].iloc[0] > 0

def test_jrd_kyi_fixed_exists(db_connection):
    import pandas as pd
    df = pd.read_sql("SELECT COUNT(*) as cnt FROM jrd_kyi_fixed LIMIT 1", db_connection)
    assert df["cnt"].iloc[0] > 400000
