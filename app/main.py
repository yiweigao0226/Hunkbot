import logging
from fastapi import FastAPI
from app.api.webhook import router as webhook_router
from app.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

app = FastAPI(
    title="PR Review Bot",
    description="AI-powered GitHub PR reviewer",
    version="0.1.0",
)

app.include_router(webhook_router, prefix="/github")


@app.get("/health")
async def health():
    return {"status": "ok"}
