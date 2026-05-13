from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from agent.tenant_config import business_type_presets
from config import settings
from routers.auth_router import CurrentUser, get_current_user
from services.visual_stock_ingestion import (
    approve_candidate,
    claim_setup_batch,
    create_batch,
    duplicate_candidate_product,
    list_batch_candidates,
    reject_candidate,
    save_upload_to_batch,
    search_by_uploaded_image,
)

router = APIRouter(prefix="/visual-stock", tags=["visual-stock"])


class CandidateApproveRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    price: float | None = None
    stock_quantity: int | None = None
    low_stock_threshold: int | None = None
    visual_keywords: str | None = None
    description: str | None = None
    ingredients: str | None = None
    allergens: str | None = None
    size_guide: str | None = None
    advisory_notes: str | None = None


class CandidateRejectRequest(BaseModel):
    reason: str | None = None


@router.get("/capabilities")
def capabilities():
    return {
        "modes": {
            "demo": "filename + visual_keywords fallback, no model cost",
            "clip": "sentence-transformers CLIP if installed/loaded",
            "fashion": "business_type=giyim tries FASHION_CLIP_MODEL first, then GENERAL_CLIP_MODEL",
            "future": "SigLIP/ChromaDB can replace SQLite vector store",
        },
        "models": {
            "fashion_clip": settings.FASHION_CLIP_MODEL,
            "general_clip": settings.GENERAL_CLIP_MODEL,
        },
        "business_type_presets": business_type_presets(),
    }


@router.post("/batches")
async def upload_visual_stock_batch(
    business_type: str = Form("giyim"),
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="En az bir gorsel yukleyin.")
    batch_id = create_batch(current_user.tenant_id, business_type, current_user.id)
    candidates = []
    for file in files:
        if not (file.content_type or "").startswith("image/"):
            continue
        candidates.append(
            save_upload_to_batch(
                batch_id,
                current_user.tenant_id,
                file.filename or "urun.jpg",
                file.file,
                business_type,
            )
        )
    if not candidates:
        raise HTTPException(status_code=400, detail="Gecerli image dosyasi bulunamadi.")
    return {
        "batch_id": batch_id,
        "status": "pending_review",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


@router.post("/setup/batches")
async def upload_visual_stock_setup_batch(
    business_type: str = Form("giyim"),
    files: list[UploadFile] = File(...),
):
    """Public onboarding upload.

    The batch is kept under tenant_id=0 until the final signup step creates the
    real tenant. It lets the wizard classify images before persisting an account.
    """
    if not files:
        raise HTTPException(status_code=400, detail="En az bir gorsel yukleyin.")
    batch_id = create_batch(0, business_type, None)
    candidates = []
    for file in files:
        if not (file.content_type or "").startswith("image/"):
            continue
        candidates.append(
            save_upload_to_batch(
                batch_id,
                0,
                file.filename or "urun.jpg",
                file.file,
                business_type,
            )
        )
    if not candidates:
        raise HTTPException(status_code=400, detail="Gecerli image dosyasi bulunamadi.")
    return {
        "batch_id": batch_id,
        "status": "pending_review",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, current_user: CurrentUser = Depends(get_current_user)):
    return {
        "batch_id": batch_id,
        "candidates": list_batch_candidates(batch_id, current_user.tenant_id),
    }


@router.post("/batches/{batch_id}/claim")
def claim_visual_setup_batch(batch_id: int, current_user: CurrentUser = Depends(get_current_user)):
    out = claim_setup_batch(batch_id, current_user.tenant_id, current_user.id)
    if out.get("hata"):
        raise HTTPException(status_code=404, detail=out["hata"])
    return out


@router.post("/candidates/{candidate_id}/approve")
def approve_visual_candidate(
    candidate_id: int,
    body: CandidateApproveRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    out = approve_candidate(candidate_id, current_user.tenant_id, body.model_dump(exclude_unset=True))
    if out.get("hata"):
        raise HTTPException(status_code=404, detail=out["hata"])
    return out


@router.post("/candidates/{candidate_id}/reject")
def reject_visual_candidate(
    candidate_id: int,
    body: CandidateRejectRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    out = reject_candidate(candidate_id, current_user.tenant_id, body.reason)
    if out.get("hata"):
        raise HTTPException(status_code=404, detail=out["hata"])
    return out


@router.post("/candidates/{candidate_id}/duplicate")
def duplicate_visual_candidate(
    candidate_id: int,
    body: CandidateApproveRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    out = duplicate_candidate_product(candidate_id, current_user.tenant_id, body.model_dump(exclude_unset=True))
    if out.get("hata"):
        raise HTTPException(status_code=404, detail=out["hata"])
    return out


@router.post("/search")
async def visual_product_search(
    business_type: str = Form("giyim"),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Image dosyasi gerekli.")
    return search_by_uploaded_image(
        current_user.tenant_id,
        file.filename or "search.jpg",
        file.file,
        business_type,
    )
