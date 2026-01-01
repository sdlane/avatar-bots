"""
Event handlers for faction-related events.
"""
from typing import Dict, Any


def join_faction_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for JOIN_FACTION event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"✅ Joined faction: **{faction_name}**"


def join_faction_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for JOIN_FACTION event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"✅ {char} → {faction}"


def join_faction_completed_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for JOIN_FACTION_COMPLETED event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"✅ **{char_name}** joined faction: **{faction_name}**"


def join_faction_completed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for JOIN_FACTION_COMPLETED event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"✅ {char} → {faction}"


def join_faction_pending_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for JOIN_FACTION_PENDING event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    waiting_for = event_data.get('waiting_for', 'approval')
    return f"⏳ Join request for **{faction_name}** submitted (waiting for {waiting_for})"


def join_faction_pending_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for JOIN_FACTION_PENDING event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    waiting_for = event_data.get('waiting_for', '?')
    return f"⏳ {char} → {faction} (pending: {waiting_for})"


def leave_faction_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for LEAVE_FACTION event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"❌ **{char_name}** left faction: **{faction_name}**"


def leave_faction_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for LEAVE_FACTION event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"❌ {char} ← {faction}"


def kick_from_faction_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for KICK_FROM_FACTION event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"🚫 **{char_name}** was removed from faction: **{faction_name}**"


def kick_from_faction_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for KICK_FROM_FACTION event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"🚫 {char} ← {faction} (kicked)"


def order_failed_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for ORDER_FAILED event."""
    order_type = event_data.get('order_type', 'Unknown')
    error = event_data.get('error', 'Unknown error')
    return f"❌ Order failed: **{order_type}** - {error}"


def order_failed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for ORDER_FAILED event."""
    order_type = event_data.get('order_type', 'Unknown')
    error = event_data.get('error', 'Unknown')
    return f"❌ {order_type}: {error}"
