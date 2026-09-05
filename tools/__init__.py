"""
Society Tools — AI Agent Toolkit
Cozy Ghibli Community Platform

Expose 11 functions for LLM agents to interact with the platform.
All functions are synchronous, return dict with {success, data/error}, and persist to JSON.
"""
from .tools import (
    block_user,
    search_for_user,
    mute_user,
    send_friend_request,
    remove_friend,
    create_group,
    create_server,
    update_profile_avatar,
    update_profile_banner,
    update_profile_bio,
    update_profile_status,
    # helpers
    get_user_by_id,
    list_users,
    get_profile,
)

__all__ = [
    "block_user",
    "search_for_user",
    "mute_user",
    "send_friend_request",
    "remove_friend",
    "create_group",
    "create_server",
    "update_profile_avatar",
    "update_profile_banner",
    "update_profile_bio",
    "update_profile_status",
    "get_user_by_id",
    "list_users",
    "get_profile",
]
