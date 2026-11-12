from app.settings import settings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.analytics import router as analytics_router
from app.routers.categories import router as categories_router
from app.routers.finance import router as finance_router
from app.routers.health import router as health_router
from app.routers.imports import router as imports_router
from app.routers.documents import router as documents_router
from app.routers.upload_files import router as upload_files_router
from app.routers.cash_closures import router as cash_closures_router
from app.routers.auth import router as auth_router
from app.routers.bar_context import router as bar_context_router
from app.routers.admin import router as admin_router
from app.config import ensure_upload_dirs

app = FastAPI(title="Bar Margin Analyzer API")

ensure_upload_dirs()


@app.middleware("http")
async def disable_upload_caching(request, call_next):
    response = await call_next(request)
    if request.url.path == "/uploads" or request.url.path.startswith("/uploads/"):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        vary = response.headers.get("Vary", "")
        if "cookie" not in {value.strip().lower() for value in vary.split(",")}:
            response.headers.add_vary_header("Cookie")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
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
app.include_router(upload_files_router)
app.include_router(cash_closures_router)
app.include_router(auth_router)
app.include_router(bar_context_router)
app.include_router(admin_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Bar Margin Analyzer backend is running"}