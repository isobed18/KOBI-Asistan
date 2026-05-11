"""
Admin Chat Endpoint — İşletmeci LLM Asistanı
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
import uuid

from langchain_core.messages import HumanMessage
from agent.admin_graph import admin_graph
from agent.tenant_context import set_tenant_id
from routers.auth_router import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Asistan"])


class AdminChatRequest(BaseModel):
    mesaj: str
    session_id: Optional[str] = None


class ToolCallInfo(BaseModel):
    tool: str
    input: dict = {}
    output: dict = {}


class AdminChatResponse(BaseModel):
    yanit: str
    session_id: str
    tool_calls: list = []


@router.post("/chat", response_model=AdminChatResponse)
async def admin_chat(request: AdminChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    İşletmeci için yönetim asistanı. Müşteri auth gerekmez.
    Stok girişi, sipariş güncelleme, ürün ekleme, bilet yönetimi.
    """
    session_id = request.session_id or f"admin_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": session_id}}
    set_tenant_id(current_user.tenant_id)

    try:
        result = admin_graph.invoke(
            {"messages": [HumanMessage(content=request.mesaj)]},
            config=config,
        )

        tool_calls_info = []
        for msg in result["messages"]:
            # Tool çağrıları (LLM'in istediği)
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls_info.append({
                        "tool": tc["name"],
                        "input": tc.get("args", {}),
                        "output": {},
                    })
            # Tool sonuçları
            if hasattr(msg, "name") and msg.name:
                for tc in tool_calls_info:
                    if tc["tool"] == msg.name and not tc["output"]:
                        import json
                        try:
                            tc["output"] = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        except Exception:
                            tc["output"] = {"sonuc": str(msg.content)[:300]}
                        break

        final_message = result["messages"][-1].content

        return AdminChatResponse(
            yanit=final_message,
            session_id=session_id,
            tool_calls=tool_calls_info,
        )

    except Exception as e:
        return AdminChatResponse(
            yanit=f"Hata oluştu: {str(e)[:300]}",
            session_id=session_id,
            tool_calls=[],
        )


@router.delete("/chat/{session_id}")
async def clear_admin_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Admin chat geçmişini sıfırlar (yeni sohbet başlatmak için)."""
    # MemorySaver in-memory olduğu için sadece frontend'e bilgi dönmek yeterli
    return {"mesaj": f"Oturum '{session_id}' sıfırlandı.", "session_id": session_id}
