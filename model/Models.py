import asyncio
import random
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from prompts.promp import prompt
from tools.tools import TOOL_SCHEMAS


# Mix providers so a single quota outage does not silence the whole society.
# Verified working with the project's current API keys (Sep 2026):
#   - google_genai:gemini-flash-latest  (gemini-2.0-flash / 2.5-flash are retired)
#   - groq:openai/gpt-oss-20b / openai/gpt-oss-120b (llama-3.3-* names no longer exist)
# NOTE: openai:gpt-4o-mini was removed from rotation — the account has no credits
# left (HTTP 429). Add credits, then re-add it to MODEL_NAMES if desired.
# Groq gpt-oss-20b is the most reliable primary right now (free quota limits are
# per-model: gpt-oss-20b is separate from gpt-oss-120b, and both are cheaper than
# the Gemini quota which was exhausted during the burst test).
MODEL_NAMES = [
    "groq:openai/gpt-oss-20b",
    "groq:openai/gpt-oss-20b",
    "google_genai:gemini-flash-latest",
    "groq:openai/gpt-oss-20b",
    "groq:openai/gpt-oss-20b",
    "google_genai:gemini-flash-latest",
    "groq:openai/gpt-oss-20b",
    "groq:openai/gpt-oss-20b",
    "google_genai:gemini-flash-latest",
    "groq:openai/gpt-oss-20b",
]

# Tried in order when the primary model hits rate limits / outages.
FALLBACK_MODELS = [
    "groq:openai/gpt-oss-20b",
    "google_genai:gemini-flash-latest",
    "groq:openai/gpt-oss-120b",
]


API_SEMAPHORE = asyncio.Semaphore(3)


def _is_retryable_error(error_str: str) -> bool:
    e = error_str.lower()
    return any(
        s in e
        for s in (
            "429",
            "resource_exhausted",
            "503",
            "unavailable",
            "overloaded",
            "timeout",
            "timed out",
            "temporarily",
            "try again",
            "500",
            "502",
            "504",
            "rate_limit",
            "quota",
        )
    )


def _is_quota_exhausted(error_str: str) -> bool:
    """True when waiting/retrying the same model won't help soon (e.g. TPD)."""
    e = error_str.lower()
    return any(
        s in e
        for s in (
            "tokens per day",
            "tpd",
            "daily",
            "quota",
            "billing",
            "insufficient_quota",
        )
    )


def _candidate_models(primary: str) -> List[str]:
    ordered = [primary]
    for name in FALLBACK_MODELS:
        if name not in ordered:
            ordered.append(name)
    return ordered


async def run_one(
    name: str,
    user_prompt: str,
    messages: Optional[List[Any]] = None,
    max_retries: int = 2,
    timeout: float = 45.0,
) -> Dict[str, Any]:
    if messages is None:
        messages = [HumanMessage(content=user_prompt)]

    last_error = None
    for model_name in _candidate_models(name):
        try:
            model = init_chat_model(model_name, temperature=0.7)
            model_with_tools = model.bind_tools(TOOL_SCHEMAS)
        except Exception as e:
            last_error = f"Model init failed ({model_name}): {e}"
            print(f"[LLM] {last_error}")
            continue

        # One provider failing hard (model retired, bad key, no credits) must NOT
        # kill the whole call — fall through to the next provider in the list.
        succeeded = False
        for attempt in range(max_retries):
            try:
                async with API_SEMAPHORE:
                    response = await asyncio.wait_for(
                        model_with_tools.ainvoke(messages), timeout=timeout
                    )
                succeeded = True
                break
            except asyncio.TimeoutError:
                last_error = f"LLM timeout after {timeout}s ({model_name})"
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                break  # try next provider
            except Exception as e:
                last_error = str(e)
                if _is_retryable_error(last_error) and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                # Permanent failure for this provider (429 quota, 404 model,
                # 401 key, ...) -> move to the next provider, don't give up yet.
                break

        if not succeeded:
            if _is_quota_exhausted(str(last_error)):
                print(f"[LLM] Quota exhausted on {model_name}, trying fallback...")
            else:
                print(f"[LLM] {model_name} failed, trying fallback...")
            continue

        tool_calls = []
        raw_tool_calls = getattr(response, "tool_calls", None) or []
        for tc in raw_tool_calls:
            tool_calls.append(
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                }
            )

        if model_name != name:
            print(f"[LLM] Fell back from {name} -> {model_name}")

        return {
            "model": model_name,
            "content": _content_to_str(getattr(response, "content", "")),
            "tool_calls": tool_calls,
            "error": None,
        }

    return {
        "model": name,
        "content": "",
        "tool_calls": [],
        "error": last_error or "All models failed",
    }


def _content_to_str(raw: Any) -> str:
    """Normalize model content to plain text (some providers return block lists)."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for b in raw:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if isinstance(b.get("text"), str):
                    parts.append(b["text"])
            elif hasattr(b, "text") and isinstance(getattr(b, "text"), str):
                parts.append(getattr(b, "text"))
        return "".join(parts)
    return str(raw) if raw else ""


async def run_concurrent(model_names: List[str], user_prompt: str) -> List[Dict[str, Any]]:
    tasks = [run_one(name, user_prompt) for name in model_names]
    return await asyncio.gather(*tasks, return_exceptions=True)


def build_system_prompt() -> str:
    return (
        prompt
        + "\n\n"
        + "لديك صلاحية استخدام الأدوات التالية للتفاعل مع المنصة: "
        + "block_user, search_for_user, mute_user, send_friend_request, "
        + "remove_friend, create_group, create_server, update_profile_avatar, "
        + "update_profile_banner, update_profile_bio, update_profile_status, "
        + "send_message, reply_to_message, delete_message, list_users, get_profile."
        + "\n\n"
        + "كن إيجابياً، محترماً، وطبيعياً في تفاعلاتك."
    )
