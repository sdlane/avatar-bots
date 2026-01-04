"""
Event handlers for unit-related events.
"""
from typing import Dict, Any, Optional


def commander_assigned_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMMANDER_ASSIGNED event."""
    unit_name = event_data.get('unit_name', 'Unknown Unit')
    new_commander_name = event_data.get('new_commander_name', 'Unknown')
    old_commander_name = event_data.get('old_commander_name')

    if old_commander_name:
        return f"**{unit_name}**: Commander changed from **{old_commander_name}** to **{new_commander_name}**"
    else:
        return f"**{unit_name}**: **{new_commander_name}** assigned as commander"


def commander_assigned_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMMANDER_ASSIGNED event."""
    unit_id = event_data.get('unit_id', '?')
    new_commander_name = event_data.get('new_commander_name', '?')
    old_commander_name = event_data.get('old_commander_name')

    if old_commander_name:
        return f"{unit_id}: {old_commander_name} -> {new_commander_name}"
    else:
        return f"{unit_id}: -> {new_commander_name}"
