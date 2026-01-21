"""
Event handlers for movement-related events.
"""
from typing import Dict, Any, Optional


def transit_complete_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for TRANSIT_COMPLETE event."""
    units = event_data.get('units', [])
    final_territory = event_data.get('final_territory', 'Unknown')
    return f"Units arrived: {', '.join(units)} -> Territory {final_territory}"


def transit_complete_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TRANSIT_COMPLETE event."""
    units = event_data.get('units', [])
    final_territory = event_data.get('final_territory', 'Unknown')
    return f"{', '.join(units)} -> T{final_territory}"


def transit_progress_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for TRANSIT_PROGRESS event."""
    units = event_data.get('units', [])
    current_territory = event_data.get('current_territory', 'Unknown')
    path_index = event_data.get('path_index', 0)
    total_steps = event_data.get('total_steps', 0)
    return f"Units moving: {', '.join(units)} -> Territory {current_territory} ({path_index}/{total_steps})"


def transit_progress_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TRANSIT_PROGRESS event."""
    units = event_data.get('units', [])
    current_territory = event_data.get('current_territory', 'Unknown')
    return f"{', '.join(units)} -> T{current_territory}"


def movement_blocked_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for MOVEMENT_BLOCKED event."""
    units = event_data.get('units', [])
    blocked_at = event_data.get('blocked_at', 'Unknown')
    terrain_cost = event_data.get('terrain_cost', 0)
    remaining_mp = event_data.get('remaining_mp', 0)
    current = event_data.get('current_territory', 'Unknown')
    return (f"Movement blocked: {', '.join(units)} stopped at {current}. "
            f"Cannot enter {blocked_at} (cost {terrain_cost}, have {remaining_mp} MP)")


def movement_blocked_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for MOVEMENT_BLOCKED event."""
    units = event_data.get('units', [])
    blocked_at = event_data.get('blocked_at', 'Unknown')
    terrain_cost = event_data.get('terrain_cost', 0)
    remaining_mp = event_data.get('remaining_mp', 0)
    return f"{', '.join(units)} blocked at {blocked_at} (cost {terrain_cost} > {remaining_mp} MP)"
