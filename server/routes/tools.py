from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/tools", tags=["tools"])

class BlockUserRequest(BaseModel):
    user_id: str
    current_user_id: str = "me"

class SearchUserRequest(BaseModel):
    query: str
    limit: int = 10
    include_blocked: bool = False
    current_user_id: str = "me"

class MuteUserRequest(BaseModel):
    user_id: str
    current_user_id: str = "me"

class FriendRequestRequest(BaseModel):
    to_user_id: str
    current_user_id: str = "me"

class RemoveFriendRequest(BaseModel):
    user_id: str
    current_user_id: str = "me"

class CreateGroupRequest(BaseModel):
    name: str
    member_ids: Optional[List[str]] = None
    current_user_id: str = "me"

class CreateServerRequest(BaseModel):
    name: str
    description: str = ""
    current_user_id: str = "me"

class UpdateAvatarRequest(BaseModel):
    avatar_url: Optional[str] = None
    avatar_path: Optional[str] = None
    current_user_id: str = "me"

class UpdateBannerRequest(BaseModel):
    banner_url: Optional[str] = None
    banner_path: Optional[str] = None
    current_user_id: str = "me"

class UpdateBioRequest(BaseModel):
    bio: str
    current_user_id: str = "me"

class UpdateStatusRequest(BaseModel):
    status: str
    current_user_id: str = "me"

class UpdateNameRequest(BaseModel):
    name: str
    current_user_id: str = "me"

class UpdateNicknameRequest(BaseModel):
    nickname: str
    current_user_id: str = "me"

class FriendRequestAction(BaseModel):
    request_id: str
    current_user_id: str = "me"

class LeaveGroupRequest(BaseModel):
    group_id: str
    current_user_id: str = "me"

class LeaveServerRequest(BaseModel):
    server_id: str
    current_user_id: str = "me"

class SendMessageRequest(BaseModel):
    chat_id: str
    text: str
    from_id: str = "me"
    current_user_id: str = "me"

class ReplyToMessageRequest(BaseModel):
    chat_id: str
    message_id: str
    text: str
    from_id: str = "me"
    current_user_id: str = "me"

class DeleteMessageRequest(BaseModel):
    message_id: str
    current_user_id: str = "me"


def _call_tool(func, payload: Dict[str, Any]):
    try:
        return func(**payload)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from tools.tools import (
    block_user,
    unblock_user,
    search_for_user,
    mute_user,
    unmute_user,
    send_friend_request,
    accept_friend_request,
    decline_friend_request,
    remove_friend,
    create_group,
    leave_group,
    create_server,
    leave_server,
    update_profile_avatar,
    update_profile_banner,
    update_profile_bio,
    update_profile_status,
    update_profile_name,
    update_profile_nickname,
    send_message,
    reply_to_message,
    delete_message,
    list_users,
    get_profile,
)


@router.post("/block_user")
def block_user_endpoint(body: BlockUserRequest):
    return _call_tool(block_user, body.model_dump())

@router.post("/unblock_user")
def unblock_user_endpoint(body: BlockUserRequest):
    return _call_tool(unblock_user, body.model_dump())

@router.post("/search_for_user")
def search_for_user_endpoint(body: SearchUserRequest):
    return _call_tool(search_for_user, body.model_dump())

@router.post("/mute_user")
def mute_user_endpoint(body: MuteUserRequest):
    return _call_tool(mute_user, body.model_dump())

@router.post("/unmute_user")
def unmute_user_endpoint(body: MuteUserRequest):
    return _call_tool(unmute_user, body.model_dump())

@router.post("/send_friend_request")
def send_friend_request_endpoint(body: FriendRequestRequest):
    return _call_tool(send_friend_request, body.model_dump())

@router.post("/accept_friend_request")
def accept_friend_request_endpoint(body: FriendRequestAction):
    return _call_tool(accept_friend_request, body.model_dump())

@router.post("/decline_friend_request")
def decline_friend_request_endpoint(body: FriendRequestAction):
    return _call_tool(decline_friend_request, body.model_dump())

@router.post("/remove_friend")
def remove_friend_endpoint(body: RemoveFriendRequest):
    return _call_tool(remove_friend, body.model_dump())

@router.post("/create_group")
def create_group_endpoint(body: CreateGroupRequest):
    return _call_tool(create_group, body.model_dump())

@router.post("/leave_group")
def leave_group_endpoint(body: LeaveGroupRequest):
    return _call_tool(leave_group, body.model_dump())

@router.post("/create_server")
def create_server_endpoint(body: CreateServerRequest):
    return _call_tool(create_server, body.model_dump())

@router.post("/leave_server")
def leave_server_endpoint(body: LeaveServerRequest):
    return _call_tool(leave_server, body.model_dump())

@router.post("/update_profile_avatar")
def update_profile_avatar_endpoint(body: UpdateAvatarRequest):
    return _call_tool(update_profile_avatar, body.model_dump())

@router.post("/update_profile_banner")
def update_profile_banner_endpoint(body: UpdateBannerRequest):
    return _call_tool(update_profile_banner, body.model_dump())

@router.post("/update_profile_bio")
def update_profile_bio_endpoint(body: UpdateBioRequest):
    return _call_tool(update_profile_bio, body.model_dump())

@router.post("/update_profile_status")
def update_profile_status_endpoint(body: UpdateStatusRequest):
    return _call_tool(update_profile_status, body.model_dump())

@router.post("/update_profile_name")
def update_profile_name_endpoint(body: UpdateNameRequest):
    return _call_tool(update_profile_name, body.model_dump())

@router.post("/update_profile_nickname")
def update_profile_nickname_endpoint(body: UpdateNicknameRequest):
    return _call_tool(update_profile_nickname, body.model_dump())

@router.post("/send_message")
def send_message_endpoint(body: SendMessageRequest):
    result = _call_tool(send_message, body.model_dump())
    if result.get("success"):
        from model.agents import wake_agents_for_chat
        wake_agents_for_chat(body.from_id or body.current_user_id, body.chat_id)
    return result

@router.post("/reply_to_message")
def reply_to_message_endpoint(body: ReplyToMessageRequest):
    result = _call_tool(reply_to_message, body.model_dump())
    if result.get("success"):
        from model.agents import wake_agents_for_chat
        wake_agents_for_chat(body.from_id or body.current_user_id, body.chat_id)
    return result

@router.post("/delete_message")
def delete_message_endpoint(body: DeleteMessageRequest):
    return _call_tool(delete_message, body.model_dump())

@router.get("/users")
def list_users_endpoint(limit: int = 20):
    return _call_tool(list_users, {"limit": limit})

@router.get("/groups")
def list_groups_endpoint():
    from tools.store import load_data
    data = load_data()
    return {"success": True, "data": data.get("groups", [])}

@router.get("/servers")
def list_servers_endpoint():
    from tools.store import load_data
    data = load_data()
    return {"success": True, "data": data.get("servers", [])}

@router.get("/messages")
def list_messages_endpoint(chat_id: str, current_user_id: str = "me"):
    from tools.store import load_data
    data = load_data()
    all_msgs = data.get("messages", [])
    group_ids = {g.get("id") for g in data.get("groups", [])}
    server_ids = {s.get("id") for s in data.get("servers", [])}

    if chat_id not in group_ids and chat_id not in server_ids:
        # DM chat: include messages between current_user_id and chat_id regardless of which was chat_id/from_id
        msgs = [
            m for m in all_msgs
            if (m.get("chat_id") == chat_id and m.get("from_id") == current_user_id)
            or (m.get("chat_id") == current_user_id and m.get("from_id") == chat_id)
            or (m.get("chat_id") == chat_id)
        ]
    else:
        msgs = [m for m in all_msgs if m.get("chat_id") == chat_id]
    return {"success": True, "data": msgs}


@router.get("/friend_requests")
def list_friend_requests_endpoint():
    from tools.store import load_data
    data = load_data()
    return {"success": True, "data": data.get("friend_requests", [])}

@router.get("/profile")
def get_profile_endpoint(current_user_id: str = "me"):
    return _call_tool(get_profile, {"current_user_id": current_user_id})
