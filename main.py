from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database.db import init_db
from database.seed import seed
from routers import orders, products
from routers.chat import router as chat_router
from integrations.telegram_bot import setup_telegram, stop_telegram
from agent.scheduler import setup_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- Startup --
    init_db()
    seed()
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
