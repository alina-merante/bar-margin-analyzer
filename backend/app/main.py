from fastapi import FastAPI

from app.routers.health import router as health_router

app = FastAPI(title="Bar Margin Analyzer API")
app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Bar Margin Analyzer backend is running"}
