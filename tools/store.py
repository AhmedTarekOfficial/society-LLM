"""
store.py — simple JSON persistence for Society
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List
import threading

# store file is next to this module
STORE_PATH = Path(__file__).parent / "data.json"
_lock = threading.Lock()

DEFAULT_DATA: Dict[str, Any] = {
    "users": [
        {"id": "me", "name": "Hana", "nickname": "هانا 🌸", "handle": "@hana", "avatar": "https://i.pravatar.cc/100?img=5", "banner": "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?w=800", "bio": "أحب الرسم تحت ضوء الشمس، وموسيقى Ghibli تملأ يومي.", "status": "🌿 متاحة", "friends": [], "blocked": [], "muted": []},
    ],
    "servers": [],
    "groups": [],
    "friend_requests": [],
    "messages": [],
    "current_user_id": "me"
}

def _ensure_store():
    if not STORE_PATH.exists():
        STORE_PATH.write_text(json.dumps(DEFAULT_DATA, ensure_ascii=False, indent=2), encoding="utf-8")

def load_data() -> Dict[str, Any]:
    _ensure_store()
    with _lock:
        try:
            text = STORE_PATH.read_text(encoding="utf-8")
            data = json.loads(text)
            # migrate missing keys
            for k, v in DEFAULT_DATA.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            # corrupted -> reset
            STORE_PATH.write_text(json.dumps(DEFAULT_DATA, ensure_ascii=False, indent=2), encoding="utf-8")
            return json.loads(json.dumps(DEFAULT_DATA))

def save_data(data: Dict[str, Any]) -> None:
    with _lock:
        STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def reset_data():
    save_data(json.loads(json.dumps(DEFAULT_DATA)))

def find_user(data: Dict[str, Any], user_id: str):
    for u in data.get("users", []):
        if u["id"] == user_id:
            return u
    return None

def find_user_by_query(data: Dict[str, Any], query: str):
    q = query.strip().lower()
    results = []
    for u in data.get("users", []):
        # search in name, nickname, handle, id
        hay = " ".join([u.get("name",""), u.get("nickname",""), u.get("handle",""), u.get("id","")]).lower()
        if q in hay:
            results.append(u)
    return results
