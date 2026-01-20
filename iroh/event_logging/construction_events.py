"""
Event handlers for construction and mobilization events.
"""
from typing import Dict, Any, Optional


def unit_mobilized_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UNIT_MOBILIZED event."""
    unit_name = event_data.get('unit_name', 'Unknown Unit')
    unit_type = event_data.get('unit_type', 'Unknown Type')
    territory_id = event_data.get('territory_id', '?')
    faction_name = event_data.get('faction_name')

    if faction_name:
        return f"**{unit_name}** ({unit_type}) mobilized in territory **{territory_id}** using **{faction_name}** resources"
    else:
        return f"**{unit_name}** ({unit_type}) mobilized in territory **{territory_id}**"


def unit_mobilized_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UNIT_MOBILIZED event."""
    unit_id = event_data.get('unit_id', '?')
    unit_type = event_data.get('unit_type', '?')
    territory_id = event_data.get('territory_id', '?')
    character_name = event_data.get('character_name', '?')
    faction_name = event_data.get('faction_name')
    cost = event_data.get('cost', {})

    cost_str = ', '.join(f"{k}:{v}" for k, v in cost.items() if v > 0)
    source = f" ({faction_name})" if faction_name else ""

    return f"{unit_id} ({unit_type}) mobilized at {territory_id} by {character_name}{source} [cost: {cost_str}]"


def mobilization_failed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for MOBILIZATION_FAILED event."""
    error = event_data.get('error', 'Unknown error')
    order_id = event_data.get('order_id', '?')

    return f"**Mobilization Failed** (Order {order_id}): {error}"


def mobilization_failed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for MOBILIZATION_FAILED event."""
    error = event_data.get('error', 'Unknown error')
    order_id = event_data.get('order_id', '?')

    return f"MOBILIZATION FAILED [{order_id}]: {error}"


def building_constructed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for BUILDING_CONSTRUCTED event."""
    building_type = event_data.get('building_type', 'Unknown Building')
    territory_id = event_data.get('territory_id', '?')
    faction_name = event_data.get('faction_name')

    if faction_name:
        return f"**{building_type}** constructed in territory **{territory_id}** using **{faction_name}** resources"
    else:
        return f"**{building_type}** constructed in territory **{territory_id}**"


def building_constructed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for BUILDING_CONSTRUCTED event."""
    building_id = event_data.get('building_id', '?')
    building_type = event_data.get('building_type', '?')
    territory_id = event_data.get('territory_id', '?')
    character_name = event_data.get('character_name', '?')
    faction_name = event_data.get('faction_name')
    cost = event_data.get('cost', {})

    cost_str = ', '.join(f"{k}:{v}" for k, v in cost.items() if v > 0)
    source = f" ({faction_name})" if faction_name else ""

    return f"{building_id} ({building_type}) built at {territory_id} by {character_name}{source} [cost: {cost_str}]"


def construction_failed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for CONSTRUCTION_FAILED event."""
    error = event_data.get('error', 'Unknown error')
    order_id = event_data.get('order_id', '?')

    return f"**Construction Failed** (Order {order_id}): {error}"


def construction_failed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for CONSTRUCTION_FAILED event."""
    error = event_data.get('error', 'Unknown error')
    order_id = event_data.get('order_id', '?')

    return f"CONSTRUCTION FAILED [{order_id}]: {error}"
