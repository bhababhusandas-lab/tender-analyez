import asyncio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from app.core.llm.claude_client import chat
from app.agents.registry import get_system_prompt
from app.core.db.models import User
from app.core.document_extract import DocumentExtractionError, extract_document_text
from app.core.security.auth import get_current_user

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    agent_id: str
    messages: list[Message]


class ChatResponse(BaseModel):
    content: str
    agent_id: str


@router.post("/chat/extract-documents")
async def extract_chat_documents(
    files: list[UploadFile] = File(...),
    _user: User = Depends(get_current_user),
):
    """Extract temporary reference files for the AI Team chat.

    Nothing is saved to the vault: the returned text lives only in the current
    browser session and is sent to agents as untrusted reference context.
    """
    if not files or len(files) > 5:
        raise HTTPException(status_code=400, detail="Upload between 1 and 5 documents at a time")

    extracted = []
    total_bytes = 0
    for upload in files:
        raw = await upload.read()
        total_bytes += len(raw)
        if total_bytes > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Combined document size must be 25 MB or less")
        try:
            # Conversion/OCR can take a while; keep the event loop free.
            text = await asyncio.to_thread(
                extract_document_text, raw, upload.filename or "", upload.content_type or ""
            )
        except DocumentExtractionError as exc:
            raise HTTPException(status_code=400, detail=f"{upload.filename or 'Document'}: {exc}") from exc
        extracted.append({
            "name": upload.filename or "Document",
            "text": text[:50_000],
            "characters": min(len(text), 50_000),
        })
    return {"documents": extracted}


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty")

    system_prompt = get_system_prompt(request.agent_id)

    claude_messages = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
        if msg.role in ("user", "assistant")
    ]

    if not claude_messages or claude_messages[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="Last message must be from user")

    try:
        reply = chat(system_prompt=system_prompt, messages=claude_messages, agent_id=request.agent_id)
        return ChatResponse(content=reply, agent_id=request.agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
