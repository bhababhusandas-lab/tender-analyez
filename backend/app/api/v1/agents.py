from fastapi import APIRouter
from app.agents.registry import AGENT_SYSTEM_PROMPTS

router = APIRouter()


@router.get("/agents")
async def list_agents():
    return {"agents": list(AGENT_SYSTEM_PROMPTS.keys()), "count": len(AGENT_SYSTEM_PROMPTS)}
