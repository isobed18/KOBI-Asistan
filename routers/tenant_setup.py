from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agent.tenant_config import business_type_presets

router = APIRouter(prefix="/tenant-setup", tags=["tenant-setup"])


class BusinessSetupPreviewRequest(BaseModel):
    business_name: str
    business_type: str
    owner_notes: str | None = None


@router.get("/business-types")
def list_business_types():
    """Onboarding ekraninin gosterecegi isletme tipi presetleri."""
    return business_type_presets()


@router.post("/preview")
def preview_business_setup(body: BusinessSetupPreviewRequest):
    """Ilk kayit ekraninda LLM'e gitmeden config taslagi uretir.

    Demo icin dusuk maliyetli deterministic preview. Sonraki adimda bu taslak
    admin onayi ile tenant config dosyasina veya DB tenant ayarlarina yazilabilir.
    """
    presets = business_type_presets()
    preset = presets.get(body.business_type) or presets["genel"]
    return {
        "business_name": body.business_name,
        "business_type": body.business_type,
        "preset": preset,
        "config_preview": {
            "agent": {
                "personality": (
                    f"{body.business_name} icin sakin, satis odakli ve proaktif bir musteri asistanisin. "
                    "Sadece katalog ve isletme kurallarina dayanarak cevap ver."
                ),
                "rules": preset["agent_rules"],
            },
            "features": preset["features"],
            "recommended_metadata": preset["recommended_metadata"],
            "owner_notes": body.owner_notes,
        },
    }
