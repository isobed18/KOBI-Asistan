from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database.db import init_db
from database.seed import seed
from database.seed_users import seed as seed_users
from routers import orders, products
from routers.chat import router as chat_router
from routers.dashboard import router as dashboard_router
from routers.tickets import router as tickets_router
from routers.reports import router as reports_router
from routers.admin_chat import router as admin_chat_router
from routers.auth_router import router as auth_router
from routers.tenant_setup import router as tenant_setup_router
from integrations.telegram_bot import setup_telegram, stop_telegram
from agent.scheduler import setup_scheduler, stop_scheduler
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- Startup --
    init_db()
    seed()
    seed_users()
    print(
        f"[CONFIG] LLM_PROVIDER={settings.LLM_PROVIDER!r} "
        "(kabuktaki ortam degiskeni .env dosyasini ezer)"
    )
    print("[START] KOBI Asistan API baslatiliyor...")
    setup_scheduler()
    await setup_telegram()
    yield
    # -- Shutdown --
    stop_scheduler()
    await stop_telegram()


app = FastAPI(
    title="KOBI Asistan API",
    description="Kucuk isletmeler icin AI destekli siparis, stok ve kargo yonetimi",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router'lar
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(tickets_router)
app.include_router(reports_router)
app.include_router(admin_chat_router)
app.include_router(auth_router)
app.include_router(tenant_setup_router)

# Static files
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", tags=["Genel"])
def root():
    return {
        "mesaj": "KOBI Asistan API calisiyor",
        "version": "3.0.0",
        "docs": "/docs",
        "chat_ui": "/static/index.html",
        "endpoints": {
            "chat": "/api/v1/chat",
            "chat_stream": "/api/v1/chat/stream",
            "notifications": "/api/v1/notifications",
            "siparisler": "/orders",
            "urunler": "/products",
        },
    }
