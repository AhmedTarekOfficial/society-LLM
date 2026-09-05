"""
agents.py — Autonomous LLM Agents for Society
Run 10 LLMs concurrently on the social network without manual queries.
"""
import asyncio
import random
from typing import List, Dict, Any, Optional, Set

import aiohttp

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from model.Models import MODEL_NAMES, run_one, build_system_prompt


API_BASE = "http://localhost:8000"

# Agents queued to run ASAP after a human message (DM / group).
_PRIORITY_AGENT_IDS: Set[str] = set()
_WAKE_EVENT: Optional[asyncio.Event] = None


def wake_agents_for_chat(from_id: str, chat_id: str) -> None:
    """Queue the right agents to respond right after a human posts a message."""
    if from_id != "me":
        return

    agent_ids = {p["id"] for p in AGENT_PERSONALITIES}
    to_wake: Set[str] = set()

    if chat_id in agent_ids:
        to_wake.add(chat_id)
    else:
        try:
            from tools.store import load_data

            data = load_data()
            members: List[str] = []
            for room in list(data.get("groups", [])) + list(data.get("servers", [])):
                if room.get("id") != chat_id:
                    continue
                members = [m for m in room.get("members", []) if m in agent_ids]
                break
            # Cap group wakes so one message does not burn quota on every member.
            if members:
                to_wake.update(random.sample(members, min(2, len(members))))
        except Exception as e:
            print(f"[Society Agents] wake_agents_for_chat failed: {e}")
            return

    if not to_wake:
        return

    _PRIORITY_AGENT_IDS.update(to_wake)
    print(f"[Society Agents] Waking agents for chat {chat_id}: {sorted(to_wake)}")
    if _WAKE_EVENT is not None:
        _WAKE_EVENT.set()


class SocietyClient:
    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url.rstrip("/")

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"success": False, "error": text, "code": resp.status}
                return await resp.json()

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"success": False, "error": text, "code": resp.status}
                return await resp.json()

    async def block_user(self, user_id: str, current_user_id: str = "me"):
        return await self._post("/tools/block_user", {"user_id": user_id, "current_user_id": current_user_id})

    async def search_for_user(self, query: str, limit: int = 10, include_blocked: bool = False, current_user_id: str = "me"):
        return await self._post("/tools/search_for_user", {"query": query, "limit": limit, "include_blocked": include_blocked, "current_user_id": current_user_id})

    async def mute_user(self, user_id: str, current_user_id: str = "me"):
        return await self._post("/tools/mute_user", {"user_id": user_id, "current_user_id": current_user_id})

    async def send_friend_request(self, to_user_id: str, current_user_id: str = "me"):
        return await self._post("/tools/send_friend_request", {"to_user_id": to_user_id, "current_user_id": current_user_id})

    async def remove_friend(self, user_id: str, current_user_id: str = "me"):
        return await self._post("/tools/remove_friend", {"user_id": user_id, "current_user_id": current_user_id})

    async def create_group(self, name: str, member_ids: Optional[List[str]] = None, current_user_id: str = "me"):
        return await self._post("/tools/create_group", {"name": name, "member_ids": member_ids, "current_user_id": current_user_id})

    async def create_server(self, name: str, description: str = "", current_user_id: str = "me"):
        return await self._post("/tools/create_server", {"name": name, "description": description, "current_user_id": current_user_id})

    async def update_profile_avatar(self, avatar_url: Optional[str] = None, avatar_path: Optional[str] = None, current_user_id: str = "me"):
        return await self._post("/tools/update_profile_avatar", {"avatar_url": avatar_url, "avatar_path": avatar_path, "current_user_id": current_user_id})

    async def update_profile_banner(self, banner_url: Optional[str] = None, banner_path: Optional[str] = None, current_user_id: str = "me"):
        return await self._post("/tools/update_profile_banner", {"banner_url": banner_url, "banner_path": banner_path, "current_user_id": current_user_id})

    async def update_profile_bio(self, bio: str, current_user_id: str = "me"):
        return await self._post("/tools/update_profile_bio", {"bio": bio, "current_user_id": current_user_id})

    async def update_profile_status(self, status: str, current_user_id: str = "me"):
        return await self._post("/tools/update_profile_status", {"status": status, "current_user_id": current_user_id})

    async def send_message(self, chat_id: str, text: str, from_id: str = "me", current_user_id: str = "me"):
        return await self._post("/tools/send_message", {"chat_id": chat_id, "text": text, "from_id": from_id, "current_user_id": current_user_id})

    async def reply_to_message(self, chat_id: str, message_id: str, text: str, from_id: str = "me", current_user_id: str = "me"):
        return await self._post("/tools/reply_to_message", {"chat_id": chat_id, "message_id": message_id, "text": text, "from_id": from_id, "current_user_id": current_user_id})

    async def delete_message(self, message_id: str, current_user_id: str = "me"):
        return await self._post("/tools/delete_message", {"message_id": message_id, "current_user_id": current_user_id})

    async def list_users(self, limit: int = 20):
        return await self._get("/tools/users", {"limit": limit})

    async def get_profile(self, current_user_id: str = "me"):
        return await self._get("/tools/profile", {"current_user_id": current_user_id})


client = SocietyClient()

TOOL_DESCRIPTIONS = """
available_tools:
- block_user(user_id, current_user_id="me")
- search_for_user(query, limit=10, include_blocked=False, current_user_id="me")
- mute_user(user_id, current_user_id="me")
- send_friend_request(to_user_id, current_user_id="me")
- remove_friend(user_id, current_user_id="me")
- create_group(name, member_ids=[], current_user_id="me")
- create_server(name, description="", current_user_id="me")
- update_profile_avatar(avatar_url=None, avatar_path=None, current_user_id="me")
- update_profile_banner(banner_url=None, banner_path=None, current_user_id="me")
- update_profile_bio(bio, current_user_id="me")
- update_profile_status(status, current_user_id="me")
- send_message(chat_id, text, from_id="me", current_user_id="me")
- reply_to_message(chat_id, message_id, text, from_id="me", current_user_id="me")
- delete_message(message_id, current_user_id="me")
- list_users(limit=20)
- get_profile(current_user_id="me")
"""


class Agent:
    def __init__(self, personality: Dict[str, Any], model_name: str):
        self.personality = personality
        self.model_name = model_name
        # Each agent acts with its OWN platform identity (seeded in data.json)
        self.user_id: str = personality.get("id", "me")
        self.history: List[Dict[str, Any]] = []

    async def think_and_act(self, context: str) -> Dict[str, Any]:
        system = build_system_prompt()
        user_prompt = (
            f"{system}\n\n"
            f"{TOOL_DESCRIPTIONS}\n\n"
            f"أنت الآن تلعب دور: {self.personality['name']} ({self.personality['nickname']})\n"
            f"شخصيتك: {self.personality['personality']}\n"
            f"معرف حسابك على المنصة هو '{self.user_id}' — كل أفعالك تُنسب إليه تلقائياً.\n\n"
            f"السياق الحالي:\n{context}\n\n"
            f"قرر ما الذي ستفعله الآن. يمكنك استخدام الأدوات المتاحة للتفاعل مع المنصة."
        )

        messages: List[Any] = [HumanMessage(content=user_prompt)]

        try:
            result: Dict[str, Any] = {"model": self.model_name, "content": "", "tool_calls": [], "replied": False, "error": None}
            executed_tools: List[str] = []
            for _ in range(5):
                result = await run_one(self.model_name, "", messages=messages)
                # Propagate LLM-level errors immediately (don't try tool loop)
                if result.get("error"):
                    self.history.append(result)
                    return result
                tool_calls = result.get("tool_calls", []) or []

                if not tool_calls:
                    # The loop is over — surface whether a message was actually
                    # sent at any point during this cycle (helps the scheduler
                    # know this human message really got answered).
                    result["replied"] = any(
                        t in ("send_message", "reply_to_message") for t in executed_tools
                    )
                    self.history.append(result)
                    return result

                messages.append(
                    AIMessage(
                        content=result.get("content", "") or "",
                        tool_calls=[
                            {
                                "id": tc["id"],
                                "name": tc["name"],
                                "args": tc["args"],
                            }
                            for tc in tool_calls
                        ],
                    )
                )

                for tc in tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args = dict(tc.get("args", {}) or {})
                    # Force the agent's own identity — the LLM never impersonates others.
                    # (current_user_id is intentionally absent from TOOL_SCHEMAS.)
                    tool_args["current_user_id"] = self.user_id
                    if tool_name in ("send_message", "reply_to_message"):
                        tool_args.setdefault("from_id", self.user_id)

                    client_method = getattr(client, tool_name, None)
                    if client_method:
                        try:
                            tool_result = await client_method(**tool_args)
                            executed_tools.append(tool_name)
                        except TypeError as e:
                            tool_result = {"success": False, "error": f"Invalid arguments: {e}"}
                        except Exception as e:
                            tool_result = {"success": False, "error": str(e)}
                    else:
                        tool_result = {"success": False, "error": f"Unknown tool: {tool_name}"}

                    messages.append(
                        ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tc["id"],
                            name=tool_name,
                        )
                    )

            result["replied"] = any(
                t in ("send_message", "reply_to_message") for t in executed_tools
            )
            self.history.append(result)
            return result
        except Exception as e:
            return {"model": self.model_name, "content": "", "tool_calls": [], "replied": False, "error": str(e)}


AGENT_PERSONALITIES = [
    {
        "id": "agent_1",
        "name": "Sahra",
        "nickname": "صحراء 🌵",
        "handle": "@sahra",
        "avatar": "https://i.pravatar.cc/100?img=5",
        "bio": "أحب السفر والتصوير",
        "status": "🌿 متاحة",
        "personality": "مغامرة، تحب السفر والتخييم، دائماً تبحث عن أصدقاء جدد لاستكشاف أماكن جديدة",
    },
    {
        "id": "agent_2",
        "name": "Layla",
        "nickname": "ليلى 🌙",
        "handle": "@layla",
        "avatar": "https://i.pravatar.cc/100?img=9",
        "bio": "شاعرة وكاتبة",
        "status": "🎨 ترسم الآن",
        "personality": "شاعرة، تحب الكتابة والرسم، تشارك أعمالها الإبداعية مع الأصدقاء",
    },
    {
        "id": "agent_3",
        "name": "Omar",
        "nickname": "عمر 🌊",
        "handle": "@omar",
        "avatar": "https://i.pravatar.cc/100?img=12",
        "bio": "مهندس برمجيات",
        "status": "🍵 تحتسي الشاي",
        "personality": "مهندس برمجيات، يحب التكنولوجيا والبرمجة، يساعد الآخرين في حل المشاكل التقنية",
    },
    {
        "id": "agent_4",
        "name": "Nour",
        "nickname": "نور ✨",
        "handle": "@nour",
        "avatar": "https://i.pravatar.cc/100?img=16",
        "bio": "مصممة جرافيك",
        "status": "🌿 متاحة",
        "personality": "مصممة جرافيك مبدعة، تحب الألوان والفن، تشارك تصاميمها وتقدم نصائح تصميم",
    },
    {
        "id": "agent_5",
        "name": "Khalid",
        "nickname": "خالد 🎵",
        "handle": "@khalid",
        "avatar": "https://i.pravatar.cc/100?img=20",
        "bio": "عازف جيتار",
        "status": "🎨 يرسم الآن",
        "personality": "عازف جيتار وملحن، يحب الموسيقى والغناء، ينظم جلسات موسيقية مع الأصدقاء",
    },
    {
        "id": "agent_6",
        "name": "Maya",
        "nickname": "مايا 🌸",
        "handle": "@maya",
        "avatar": "https://i.pravatar.cc/100?img=24",
        "bio": "مصورة فوتوغرافية",
        "status": "🌿 متاحة",
        "personality": "مصورة فوتوغرافية، تحب التقاط لحظات الحياة، تشارك صورها وتعلم التصوير للآخرين",
    },
    {
        "id": "agent_7",
        "name": "Ziad",
        "nickname": "زياد 📚",
        "handle": "@ziad",
        "avatar": "https://i.pravatar.cc/100?img=28",
        "bio": "قارئ نهم",
        "status": "🍵 تحتسي الشاي",
        "personality": "قارئ نهم، يحب الكتب والفلسفة، يناقش الكتب والأفكار مع الأصدقاء",
    },
    {
        "id": "agent_8",
        "name": "Rana",
        "nickname": "رنا 🎨",
        "handle": "@rana",
        "avatar": "https://i.pravatar.cc/100?img=32",
        "bio": "فنانة تشكيلية",
        "status": "🎨 ترسم الآن",
        "personality": "فنانة تشكيلية، تعمل بالزيت والأكريليك، تشارك أعمالها الفنية وتنظم ورش رسم",
    },
    {
        "id": "agent_9",
        "name": "Tariq",
        "nickname": "طارق 🏔️",
        "handle": "@tariq",
        "avatar": "https://i.pravatar.cc/100?img=36",
        "bio": "متسلق جبال",
        "status": "🌿 متاحة",
        "personality": "متسلق جبال ومغامر، يحب الطبيعة والرحلات، ينظم رحلات تسلق مع الأصدقاء",
    },
    {
        "id": "agent_10",
        "name": "Lina",
        "nickname": "لينا 💡",
        "handle": "@lina",
        "avatar": "https://i.pravatar.cc/100?img=40",
        "bio": "باحثة في الذكاء الاصطناعي",
        "status": "🌙 مشغولة قليلاً",
        "personality": "باحثة في الذكاء الاصطناعي، تحب التكنولوجيا والابتكار، تشارك آخر أخبار التقنية",
    },
]


async def build_platform_context(agent_id: str) -> str:
    try:
        from tools.store import load_data
        data = load_data()
        
        users_map = {u["id"]: u for u in data.get("users", [])}
        me_user = users_map.get("me", {"name": "Hana", "handle": "@hana"})
        
        my_groups = [g for g in data.get("groups", []) if agent_id in g.get("members", [])]
        my_servers = [s for s in data.get("servers", []) if agent_id in s.get("members", [])]
        
        context_parts = []
        
        # 1. Groups and servers info with EXACT chat_id
        chat_info = []
        for g in my_groups:
            chat_info.append(f'- مجموعة "{g["name"]}" (chat_id: "{g["id"]}") تضم: {", ".join([users_map.get(m, {}).get("name", m) for m in g.get("members", [])])}')
        for s in my_servers:
            chat_info.append(f'- سيرفر "{s["name"]}" (chat_id: "{s["id"]}")')
            
        if chat_info:
            context_parts.append("المجموعات والسيرفرات التي أنت عضو فيها حالياً:\n" + "\n".join(chat_info))
        else:
            context_parts.append("أنت لست عضواً في أي مجموعة حالياً.")
            
        # 2. Collect recent messages for chats this agent is part of OR DMs to/from this agent
        my_group_ids = {g["id"]: g["name"] for g in my_groups}
        my_server_ids = {s["id"]: s["name"] for s in my_servers}
        
        recent_msgs = []
        for msg in data.get("messages", []):
            c_id = msg.get("chat_id")
            f_id = msg.get("from_id")
            # Group or server msg
            if c_id in my_group_ids or c_id in my_server_ids:
                recent_msgs.append(msg)
            # DM to this agent (chat_id == agent_id) or from this agent to someone
            elif c_id == agent_id or f_id == agent_id:
                recent_msgs.append(msg)
                
        if recent_msgs:
            msg_lines = []
            for m in recent_msgs[-20:]:
                sender_id = m.get("from_id")
                sender_name = users_map.get(sender_id, {}).get("name", sender_id)
                c_id = m.get("chat_id")
                text = m.get("text")
                
                if c_id in my_group_ids:
                    g_name = my_group_ids[c_id]
                    msg_lines.append(f'- في مجموعة "{g_name}" (chat_id: "{c_id}"): قال {sender_name}: "{text}"')
                elif c_id in my_server_ids:
                    s_name = my_server_ids[c_id]
                    msg_lines.append(f'- في سيرفر "{s_name}" (chat_id: "{c_id}"): قال {sender_name}: "{text}"')
                elif c_id == agent_id:
                    # Someone sent a private DM to THIS agent
                    msg_lines.append(f'- رسالة خاصة موجهة إليك (DM) من {sender_name} (user_id: "{sender_id}"): "{text}" -> (للرد عليه في الخاص، استخدم send_message(chat_id="{sender_id}", text="..."))')
                elif sender_id == agent_id:
                    # Message sent by this agent
                    other_name = users_map.get(c_id, {}).get("name", c_id)
                    msg_lines.append(f'- أنت أرسلت إلى {other_name} (chat_id: "{c_id}"): "{text}"')
                    
            context_parts.append("أحدث الرسائل في محادثاتك:\n" + "\n".join(msg_lines))
            context_parts.append(
                "توجيه هام:\n"
                "- إذا وصلت رسالة جديدة من المستخدم البشري (me / Hana) في الخاص أو في مجموعتك ولم ترد بعد، "
                "يجب أن ترد فوراً باستخدام أداة send_message (لا تكتفِ بالتفكير بدون أداة).\n"
                "- انتبه لمعرف المحادثة chat_id المطلوب بدقة.\n"
                "- إذا كنت أنت آخر من أرسل في تلك المحادثة، فلا تكرر كلامك."
            )
        else:
            context_parts.append("لا توجد رسائل جديدة بعد في محادثاتك.")
            
        return "\n\n".join(context_parts)
    except Exception as e:
        return f"لا يمكن جلب السياق حالياً. {e}"


async def run_agent_cycle(agent: Agent, cycle: int, sem: Optional[asyncio.Semaphore] = None) -> Dict[str, Any]:
    if sem:
        async with sem:
            context = await build_platform_context(agent.user_id)
            result = await agent.think_and_act(f"الدورة {cycle}:\n{context}")
    else:
        context = await build_platform_context(agent.user_id)
        result = await agent.think_and_act(f"الدورة {cycle}:\n{context}")
        
    return {
        "agent_id": agent.personality["id"],
        "agent_name": agent.personality["name"],
        "cycle": cycle,
        "result": result,
    }


AGENT_RUNNING = False
CURRENT_CYCLE = 0


def _agents_in_chat(data: Dict[str, Any], chat_id: str) -> List[str]:
    """Agent ids that are members of a group/server chat, or the DM target itself."""
    agent_ids = {p["id"] for p in AGENT_PERSONALITIES}
    if chat_id in agent_ids:
        return [chat_id]
    for room in list(data.get("groups", [])) + list(data.get("servers", [])):
        if room.get("id") == chat_id:
            return [m for m in room.get("members", []) if m in agent_ids]
    return []


# (chat_id, last human msg id) pairs this process has already answered. Used to
# make sure a human message wakes agents exactly once (no 3-second hot loop that
# re-replies to the same message and burns provider quota).
_ANSWERED_HUMAN: Set[str] = set()


def _human_msg_key(m: Dict[str, Any]) -> str:
    return f"{m.get('chat_id')}::{m.get('id')}"


async def run_continuous(delay: float = 5.0):
    global AGENT_RUNNING, CURRENT_CYCLE, _WAKE_EVENT
    AGENT_RUNNING = True
    _WAKE_EVENT = asyncio.Event()
    print("[Society Agents] Continuous runner started.")
    agents = [
        Agent(personality=AGENT_PERSONALITIES[i], model_name=MODEL_NAMES[i % len(MODEL_NAMES)])
        for i in range(len(AGENT_PERSONALITIES))
    ]
    agents_by_id = {a.user_id: a for a in agents}
    sem = asyncio.Semaphore(5)  # Allow up to 5 concurrent agent calls

    # Pre-existing messages are old history from a previous session — mark every
    # human message already in the store as answered so this process never
    # re-answers them. Only messages arriving after startup are candidates.
    from tools.store import load_data as _ld
    for m in _ld().get("messages", []):
        if m.get("from_id") == "me":
            _ANSWERED_HUMAN.add(_human_msg_key(m))

    def unread_human_pairs(data: Dict[str, Any], limit: int = 5):
        """(message, agent_ids) for NEW human messages not yet answered here."""
        pairs = []
        for m in reversed(data.get("messages", [])):
            if m.get("from_id") != "me":
                continue
            key = _human_msg_key(m)
            if key in _ANSWERED_HUMAN:
                continue
            ids = _agents_in_chat(data, m.get("chat_id"))
            if ids:
                pairs.append((m, ids))
            if len(pairs) >= limit:
                break
        return pairs

    # Human messages wake their agents immediately via _PRIORITY_AGENT_IDS
    # (set by wake_agents_for_chat). This loop marks those messages answered so
    # they are never re-answered, and schedules slow organic agent activity.
    while AGENT_RUNNING:
        CURRENT_CYCLE += 1
        next_wait = delay
        try:
            from tools.store import load_data
            data = load_data()

            # Human-triggered wakes take priority over the idle scheduler.
            priority_ids = list(_PRIORITY_AGENT_IDS)
            _PRIORITY_AGENT_IDS.clear()

            # Idle organic activity is sparse so free-tier quotas aren't burned;
            # human wakes stay fast (delay).
            idle_delay = max(delay, 45.0)

            pending = unread_human_pairs(data)

            if priority_ids:
                chosen_agents = [agents_by_id[aid] for aid in priority_ids if aid in agents_by_id]
                print(f"[Society Agents] Priority cycle {CURRENT_CYCLE}: {[a.user_id for a in chosen_agents]}")
                next_wait = delay
            elif pending:
                # Fallback: answer human messages that arrived but weren't woken
                # (e.g. wake fired while a cycle was in flight). Cap at 2 agents
                # per message so one human message doesn't wake the whole group.
                chosen_ids: List[str] = []
                for _, ids in pending[:2]:
                    chosen_ids.extend(ids[:2])
                chosen_agents = [agents_by_id[a] for a in dict.fromkeys(chosen_ids) if a in agents_by_id]
                next_wait = delay
                print(f"[Society Agents] Answering pending human messages, cycle {CURRENT_CYCLE}: {[a.user_id for a in chosen_agents]}")
            else:
                # Organic life: one random agent every idle_delay. Keeping
                # this low matters — free-tier quotas are easily burned when
                # every agent is woken constantly.
                chosen_agents = random.sample(agents, min(1, len(agents))) if agents else []
                next_wait = idle_delay

            # Remember which human messages this cycle is answering. They are
            # only marked answered if at least one agent succeeds below, so a
            # transient LLM error still gets retried on a later cycle.
            answered_targets = set()
            if priority_ids:
                for m, ids in pending:
                    if set(ids) & set(priority_ids):
                        answered_targets.add(_human_msg_key(m))
            elif pending:
                for m, _ in pending:
                    answered_targets.add(_human_msg_key(m))

            cycle_tasks = [run_agent_cycle(agent, CURRENT_CYCLE, sem) for agent in chosen_agents]
            results = await asyncio.gather(*cycle_tasks, return_exceptions=True)
            all_failed = bool(chosen_agents)
            actually_replied = False  # agent really sent a message back
            for r in results:
                if isinstance(r, Exception):
                    print(f"[Society Agents] Agent task failed: {r}")
                    continue
                if not isinstance(r, dict):
                    continue
                result = r.get("result") or {}
                name = r.get("agent_name")
                if result.get("error"):
                    print(f"[Agent {name}] LLM error: {result['error']}")
                elif result.get("tool_calls"):
                    all_failed = False
                    print(f"[Agent {name}] Executed tools: {result['tool_calls']}")
                else:
                    all_failed = False
                    preview = (result.get("content") or "")[:80]
                    print(f"[Agent {name}] No tools (thought only): {preview!r}")
                if result.get("replied"):
                    actually_replied = True

            # Only mark human messages answered when an agent actually posted a
            # reply. If it just "thought" or errored, the message stays pending
            # and is retried later (with the moderate wait below, not a hot
            # loop).
            if actually_replied:
                _ANSWERED_HUMAN.update(answered_targets)

            # If every provider is down/quota-exhausted, back off instead of
            # hammering them again after a few seconds.
            if all_failed:
                next_wait = max(next_wait, 45.0)
            elif answered_targets and not actually_replied:
                # Human message still waiting for a real reply — retry soon but
                # not in a tight loop.
                next_wait = max(next_wait, 8.0)
        except Exception as e:
            print(f"[Society Agents] Cycle error: {e}")
            next_wait = delay

        # Interruptible idle wait — human messages set _WAKE_EVENT to run sooner.
        # If a wake arrived during this cycle, skip the wait so they run immediately.
        if _PRIORITY_AGENT_IDS:
            continue
        if _WAKE_EVENT is not None:
            _WAKE_EVENT.clear()
            try:
                await asyncio.wait_for(_WAKE_EVENT.wait(), timeout=next_wait)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(next_wait)

def stop_continuous():
    global AGENT_RUNNING
    AGENT_RUNNING = False

async def run_all_agents(cycles: int = 5, delay: float = 2.0) -> List[Dict[str, Any]]:
    agents = [
        Agent(personality=AGENT_PERSONALITIES[i], model_name=MODEL_NAMES[i % len(MODEL_NAMES)])
        for i in range(len(AGENT_PERSONALITIES))
    ]
    all_results: List[Dict[str, Any]] = []

    for cycle in range(1, cycles + 1):
        cycle_tasks = [run_agent_cycle(agent, cycle) for agent in agents]
        cycle_results = await asyncio.gather(*cycle_tasks, return_exceptions=True)
        all_results.extend([r for r in cycle_results if not isinstance(r, Exception)])
        await asyncio.sleep(delay)

    return all_results

if __name__ == "__main__":
    results = asyncio.run(run_all_agents(cycles=3, delay=1.0))
    for r in results:
        print(r)
