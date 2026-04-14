from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import health, analysis

app = FastAPI(
    title="Enable Edge Engine",
    description="プロフェッショナル向け競馬データ分析プラットフォーム",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])

@app.get("/")
def root():
    return {"name": "Enable Edge Engine", "version": "0.1.0", "status": "running"}
