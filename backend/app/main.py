from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.analytics import router as analytics_router
from app.routers.categories import router as categories_router
from app.routers.finance import router as finance_router
from app.routers.health import router as health_router
from app.routers.imports import router as imports_router

from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="Bar Margin Analyzer API")

# ✅ CORS FIX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # per demo va benissimo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(imports_router)
app.include_router(categories_router)
app.include_router(finance_router)
app.include_router(analytics_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Bar Margin Analyzer backend is running"}