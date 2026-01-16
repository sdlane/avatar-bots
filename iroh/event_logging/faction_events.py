"""
Event handlers for faction-related events.
"""
from typing import Dict, Any, Optional


def join_faction_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for JOIN_FACTION event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"✅ Joined faction: **{faction_name}**"


def join_faction_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for JOIN_FACTION event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"✅ {char} → {faction}"


def join_faction_completed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for JOIN_FACTION_COMPLETED event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"✅ **{char_name}** joined faction: **{faction_name}**"


def join_faction_completed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for JOIN_FACTION_COMPLETED event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"✅ {char} → {faction}"


def join_faction_pending_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
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


def leave_faction_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for LEAVE_FACTION event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"❌ **{char_name}** left faction: **{faction_name}**"


def leave_faction_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for LEAVE_FACTION event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"❌ {char} ← {faction}"


def kick_from_faction_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for KICK_FROM_FACTION event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"🚫 **{char_name}** was removed from faction: **{faction_name}**"


def kick_from_faction_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for KICK_FROM_FACTION event."""
    char = event_data.get('character_name', 'Unknown')
    faction = event_data.get('faction_name', 'Unknown')
    return f"🚫 {char} ← {faction} (kicked)"


def order_failed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for ORDER_FAILED event."""
    order_type = event_data.get('order_type', 'Unknown')
    error = event_data.get('error', 'Unknown error')

    # Add context for ASSIGN_COMMANDER orders
    if order_type == 'ASSIGN_COMMANDER':
        unit_name = event_data.get('unit_name') or event_data.get('unit_id', 'Unknown Unit')
        new_commander_name = event_data.get('new_commander_name', 'Unknown')
        return f"❌ Order failed: Assign **{new_commander_name}** as commander of **{unit_name}** - {error}"

    return f"❌ Order failed: **{order_type}** - {error}"


def order_failed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for ORDER_FAILED event."""
    order_type = event_data.get('order_type', 'Unknown')
    error = event_data.get('error', 'Unknown')

    # Add context for ASSIGN_COMMANDER orders
    if order_type == 'ASSIGN_COMMANDER':
        unit_id = event_data.get('unit_id', '?')
        new_commander_name = event_data.get('new_commander_name', '?')
        return f"❌ ASSIGN_COMMANDER ({unit_id} → {new_commander_name}): {error}"

    return f"❌ {order_type}: {error}"


def vp_assignment_started_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for VP_ASSIGNMENT_STARTED event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('target_faction_name', 'Unknown')
    vps = event_data.get('vps_controlled', 0)
    return f"🏆 **{char_name}** began assigning **{vps} VP** to **{faction_name}**"


def vp_assignment_started_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for VP_ASSIGNMENT_STARTED event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('target_faction_name', 'Unknown')
    vps = event_data.get('vps_controlled', 0)
    return f"🏆 {char_name} → {faction_name} ({vps} VP) [started]"


def vp_assignment_active_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for VP_ASSIGNMENT_ACTIVE event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('target_faction_name', 'Unknown')
    vps = event_data.get('vps_controlled', 0)
    return f"🏆 **{char_name}** is assigning **{vps} VP** to **{faction_name}**"


def vp_assignment_active_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for VP_ASSIGNMENT_ACTIVE event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('target_faction_name', 'Unknown')
    vps = event_data.get('vps_controlled', 0)
    return f"🏆 {char_name} → {faction_name} ({vps} VP) [active]"


def vp_assignment_cancelled_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for VP_ASSIGNMENT_CANCELLED event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('target_faction_name', 'Unknown')
    return f"🚫 **{char_name}** stopped assigning VPs to **{faction_name}**"


def vp_assignment_cancelled_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for VP_ASSIGNMENT_CANCELLED event."""
    char_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('target_faction_name', 'Unknown')
    return f"🚫 {char_name} ✗ {faction_name} [cancelled]"


# Alliance events

def alliance_pending_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for ALLIANCE_PENDING event."""
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    waiting_for = event_data.get('waiting_for_faction_name', 'Unknown')
    initiated_by = event_data.get('initiated_by_faction_name', 'Unknown')
    return f"⏳ Alliance proposed between **{faction_a}** and **{faction_b}** (initiated by {initiated_by}, waiting for {waiting_for})"


def alliance_pending_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for ALLIANCE_PENDING event."""
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    waiting_for = event_data.get('waiting_for_faction_name', 'Unknown')
    return f"⏳ Alliance: {faction_a} ↔ {faction_b} (pending: {waiting_for})"


def alliance_formed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for ALLIANCE_FORMED event."""
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    return f"🤝 Alliance formed between **{faction_a}** and **{faction_b}**"


def alliance_formed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for ALLIANCE_FORMED event."""
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    return f"🤝 Alliance: {faction_a} ↔ {faction_b} (active)"


def alliance_dissolved_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for ALLIANCE_DISSOLVED event."""
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    dissolved_by = event_data.get('dissolved_by_faction_name', 'Unknown')
    return f"💔 Alliance between **{faction_a}** and **{faction_b}** has been dissolved by **{dissolved_by}**"


def alliance_dissolved_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for ALLIANCE_DISSOLVED event."""
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    dissolved_by = event_data.get('dissolved_by_faction_name', 'Unknown')
    return f"💔 Alliance: {faction_a} ↔ {faction_b} (dissolved by {dissolved_by})"


# War events

def war_declared_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for WAR_DECLARED event."""
    declaring_faction = event_data.get('declaring_faction_name', 'Unknown')
    target_factions = event_data.get('target_faction_names', [])
    objective = event_data.get('objective', 'Unknown')
    targets_str = ', '.join(target_factions) if target_factions else 'Unknown'
    return f"⚔️ **{declaring_faction}** declared war on **{targets_str}** - Objective: {objective}"


def war_declared_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for WAR_DECLARED event."""
    declaring_faction = event_data.get('declaring_faction_name', 'Unknown')
    target_factions = event_data.get('target_faction_names', [])
    objective = event_data.get('objective', 'Unknown')
    targets_str = ', '.join(target_factions) if target_factions else 'Unknown'
    return f"⚔️ {declaring_faction} → {targets_str} (war: {objective})"


def war_joined_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for WAR_JOINED event."""
    joining_faction = event_data.get('joining_faction_name', 'Unknown')
    side = event_data.get('side', 'Unknown')
    objective = event_data.get('objective', 'Unknown')
    return f"⚔️ **{joining_faction}** joined the war on **{side}** - Objective: {objective}"


def war_joined_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for WAR_JOINED event."""
    joining_faction = event_data.get('joining_faction_name', 'Unknown')
    side = event_data.get('side', 'Unknown')
    objective = event_data.get('objective', 'Unknown')
    return f"⚔️ {joining_faction} → {side} (joined war: {objective})"


def war_ally_dragged_in_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for WAR_ALLY_DRAGGED_IN event."""
    dragged_faction = event_data.get('dragged_faction_name', 'Unknown')
    side = event_data.get('side', 'Unknown')
    objective = event_data.get('objective', 'Unknown')
    allied_with_str = event_data.get('allied_with_declarer_name', 'the declaring faction')
    return f"⚔️ **{dragged_faction}** was pulled into war on **{side}** due to alliance with {allied_with_str} - Objective: {objective}"


def war_ally_dragged_in_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for WAR_ALLY_DRAGGED_IN event."""
    dragged_faction = event_data.get('dragged_faction_name', 'Unknown')
    side = event_data.get('side', 'Unknown')
    objective = event_data.get('objective', 'Unknown')
    return f"⚔️ {dragged_faction} → {side} (dragged in: {objective})"


def war_production_bonus_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for WAR_PRODUCTION_BONUS event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"💰 **{faction_name}** receives first-war production bonus! Production doubled this turn."


def war_production_bonus_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for WAR_PRODUCTION_BONUS event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    return f"💰 {faction_name} (first-war production bonus)"
