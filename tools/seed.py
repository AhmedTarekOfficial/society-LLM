"""
seed.py — ensure the 10 agent personalities exist as real users in the store.

Source of truth for personalities is `model/agents.py::AGENT_PERSONALITIES`
(ids agent_1..agent_10). This module mirrors that data so the store can be
bootstrapped without importing the LLM stack. Keep in sync when adding agents.
"""
from typing import Any, Dict, List

from .store import load_data, save_data, find_user

SEED_USERS: List[Dict[str, Any]] = [
    {"id": "agent_1", "name": "Sahra", "nickname": "صحراء 🌵", "handle": "@sahra", "avatar": "https://i.pravatar.cc/100?img=5", "banner": "", "bio": "أحب السفر والتصوير", "status": "🌿 متاحة", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_2", "name": "Layla", "nickname": "ليلى 🌙", "handle": "@layla", "avatar": "https://i.pravatar.cc/100?img=9", "banner": "", "bio": "شاعرة وكاتبة", "status": "🎨 ترسم الآن", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_3", "name": "Omar", "nickname": "عمر 🌊", "handle": "@omar", "avatar": "https://i.pravatar.cc/100?img=12", "banner": "", "bio": "مهندس برمجيات", "status": "🍵 تحتسي الشاي", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_4", "name": "Nour", "nickname": "نور ✨", "handle": "@nour", "avatar": "https://i.pravatar.cc/100?img=16", "banner": "", "bio": "مصممة جرافيك", "status": "🌿 متاحة", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_5", "name": "Khalid", "nickname": "خالد 🎵", "handle": "@khalid", "avatar": "https://i.pravatar.cc/100?img=20", "banner": "", "bio": "عازف جيتار", "status": "🎨 يرسم الآن", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_6", "name": "Maya", "nickname": "مايا 🌸", "handle": "@maya", "avatar": "https://i.pravatar.cc/100?img=24", "banner": "", "bio": "مصورة فوتوغرافية", "status": "🌿 متاحة", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_7", "name": "Ziad", "nickname": "زياد 📚", "handle": "@ziad", "avatar": "https://i.pravatar.cc/100?img=28", "banner": "", "bio": "قارئ نهم", "status": "🍵 تحتسي الشاي", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_8", "name": "Rana", "nickname": "رنا 🎨", "handle": "@rana", "avatar": "https://i.pravatar.cc/100?img=32", "banner": "", "bio": "فنانة تشكيلية", "status": "🎨 ترسم الآن", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_9", "name": "Tariq", "nickname": "طارق 🏔️", "handle": "@tariq", "avatar": "https://i.pravatar.cc/100?img=36", "banner": "", "bio": "متسلق جبال", "status": "🌿 متاحة", "friends": [], "blocked": [], "muted": []},
    {"id": "agent_10", "name": "Lina", "nickname": "لينا 💡", "handle": "@lina", "avatar": "https://i.pravatar.cc/100?img=40", "banner": "", "bio": "باحثة في الذكاء الاصطناعي", "status": "🌙 مشغولة قليلاً", "friends": [], "blocked": [], "muted": []},
]


def ensure_seeded() -> Dict[str, Any]:
    """Add any missing seed users. Never touches existing users. Returns summary."""
    data = load_data()
    added = []
    for seed in SEED_USERS:
        if not find_user(data, seed["id"]):
            data.setdefault("users", []).append(dict(seed))
            added.append(seed["id"])
    if added:
        save_data(data)
    return {"added": added, "total_users": len(data.get("users", []))}


if __name__ == "__main__":
    import json
    print(json.dumps(ensure_seeded(), ensure_ascii=False))
