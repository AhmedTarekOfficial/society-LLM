"""
tools.py — 11 core functions for AI agents
Each function mimics the UI actions and persists to store.py (JSON file).
Return format is always: {"success": bool, "data": ..., "error": ...}
"""
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from .store import load_data, save_data, find_user, find_user_by_query, STORE_PATH

# ---------- helpers ----------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ok(data=None, message=""):
    return {"success": True, "data": data, "message": message}

def _fail(error, code=400):
    return {"success": False, "error": error, "code": code}

def _current_user(data):
    cid = data.get("current_user_id", "me")
    u = find_user(data, cid)
    if not u:
        u = find_user(data, "me")
    return u

def _validate_id(id_str: str, field="id") -> Optional[str]:
    if not id_str or not str(id_str).strip():
        return f"{field} مطلوب"
    if len(str(id_str).strip()) > 64:
        return f"{field} طويل جداً"
    return None

# ========== 1) block_user ==========
def block_user(user_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    حظر مستخدم. يضيفه لقائمة blocked و يزيله من الأصدقاء والمكتومين إن وجد.
    - user_id: معرف المستخدم المراد حظره
    - current_user_id: معرف المنفذ (افتراضي me)
    """
    err = _validate_id(user_id, "user_id")
    if err: return _fail(err)
    if user_id == current_user_id:
        return _fail("لا يمكنك حظر نفسك")

    data = load_data()
    me = find_user(data, current_user_id)
    target = find_user(data, user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)
    if not target: return _fail(f"المستخدم {user_id} غير موجود", 404)

    blocked = me.setdefault("blocked", [])
    friends = me.setdefault("friends", [])
    muted = me.setdefault("muted", [])

    if user_id in blocked:
        return _ok({"user_id": user_id, "already_blocked": True}, f"{target['name']} محظور بالفعل")

    blocked.append(user_id)
    # remove from friends/muted/auto-clean friend_requests
    if user_id in friends:
        friends.remove(user_id)
    if user_id in muted:
        muted.remove(user_id)
    # also remove reverse friendship if exists
    if current_user_id in target.get("friends", []):
        target["friends"].remove(current_user_id)
    # remove pending requests between them
    data["friend_requests"] = [r for r in data.get("friend_requests", []) if not (
        (r["from_id"] == user_id and r["to_id"] == current_user_id) or
        (r["from_id"] == current_user_id and r["to_id"] == user_id)
    )]

    save_data(data)
    return _ok({"user_id": user_id, "blocked": blocked}, f"تم حظر {target['name']} ⛔")

def unblock_user(user_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """إلغاء حظر مستخدم (helper إضافي)"""
    data = load_data()
    me = find_user(data, current_user_id)
    target = find_user(data, user_id)
    if not me or not target: return _fail("مستخدم غير موجود", 404)
    blocked = me.get("blocked", [])
    if user_id not in blocked:
        return _ok({"already_unblocked": True}, "المستخدم غير محظور أصلاً")
    blocked.remove(user_id)
    save_data(data)
    return _ok({"user_id": user_id}, f"تم إلغاء حظر {target['name']}")

# ========== 2) search_for_user ==========
def search_for_user(query: str, limit: int = 10, include_blocked: bool = False, current_user_id: str = "me") -> Dict[str, Any]:
    """
    البحث عن مستخدم بالاسم أو اللقب (nickname) أو handle.
    - query: نص البحث (يبحث في name, nickname, handle)
    - limit: أقصى عدد نتائج
    - include_blocked: هل نضم المحظورين
    """
    if not query or not query.strip():
        return _fail("query فارغ")
    if limit < 1 or limit > 50:
        return _fail("limit يجب أن يكون بين 1 و 50")

    data = load_data()
    me = find_user(data, current_user_id)
    blocked = set(me.get("blocked", []) if me else [])

    results = find_user_by_query(data, query)
    # filter blocked if needed
    if not include_blocked:
        results = [u for u in results if u["id"] not in blocked]

    # rank: exact nickname/handle match first
    q = query.strip().lower()
    def score(u):
        s = 0
        if u.get("nickname","").lower() == q: s -= 10
        if u.get("handle","").lower() == f"@{q}" or u.get("handle","").lower() == q: s -= 9
        if u.get("name","").lower() == q: s -= 8
        if q in u.get("nickname","").lower(): s -= 2
        if q in u.get("name","").lower(): s -= 1
        return s
    results.sort(key=score)
    results = results[:limit]

    # sanitize output
    out = []
    for u in results:
        out.append({
            "id": u["id"],
            "name": u["name"],
            "nickname": u.get("nickname",""),
            "handle": u.get("handle",""),
            "avatar": u.get("avatar",""),
            "bio": u.get("bio",""),
            "is_friend": u["id"] in me.get("friends", []) if me else False,
            "is_blocked": u["id"] in blocked,
            "is_muted": u["id"] in me.get("muted", []) if me else False,
        })
    return _ok({"query": query, "count": len(out), "users": out}, f"وجدنا {len(out)} نتيجة")

# ========== 3) mute_user ==========
def mute_user(user_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    كتم مستخدم (إخفاء إشعاراته/رسائله بدون حظر).
    toggle: إذا كان مكتوم يلغي الكتم، وإلا يكتمه.
    """
    err = _validate_id(user_id, "user_id")
    if err: return _fail(err)
    if user_id == current_user_id: return _fail("لا يمكنك كتم نفسك")

    data = load_data()
    me = find_user(data, current_user_id)
    target = find_user(data, user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)
    if not target: return _fail(f"المستخدم {user_id} غير موجود", 404)
    if user_id in me.get("blocked", []):
        return _fail("المستخدم محظور — ألغِ الحظر أولاً")

    muted = me.setdefault("muted", [])
    if user_id in muted:
        muted.remove(user_id)
        save_data(data)
        return _ok({"user_id": user_id, "muted": False}, f"تم إلغاء كتم {target['name']}")
    else:
        muted.append(user_id)
        save_data(data)
        return _ok({"user_id": user_id, "muted": True}, f"تم كتم {target['name']} 🔇")

def unmute_user(user_id: str, current_user_id: str = "me"):
    """إلغاء كتم صريح"""
    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("غير موجود", 404)
    muted = me.get("muted", [])
    if user_id not in muted:
        return _ok({"already_unmuted": True}, "غير مكتوم أصلاً")
    muted.remove(user_id)
    save_data(data)
    return _ok({"user_id": user_id}, "تم إلغاء الكتم")

# ========== 4) send_friend_request ==========
def send_friend_request(to_user_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    إرسال طلب صداقة.
    - to_user_id: معرف المستلم
    """
    err = _validate_id(to_user_id, "to_user_id")
    if err: return _fail(err)
    if to_user_id == current_user_id: return _fail("لا يمكنك إرسال طلب لنفسك")

    data = load_data()
    me = find_user(data, current_user_id)
    target = find_user(data, to_user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)
    if not target: return _fail(f"المستخدم {to_user_id} غير موجود", 404)
    if to_user_id in me.get("blocked", []): return _fail("المستخدم محظور لديك — ألغِ الحظر أولاً")
    if current_user_id in target.get("blocked", []): return _fail("لا يمكنك الإرسال — أنت محظور لديه")
    if to_user_id in me.get("friends", []): return _fail("أنتم أصدقاء بالفعل")
    # check existing pending
    for r in data.get("friend_requests", []):
        if r["from_id"] == current_user_id and r["to_id"] == to_user_id and r["status"] == "pending":
            return _ok({"already_pending": True, "request_id": r["id"]}, "طلب معلق بالفعل")
        if r["from_id"] == to_user_id and r["to_id"] == current_user_id and r["status"] == "pending":
            return _fail("يوجد طلب معلق منه إليك — اقبله بدلاً من الإرسال")

    req_id = "r" + uuid.uuid4().hex[:6]
    new_req = {"id": req_id, "from_id": current_user_id, "to_id": to_user_id, "status": "pending", "created_at": _now_iso()}
    data.setdefault("friend_requests", []).append(new_req)
    save_data(data)
    return _ok({"request_id": req_id, "to": target["name"]}, f"تم إرسال طلب صداقة إلى {target['name']} ✦")

def accept_friend_request(request_id: str, current_user_id: str = "me"):
    """قبول طلب صداقة (helper)"""
    data = load_data()
    req = next((r for r in data.get("friend_requests", []) if r["id"] == request_id and r["to_id"] == current_user_id), None)
    if not req: return _fail("الطلب غير موجود", 404)
    if req["status"] != "pending": return _fail("الطلب ليس معلقاً")
    req["status"] = "accepted"
    me = find_user(data, current_user_id)
    sender = find_user(data, req["from_id"])
    if me and sender:
        me.setdefault("friends", []).append(sender["id"])
        sender.setdefault("friends", []).append(me["id"])
        # dedupe
        me["friends"] = list(dict.fromkeys(me["friends"]))
        sender["friends"] = list(dict.fromkeys(sender["friends"]))
    save_data(data)
    return _ok({"request_id": request_id}, "تم القبول")

def decline_friend_request(request_id: str, current_user_id: str = "me"):
    data = load_data()
    req = next((r for r in data.get("friend_requests", []) if r["id"] == request_id and r["to_id"] == current_user_id), None)
    if not req: return _fail("الطلب غير موجود", 404)
    req["status"] = "declined"
    save_data(data)
    return _ok({"request_id": request_id}, "تم الرفض")

# ========== 5) remove_friend ==========
def remove_friend(user_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    إزالة صديق (unfriend). يزيل من قائمتي الطرفين.
    """
    err = _validate_id(user_id, "user_id")
    if err: return _fail(err)

    data = load_data()
    me = find_user(data, current_user_id)
    target = find_user(data, user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)
    if not target: return _fail(f"المستخدم {user_id} غير موجود", 404)

    if user_id not in me.get("friends", []):
        return _ok({"already_removed": True}, "ليس صديقاً أصلاً")

    me["friends"].remove(user_id)
    if current_user_id in target.get("friends", []):
        target["friends"].remove(current_user_id)

    # remove pending requests between them if any
    data["friend_requests"] = [r for r in data.get("friend_requests", []) if not (
        (r["from_id"] == user_id and r["to_id"] == current_user_id) or
        (r["from_id"] == current_user_id and r["to_id"] == user_id)
    )]

    save_data(data)
    return _ok({"user_id": user_id, "friends": me["friends"]}, f"تمت إزالة {target['name']} من الأصدقاء")

# ========== 6) create_group ==========
def create_group(name: str, member_ids: Optional[List[str]] = None, current_user_id: str = "me") -> Dict[str, Any]:
    """
    إنشاء مجموعة دردشة.
    - name: اسم المجموعة (2-40 حرف)
    - member_ids: قائمة معرفات الأعضاء (اختياري)
    """
    if not name or not name.strip():
        return _fail("اسم المجموعة مطلوب")
    name = name.strip()
    if len(name) < 2: return _fail("اسم المجموعة قصير جداً (حرفان على الأقل)")
    if len(name) > 40: return _fail("اسم المجموعة طويل جداً (40 حرف max)")

    member_ids = member_ids or []
    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)

    # validate members exist and not blocked
    blocked = set(me.get("blocked", []))
    valid_members = set()
    for mid in member_ids:
        if mid == current_user_id: continue
        u = find_user(data, mid)
        if not u:
            return _fail(f"العضو {mid} غير موجود", 404)
        if mid in blocked:
            return _fail(f"العضو {u['name']} محظور لديك — لا يمكن إضافته")
        valid_members.add(mid)

    group_id = "g" + uuid.uuid4().hex[:6]
    group = {
        "id": group_id,
        "name": name,
        "members": [current_user_id] + sorted(valid_members),
        "created_at": _now_iso(),
        "created_by": current_user_id,
        "avatar": f"https://i.pravatar.cc/100?img={abs(hash(group_id)) % 60 + 1}"
    }
    data.setdefault("groups", []).append(group)
    save_data(data)
    return _ok(group, f"تم إنشاء المجموعة '{name}' ◈")

# ========== 7) create_server ==========
def create_server(name: str, description: str = "", current_user_id: str = "me") -> Dict[str, Any]:
    """
    إنشاء سيرفر (مجتمع).
    - name: اسم السيرفر (2-40 حرف)
    - description: وصف اختياري (max 200)
    """
    if not name or not name.strip():
        return _fail("اسم السيرفر مطلوب")
    name = name.strip()
    if len(name) < 2: return _fail("اسم السيرفر قصير جداً")
    if len(name) > 40: return _fail("اسم السيرفر طويل جداً (40 حرف)")
    if description and len(description) > 200:
        return _fail("الوصف طويل جداً (200 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)

    server_id = "s" + uuid.uuid4().hex[:6]
    server = {
        "id": server_id,
        "name": name,
        "description": description.strip(),
        "owner_id": current_user_id,
        "members": [current_user_id],
        "created_at": _now_iso(),
        "img": f"https://images.unsplash.com/photo-{'1448375240586-882707db888b' if int(uuid.uuid4().hex[:2],16)%2==0 else '1519681393784-d120267933ba'}?w=200"
    }
    data.setdefault("servers", []).append(server)
    save_data(data)
    return _ok(server, f"تم إنشاء السيرفر '{name}' ✦")

# ========== 8) update_profile_avatar ==========
def update_profile_avatar(avatar_url: Optional[str] = None, avatar_path: Optional[str] = None, current_user_id: str = "me") -> Dict[str, Any]:
    """
    تحديث صورة البروفايل.
    - avatar_url: رابط صورة (http/https) — أو
    - avatar_path: مسار ملف محلي (سيتم التحقق من وجوده)
    واحد منهما مطلوب.
    """
    if not avatar_url and not avatar_path:
        return _fail("avatar_url أو avatar_path مطلوب")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم غير موجود", 404)

    new_avatar = None
    if avatar_path:
        p = Path(avatar_path)
        if not p.exists():
            return _fail(f"الملف غير موجود: {avatar_path}", 404)
        if p.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            return _fail("صيغة الصورة غير مدعومة (jpg/png/webp/gif)")
        # في بيئة حقيقية نرفع الملف؛ هنا نحفظ المسار
        new_avatar = str(p.resolve())
    else:
        # validate URL
        if not re.match(r"^https?://", avatar_url):
            return _fail("avatar_url يجب أن يبدأ بـ http:// أو https://")
        if len(avatar_url) > 500:
            return _fail("الرابط طويل جداً")
        new_avatar = avatar_url.strip()

    me["avatar"] = new_avatar
    save_data(data)
    return _ok({"avatar": new_avatar}, "تم تحديث الصورة ✨")

# ========== 9) update_profile_banner ==========
def update_profile_banner(banner_url: Optional[str] = None, banner_path: Optional[str] = None, current_user_id: str = "me") -> Dict[str, Any]:
    """
    تحديث بانر البروفايل (الغلاف).
    - banner_url: رابط صورة
    - banner_path: مسار ملف محلي
    """
    if not banner_url and not banner_path:
        return _fail("banner_url أو banner_path مطلوب")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم غير موجود", 404)

    new_banner = None
    if banner_path:
        p = Path(banner_path)
        if not p.exists():
            return _fail(f"الملف غير موجود: {banner_path}", 404)
        if p.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            return _fail("صيغة الصورة غير مدعومة")
        new_banner = str(p.resolve())
    else:
        if not re.match(r"^https?://", banner_url):
            return _fail("banner_url يجب أن يبدأ بـ http(s)://")
        if len(banner_url) > 500:
            return _fail("الرابط طويل جداً")
        new_banner = banner_url.strip()

    me["banner"] = new_banner
    save_data(data)
    return _ok({"banner": new_banner}, "تم تحديث الغلاف 🌿")

# ========== 10) update_profile_bio ==========
def update_profile_bio(bio: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    تحديث البايو.
    - bio: نص حتى 300 حرف، يمكن أن يكون فارغاً لمسحه
    """
    if bio is None:
        return _fail("bio مطلوب (يمكن أن يكون نص فارغ)")
    bio = str(bio).strip()
    if len(bio) > 300:
        return _fail("البايو طويل جداً (300 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم غير موجود", 404)

    me["bio"] = bio
    save_data(data)
    return _ok({"bio": bio}, "تم تحديث البايو")

# ========== 11) update_profile_status ==========
ALLOWED_STATUSES = ["🌿 متاحة", "🍵 تحتسي الشاي", "🎨 ترسم الآن", "🌙 مشغولة قليلاً", "💤 نائمة", "🌿 متصل الآن", "offline", "online", "idle"]
def update_profile_status(status: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    تحديث الحالة.
    - status: نص الحالة (يفضل اختيار من ALLOWED_STATUSES لكن نقبل أي نص حتى 40 حرف)
    """
    if not status or not str(status).strip():
        return _fail("status مطلوب")
    status = str(status).strip()
    if len(status) > 40:
        return _fail("الحالة طويلة جداً (40 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم غير موجود", 404)

    me["status"] = status
    save_data(data)
    return _ok({"status": status}, f"تم تحديث الحالة إلى: {status}")

# ========== 11b) update_profile_name ==========
def update_profile_name(name: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    تحديث اسم العرض.
    - name: الاسم الجديد (2-40 حرف)
    """
    if not name or not str(name).strip():
        return _fail("name مطلوب")
    name = str(name).strip()
    if len(name) < 2:
        return _fail("الاسم قصير جداً (حرفان على الأقل)")
    if len(name) > 40:
        return _fail("الاسم طويل جداً (40 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم غير موجود", 404)

    me["name"] = name
    save_data(data)
    return _ok({"name": name}, "تم تحديث الاسم")

# ========== 11c) update_profile_nickname ==========
def update_profile_nickname(nickname: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    تحديث اللقب (nickname).
    - nickname: اللقب الجديد (حتى 40 حرف، يمكن أن يكون فارغاً لمسحه)
    """
    if nickname is None:
        return _fail("nickname مطلوب (يمكن أن يكون نص فارغ)")
    nickname = str(nickname).strip()
    if len(nickname) > 40:
        return _fail("اللقب طويل جداً (40 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم غير موجود", 404)

    me["nickname"] = nickname
    save_data(data)
    return _ok({"nickname": nickname}, "تم تحديث اللقب")

# ========== 11d) leave_group / leave_server ==========
def leave_group(group_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    مغادرة مجموعة. إن فرغت المجموعة من الأعضاء تُحذف.
    - group_id: معرف المجموعة
    """
    err = _validate_id(group_id, "group_id")
    if err: return _fail(err)

    data = load_data()
    groups = data.get("groups", [])
    g = next((x for x in groups if x.get("id") == group_id), None)
    if not g: return _fail("المجموعة غير موجودة", 404)
    if current_user_id not in g.get("members", []):
        return _ok({"already_left": True}, "لست عضواً في هذه المجموعة")

    g["members"] = [m for m in g.get("members", []) if m != current_user_id]
    if not g["members"]:
        data["groups"] = [x for x in groups if x.get("id") != group_id]
        save_data(data)
        return _ok({"deleted_group_id": group_id}, "غادرت المجموعة وحُذفت لفراغها 🍂")
    save_data(data)
    return _ok({"group_id": group_id}, "غادرت المجموعة بهدوء 🍂")

def leave_server(server_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    مغادرة سيرفر. المالك فقط يمكنه حذف السيرفر بحذف نفسه منه إن كان العضو الوحيد.
    - server_id: معرف السيرفر
    """
    err = _validate_id(server_id, "server_id")
    if err: return _fail(err)

    data = load_data()
    servers = data.get("servers", [])
    s = next((x for x in servers if x.get("id") == server_id), None)
    if not s: return _fail("السيرفر غير موجود", 404)
    if current_user_id not in s.get("members", []):
        return _ok({"already_left": True}, "لست عضواً في هذا السيرفر")

    s["members"] = [m for m in s.get("members", []) if m != current_user_id]
    if not s["members"]:
        data["servers"] = [x for x in servers if x.get("id") != server_id]
        save_data(data)
        return _ok({"deleted_server_id": server_id}, "غادرت السيرفر وحُذف لفراغه 🍂")
    save_data(data)
    return _ok({"server_id": server_id}, "غادرت السيرفر بهدوء 🍂")

# ========== 12) send_message ==========
def send_message(chat_id: str, text: str, from_id: str = "me", current_user_id: str = "me") -> Dict[str, Any]:
    """
    إرسال رسالة نصية في دردشة.
    - chat_id: معرف المحادثة/المجموعة/السيرفر
    - text: نص الرسالة
    - from_id: مرسل الرسالة (افتراضي me)
    """
    err = _validate_id(chat_id, "chat_id")
    if err: return _fail(err)
    if not text or not str(text).strip():
        return _fail("نص الرسالة مطلوب")
    text = str(text).strip()
    if len(text) > 1000:
        return _fail("الرسالة طويلة جداً (1000 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)

    msg_id = "m" + uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%H:%M")
    message = {
        "id": msg_id,
        "chat_id": chat_id,
        "from_id": from_id,
        "text": text,
        "time": time_str,
        "reply_to": None,
    }
    data.setdefault("messages", []).append(message)
    save_data(data)
    return _ok(message, "تم إرسال الرسالة ✉")

# ========== 13) reply_to_message ==========
def reply_to_message(chat_id: str, message_id: str, text: str, from_id: str = "me", current_user_id: str = "me") -> Dict[str, Any]:
    """
    الرد على رسالة موجودة.
    - chat_id: معرف المحادثة
    - message_id: معرف الرسالة الأصلية
    - text: نص الرد
    """
    err = _validate_id(chat_id, "chat_id")
    if err: return _fail(err)
    err = _validate_id(message_id, "message_id")
    if err: return _fail(err)
    if not text or not str(text).strip():
        return _fail("نص الرد مطلوب")
    text = str(text).strip()
    if len(text) > 1000:
        return _fail("الرد طويل جداً (1000 حرف max)")

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)

    original = next((m for m in data.get("messages", []) if m["id"] == message_id), None)
    if not original:
        return _fail("الرسالة الأصلية غير موجودة", 404)
    if original.get("chat_id") != chat_id:
        return _fail("الرسالة الأصلية لا تنتمي لهذه المحادثة", 400)

    msg_id = "m" + uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%H:%M")
    message = {
        "id": msg_id,
        "chat_id": chat_id,
        "from_id": from_id,
        "text": text,
        "time": time_str,
        "reply_to": message_id,
    }
    data.setdefault("messages", []).append(message)
    save_data(data)
    return _ok(message, "تم الرد على الرسالة ↩")

# ========== 14) delete_message ==========
def delete_message(message_id: str, current_user_id: str = "me") -> Dict[str, Any]:
    """
    حذف رسالة.
    - message_id: معرف الرسالة
    يمكن حذف الرسالة فقط من قبل مرسلها أو مالك المحادثة/السيرفر.
    """
    err = _validate_id(message_id, "message_id")
    if err: return _fail(err)

    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("المستخدم الحالي غير موجود", 404)

    messages = data.get("messages", [])
    idx = next((i for i, m in enumerate(messages) if m["id"] == message_id), None)
    if idx is None:
        return _fail("الرسالة غير موجودة", 404)

    msg = messages[idx]
    chat_id = msg.get("chat_id")
    from_id = msg.get("from_id")

    is_owner = False
    for server in data.get("servers", []):
        if server.get("id") == chat_id and server.get("owner_id") == current_user_id:
            is_owner = True
            break
    for group in data.get("groups", []):
        if group.get("id") == chat_id and group.get("created_by") == current_user_id:
            is_owner = True
            break

    if from_id != current_user_id and not is_owner:
        return _fail("لا يمكنك حذف رسالة مستخدم آخر", 403)

    deleted = messages.pop(idx)
    save_data(data)
    return _ok({"deleted_message_id": message_id}, "تم حذف الرسالة 🗑")

# ---------- extra helpers for agents ----------
def get_user_by_id(user_id: str) -> Dict[str, Any]:
    data = load_data()
    u = find_user(data, user_id)
    if not u: return _fail("غير موجود", 404)
    return _ok(u)

def list_users(limit: int = 20) -> Dict[str, Any]:
    data = load_data()
    return _ok(data.get("users", [])[:limit])

def get_profile(current_user_id: str = "me") -> Dict[str, Any]:
    data = load_data()
    me = find_user(data, current_user_id)
    if not me: return _fail("غير موجود", 404)
    return _ok(me)

# ---------- tool schemas for LLM (OpenAI style) ----------
TOOL_SCHEMAS = [
    {
        "name": "block_user",
        "description": "حظر مستخدم — يزيله من الأصدقاء والمكتومين",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "string", "description": "معرف المستخدم"}}, "required": ["user_id"]}
    },
    {
        "name": "search_for_user",
        "description": "البحث عن مستخدم بالاسم أو اللقب أو handle",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}
    },
    {
        "name": "mute_user",
        "description": "كتم/إلغاء كتم مستخدم (toggle)",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}
    },
    {
        "name": "send_friend_request",
        "description": "إرسال طلب صداقة",
        "parameters": {"type": "object", "properties": {"to_user_id": {"type": "string"}}, "required": ["to_user_id"]}
    },
    {
        "name": "remove_friend",
        "description": "إزالة صديق",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}
    },
    {
        "name": "create_group",
        "description": "إنشاء مجموعة دردشة",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "member_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["name"]}
    },
    {
        "name": "create_server",
        "description": "إنشاء سيرفر جديد",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name"]}
    },
    {
        "name": "update_profile_avatar",
        "description": "تحديث صورة البروفايل",
        "parameters": {"type": "object", "properties": {"avatar_url": {"type": "string"}, "avatar_path": {"type": "string"}}, "required": []}
    },
    {
        "name": "update_profile_banner",
        "description": "تحديث بانر البروفايل",
        "parameters": {"type": "object", "properties": {"banner_url": {"type": "string"}, "banner_path": {"type": "string"}}, "required": []}
    },
    {
        "name": "update_profile_bio",
        "description": "تحديث البايو (max 300 حرف)",
        "parameters": {"type": "object", "properties": {"bio": {"type": "string"}}, "required": ["bio"]}
    },
    {
        "name": "update_profile_status",
        "description": "تحديث الحالة (max 40 حرف)",
        "parameters": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}
    },
    {
        "name": "send_message",
        "description": "إرسال رسالة نصية في محادثة/مجموعة/سيرفر",
        "parameters": {"type": "object", "properties": {
            "chat_id": {"type": "string", "description": "معرف المحادثة"},
            "text": {"type": "string", "description": "نص الرسالة"},
            "from_id": {"type": "string", "description": "معرف المرسل", "default": "me"}
        }}, "required": ["chat_id", "text"]
    },
    {
        "name": "reply_to_message",
        "description": "الرد على رسالة موجودة",
        "parameters": {"type": "object", "properties": {
            "chat_id": {"type": "string", "description": "معرف المحادثة"},
            "message_id": {"type": "string", "description": "معرف الرسالة الأصلية"},
            "text": {"type": "string", "description": "نص الرد"},
            "from_id": {"type": "string", "description": "معرف المرسل", "default": "me"}
        }}, "required": ["chat_id", "message_id", "text"]
    },
    {
        "name": "delete_message",
        "description": "حذف رسالة (من قبل مرسلها أو مالك المحادثة)",
        "parameters": {"type": "object", "properties": {
            "message_id": {"type": "string", "description": "معرف الرسالة"}
        }}, "required": ["message_id"]
    },
    {
        "name": "list_users",
        "description": "عرض قائمة مستخدمي المنصة",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "العدد الأقصى للمستخدمين", "default": 20}
        }, "required": []}
    },
    {
        "name": "get_profile",
        "description": "الحصول على بيانات الملف الشخصي الخاص بك",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
]

