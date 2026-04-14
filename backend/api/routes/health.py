from fastapi import APIRouter
from sqlalchemy import text
from backend.config.database import get_connection

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.get("/health/db")
def db_health_check():
    try:
        conn = get_connection()
        conn.execute(text("SELECT 1"))
        conn.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
