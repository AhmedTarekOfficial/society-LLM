from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage

from model.Models import run_one, build_system_prompt
from model import agents as agents_mod
from model.agents import AGENT_PERSONALITIES, stop_continuous

router = APIRouter(prefix="/agents", tags=["agents"])

_CHAT_HISTORY: Dict[str, List[Any]] = {}
_MODEL_FOR_AGENT: Dict[str, str] = {}

# Distribute models across the 10 personalities (round-robin).
from model.Models import MODEL_NAMES  # noqa: E402


def _model_for(agent_id: str) -> str:
    if agent_id not in _MODEL_FOR_AGENT:
        idx = next(
            (i for i, p in enumerate(AGENT_PERSONALITIES) if p.get("id") == agent_id),
            0,
        )
        _MODEL_FOR_AGENT[agent_id] = MODEL_NAMES[idx % len(MODEL_NAMES)]
    return _MODEL_FOR_AGENT[agent_id]


@router.get("/status")
def get_agents_status():
    return {
        "success": True,
        "running": agents_mod.AGENT_RUNNING,
        "cycle": agents_mod.CURRENT_CYCLE,
    }


@router.post("/stop")
def stop_agents():
    stop_continuous()
    return {"success": True, "message": "Agents stopped"}


@router.get("/list")
def list_agents():
    return {
        "success": True,
        "agents": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "nickname": p.get("nickname"),
                "model": _model_for(p.get("id")),
            }
            for p in AGENT_PERSONALITIES
        ],
    }


class ChatRequest(BaseModel):
    agent_id: str = Field(..., description="Personality id, e.g. 'agent_1'")
    message: str = Field(..., min_length=1)
    reset: Optional[bool] = False


@router.post("/chat")
async def chat_with_agent(req: ChatRequest):
    agent = next(
        (p for p in AGENT_PERSONALITIES if p.get("id") == req.agent_id), None
    )
    if not agent:
        return {"success": False, "error": f"Unknown agent: {req.agent_id}"}

    model_name = _model_for(req.agent_id)

    if req.reset or req.agent_id not in _CHAT_HISTORY:
        personality_block = (
            f"أنت الآن تلعب دور: {agent['name']} ({agent['nickname']}). "
            f"شخصيتك: {agent['personality']}\n"
            f"تكلّم بالعربية بأسلوب طبيعي وبشري، وجاوب بإيجاز.\n"
        )
        _CHAT_HISTORY[req.agent_id] = [
            {"role": "system", "content": build_system_prompt() + "\n\n" + personality_block}
        ]

    _CHAT_HISTORY[req.agent_id].append({"role": "user", "content": req.message})

    langchain_msgs: List[Any] = []
    for m in _CHAT_HISTORY[req.agent_id]:
        if m["role"] == "system":
            langchain_msgs.append(HumanMessage(content=m["content"]))
        elif m["role"] == "user":
            langchain_msgs.append(HumanMessage(content=m["content"]))
        else:
            langchain_msgs.append(AIMessage(content=m["content"]))

    result = await run_one(model_name, "", messages=langchain_msgs)

    if result.get("error"):
        return {
            "success": False,
            "agent_id": req.agent_id,
            "model": model_name,
            "error": result["error"],
        }

    reply = result.get("content", "") or ""
    _CHAT_HISTORY[req.agent_id].append({"role": "assistant", "content": reply})

    return {
        "success": True,
        "agent_id": req.agent_id,
        "agent_name": agent.get("name"),
        "nickname": agent.get("nickname"),
        "model": model_name,
        "reply": reply,
    }
