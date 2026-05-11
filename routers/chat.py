"""
Chat API Endpoint — Auth-Aware + Prompt Police
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import json
import re

from langchain_core.messages import HumanMessage
from agent.graph import agent_graph
from agent.guard import check_message
from agent.auth import (
    set_session_scope,
    get_session_scope,
    activate_scope,
    validate_phone,
    validate_tracking_code,
)
from agent.intent_classifier import classify, fast_response
from agent.prompt import AUTH_REQUEST_PROMPT
from agent.scheduler import notification_queue

router = APIRouter(prefix="/api/v1", tags=["Chat"])


class ChatRequest(BaseModel):
    mesaj: str
    session_id: Optional[str] = None
    telefon: Optional[str] = None
    takip_kodu: Optional[str] = None


class ChatResponse(BaseModel):
    yanit: str
    session_id: str
    tool_calls: list = []
    auth_status: str = "none"  # none, authenticated, failed


def _extract_auth_from_message(message: str) -> dict:
    """Mesajdan telefon numarasi veya takip kodu cikarir."""
    result = {"telefon": None, "takip_kodu": None}

    # Takip kodu: SIP-XXXXXX
    code_match = re.search(r"SIP-[A-Z0-9]{6}", message, re.IGNORECASE)
    if code_match:
        result["takip_kodu"] = code_match.group(0).upper()
        return result

    # Telefon: 05XX ile baslayan 11 haneli
    phone_match = re.search(r"(05\d{9})", message)
    if phone_match:
        result["telefon"] = phone_match.group(1)
        return result

    return result


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Kullanici mesajini AI agent'a iletir. Auth ve prompt police uygular."""

    session_id = request.session_id or str(uuid.uuid4())

    # 1. Prompt Police
    police_result = check_message(request.mesaj)
    if not police_result.is_safe:
        return ChatResponse(
            yanit=police_result.reason,
            session_id=session_id,
            tool_calls=[],
            auth_status=_get_auth_status(session_id)
        )

    # 2. Auth: explicit parametreler veya mesajdan cikar
    telefon = request.telefon
    takip_kodu = request.takip_kodu

    if not telefon and not takip_kodu:
        extracted = _extract_auth_from_message(request.mesaj)
        telefon = extracted.get("telefon")
        takip_kodu = extracted.get("takip_kodu")

    # Yeni auth bilgisi geldiyse dogrula ve scope'u ayarla
    if telefon:
        if validate_phone(telefon):
            set_session_scope(session_id, telefon=telefon)
        else:
            return ChatResponse(
                yanit=f"'{telefon}' numarasi ile kayitli siparis bulunamadi. Lutfen siparis verirken kullandiginiz numarayi girin.",
                session_id=session_id,
                auth_status="failed"
            )
    elif takip_kodu:
        if validate_tracking_code(takip_kodu):
            set_session_scope(session_id, takip_kodu=takip_kodu)
        else:
            return ChatResponse(
                yanit=f"'{takip_kodu}' takip kodu bulunamadi. Lutfen gecerli bir takip kodu girin (SIP-XXXXXX).",
                session_id=session_id,
                auth_status="failed"
            )

    # 3. Scope'u aktif et
    activate_scope(session_id)

    # 4. Intent Classifier — basit sorgularda LLM bypass (~100ms, sifir maliyet)
    classified = classify(request.mesaj)
    if classified.bypass_llm:
        fast = fast_response(classified)
        if fast:
            return ChatResponse(
                yanit=fast,
                session_id=session_id,
                tool_calls=[{"tool": classified.intent, "input": classified.params}],
                auth_status=_get_auth_status(session_id),
            )

    # 5. LangGraph Agent
    config = {"configurable": {"thread_id": session_id}}

    try:
        result = agent_graph.invoke(
            {"messages": [HumanMessage(content=request.mesaj)]},
            config=config
        )

        tool_calls_info = []
        for msg in result["messages"]:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls_info.append({
                        "tool": tc["name"],
                        "input": tc["args"]
                    })

        final_message = result["messages"][-1].content

        return ChatResponse(
            yanit=final_message,
            session_id=session_id,
            tool_calls=tool_calls_info,
            auth_status=_get_auth_status(session_id)
        )
    except Exception as e:
        return ChatResponse(
            yanit=f"Bir hata olustu: {str(e)[:200]}",
            session_id=session_id,
            auth_status=_get_auth_status(session_id)
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE stream ile agent yanitini doner."""

    session_id = request.session_id or str(uuid.uuid4())

    # Prompt Police
    police_result = check_message(request.mesaj)
    if not police_result.is_safe:
        async def blocked():
            yield f"data: {json.dumps({'type': 'blocked', 'content': police_result.reason}, ensure_ascii=False)}\n\n"
        return StreamingResponse(blocked(), media_type="text/event-stream")

    # Auth extraction
    telefon = request.telefon
    takip_kodu = request.takip_kodu
    if not telefon and not takip_kodu:
        extracted = _extract_auth_from_message(request.mesaj)
        telefon = extracted.get("telefon")
        takip_kodu = extracted.get("takip_kodu")

    if telefon and validate_phone(telefon):
        set_session_scope(session_id, telefon=telefon)
    elif takip_kodu and validate_tracking_code(takip_kodu):
        set_session_scope(session_id, takip_kodu=takip_kodu)

    activate_scope(session_id)
    config = {"configurable": {"thread_id": session_id}}

    async def event_stream():
        try:
            for event in agent_graph.stream(
                {"messages": [HumanMessage(content=request.mesaj)]},
                config=config,
                stream_mode="updates"
            ):
                for node_name, node_output in event.items():
                    if node_name == "agent":
                        msg = node_output["messages"][-1]
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                yield f"data: {json.dumps({'type': 'tool_call', 'tool': tc['name'], 'input': tc['args']}, ensure_ascii=False)}\n\n"
                        elif msg.content:
                            yield f"data: {json.dumps({'type': 'response', 'content': msg.content, 'session_id': session_id, 'auth_status': _get_auth_status(session_id)}, ensure_ascii=False)}\n\n"
                    elif node_name == "tools":
                        msg = node_output["messages"][-1]
                        yield f"data: {json.dumps({'type': 'tool_result', 'content': msg.content[:500]}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)[:200]})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# -- Yardimci endpoint'ler --

@router.get("/notifications")
async def get_notifications(limit: int = 20):
    """Scheduler bildirimlerini doner."""
    return notification_queue[-limit:]


def _get_auth_status(session_id: str) -> str:
    scope = get_session_scope(session_id)
    if scope and (scope.get("telefon") or scope.get("takip_kodu")):
        return "authenticated"
    return "none"
