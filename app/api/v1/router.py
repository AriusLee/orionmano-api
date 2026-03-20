from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.companies import router as companies_router
from app.api.v1.documents import router as documents_router
from app.api.v1.reports import router as reports_router
from app.api.v1.chat import router as chat_router
from app.api.v1.decks import router as decks_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(companies_router)
v1_router.include_router(documents_router)
v1_router.include_router(reports_router)
v1_router.include_router(chat_router)
v1_router.include_router(decks_router)
