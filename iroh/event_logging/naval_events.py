"""
Event handlers for naval positioning-related events.
"""
from typing import Dict, Any, Optional


def naval_position_set_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for NAVAL_POSITION_SET event."""
    units = event_data.get('units', [])
    action = event_data.get('action', 'unknown')
    occupied = event_data.get('occupied_territories', [])

    action_name = action.replace('naval_', '').title()
    return f"Naval {action_name}: {', '.join(units)} now occupy {', '.join(occupied)}"


def naval_position_set_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for NAVAL_POSITION_SET event."""
    units = event_data.get('units', [])
    action = event_data.get('action', 'unknown')
    occupied = event_data.get('occupied_territories', [])

    action_abbrev = action.replace('naval_', '').upper()[:3]
    return f"{', '.join(units)} {action_abbrev} {', '.join(occupied)}"


def naval_transit_progress_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for NAVAL_TRANSIT_PROGRESS event."""
    units = event_data.get('units', [])
    action = event_data.get('action', 'naval_transit')
    occupied = event_data.get('occupied_territories', [])
    window_start = event_data.get('window_start_index', 0)
    carrying = event_data.get('carrying_units', [])

    action_name = action.replace('naval_', '').title()

    if carrying:
        return (f"Naval {action_name} progress: {', '.join(units)} advancing, "
                f"now at {', '.join(occupied)} (carrying {', '.join(str(u) for u in carrying)})")
    else:
        return f"Naval {action_name} progress: {', '.join(units)} advancing, now at {', '.join(occupied)}"


def naval_transit_progress_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for NAVAL_TRANSIT_PROGRESS event."""
    units = event_data.get('units', [])
    occupied = event_data.get('occupied_territories', [])
    window_start = event_data.get('window_start_index', 0)

    return f"{', '.join(units)} -> {', '.join(occupied)} (idx={window_start})"


def naval_transit_complete_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for NAVAL_TRANSIT_COMPLETE event."""
    units = event_data.get('units', [])
    action = event_data.get('action', 'naval_transit')
    occupied = event_data.get('occupied_territories', [])
    carrying = event_data.get('carrying_units', [])

    action_name = action.replace('naval_', '').title()
    final = occupied[-1] if occupied else 'Unknown'

    if carrying:
        return (f"Naval {action_name} complete: {', '.join(units)} arrived at {final} "
                f"(carrying {', '.join(str(u) for u in carrying)})")
    else:
        return f"Naval {action_name} complete: {', '.join(units)} arrived at {final}"


def naval_transit_complete_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for NAVAL_TRANSIT_COMPLETE event."""
    units = event_data.get('units', [])
    occupied = event_data.get('occupied_territories', [])

    final = occupied[-1] if occupied else 'Unknown'
    return f"{', '.join(units)} -> {final} (complete)"


def naval_waiting_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for NAVAL_WAITING event."""
    units = event_data.get('units', [])
    occupied = event_data.get('occupied_territories', [])

    territory = occupied[0] if occupied else 'Unknown'
    return f"Naval transport waiting: {', '.join(units)} at {territory}, waiting for cargo"


def naval_waiting_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for NAVAL_WAITING event."""
    units = event_data.get('units', [])
    occupied = event_data.get('occupied_territories', [])

    territory = occupied[0] if occupied else 'Unknown'
    return f"{', '.join(units)} waiting at {territory}"
