"""
Event handlers for movement-related events.
"""
from typing import Dict, Any


def transit_complete_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for TRANSIT_COMPLETE event."""
    units = event_data.get('units', [])
    final_territory = event_data.get('final_territory', 'Unknown')
    return f"🎯 Units arrived: {', '.join(units)} → Territory {final_territory}"


def transit_complete_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TRANSIT_COMPLETE event."""
    units = event_data.get('units', [])
    final_territory = event_data.get('final_territory', 'Unknown')
    return f"🎯 {', '.join(units)} → T{final_territory}"


def transit_progress_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for TRANSIT_PROGRESS event."""
    units = event_data.get('units', [])
    current_territory = event_data.get('current_territory', 'Unknown')
    path_index = event_data.get('path_index', 0)
    total_steps = event_data.get('total_steps', 0)
    return f"🚶 Units moving: {', '.join(units)} → Territory {current_territory} ({path_index}/{total_steps})"


def transit_progress_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TRANSIT_PROGRESS event."""
    units = event_data.get('units', [])
    current_territory = event_data.get('current_territory', 'Unknown')
    return f"🚶 {', '.join(units)} → T{current_territory}"
