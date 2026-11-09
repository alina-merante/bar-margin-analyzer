from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.analytics import router as analytics_router
from app.routers.categories import router as categories_router
from app.routers.finance import router as finance_router
from app.routers.health import router as health_router
from app.routers.imports import router as imports_router
from fastapi.staticfiles import StaticFiles
from app.routers.documents import router as documents_router
from app.routers.cash_closures import router as cash_closures_router
from app.config import UPLOAD_BASE_PATH, ensure_upload_dirs

from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="Bar Margin Analyzer API")

ensure_upload_dirs()
app.mount("/uploads", StaticFiles(directory=UPLOAD_BASE_PATH), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://verbose-waddle-97gxgpv5qqgx3x7r7-5173.app.github.dev",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(imports_router)
app.include_router(categories_router)
app.include_router(finance_router)
app.include_router(analytics_router)
app.include_router(documents_router)
app.include_router(cash_closures_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Bar Margin Analyzer backend is running"}