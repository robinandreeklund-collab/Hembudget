from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..chat.agent import ChatAgent
from ..db.models import ChatMessage
from ..llm.client import LMStudioClient
from .deps import db, llm_client, require_auth
from .schemas import ChatMessageIn

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_auth)])


@router.post("/send")
def send(
    payload: ChatMessageIn,
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> dict:
    agent = ChatAgent(session, llm=llm)
    answer = agent.ask(payload.session_id, payload.content)
    return {"session_id": payload.session_id, "answer": answer}


@router.get("/history/{session_id}")
def history(session_id: str, session: Session = Depends(db)) -> dict:
    rows = (
        session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return {
        "messages": [
            {"role": m.role, "content": m.content, "tool_calls": m.tool_calls,
             "created_at": m.created_at.isoformat()}
            for m in rows
        ]
    }


@router.get("/lm-studio-status")
def lm_status(llm: LMStudioClient = Depends(llm_client)) -> dict:
    return {"alive": llm.is_alive(), "base_url": llm.base_url, "model": llm.model}
