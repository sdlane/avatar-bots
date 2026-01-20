"""
Event handlers for building upkeep-related events.
"""
from typing import Dict, Any, Optional


def _format_resources(resources: Dict[str, int]) -> str:
    """Helper to format resource dict into string."""
    resource_strs = []
    if resources.get('ore', 0) > 0:
        resource_strs.append(f"ore:{resources['ore']}")
    if resources.get('lumber', 0) > 0:
        resource_strs.append(f"lumber:{resources['lumber']}")
    if resources.get('coal', 0) > 0:
        resource_strs.append(f"coal:{resources['coal']}")
    if resources.get('rations', 0) > 0:
        resource_strs.append(f"rations:{resources['rations']}")
    if resources.get('cloth', 0) > 0:
        resource_strs.append(f"cloth:{resources['cloth']}")
    if resources.get('platinum', 0) > 0:
        resource_strs.append(f"platinum:{resources['platinum']}")
    return ', '.join(resource_strs) if resource_strs else 'none'


def _format_deficit_types(deficit_types: list) -> str:
    """Helper to format deficit types list."""
    return ', '.join(deficit_types) if deficit_types else 'none'


def building_upkeep_paid_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for BUILDING_UPKEEP_PAID event."""
    building_name = event_data.get('building_name', 'Unknown')
    building_id = event_data.get('building_id', 'Unknown')
    resources_paid = event_data.get('resources_paid', {})
    resources_str = _format_resources(resources_paid)
    display_name = building_name if building_name else building_id
    return f"🏠 Building upkeep paid for {display_name}: {resources_str}"


def building_upkeep_paid_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for BUILDING_UPKEEP_PAID event."""
    building_id = event_data.get('building_id', 'Unknown')
    resources_paid = event_data.get('resources_paid', {})
    resources_str = _format_resources(resources_paid)
    return f"🏠 {building_id}: {resources_str}"


def building_upkeep_deficit_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for BUILDING_UPKEEP_DEFICIT event."""
    building_name = event_data.get('building_name', 'Unknown')
    building_id = event_data.get('building_id', 'Unknown')
    deficit_types = event_data.get('deficit_types', [])
    durability_penalty = event_data.get('durability_penalty', 0)
    new_durability = event_data.get('new_durability', 0)
    deficit_str = _format_deficit_types(deficit_types)
    display_name = building_name if building_name else building_id
    return f"⚠️ {display_name}: Insufficient upkeep (missing {deficit_str}) - Durability -{durability_penalty} → {new_durability}"


def building_upkeep_deficit_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for BUILDING_UPKEEP_DEFICIT event."""
    building_id = event_data.get('building_id', 'Unknown')
    durability_penalty = event_data.get('durability_penalty', 0)
    new_durability = event_data.get('new_durability', 0)
    return f"⚠️ {building_id} durability -{durability_penalty} → {new_durability}"


def building_destroyed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for BUILDING_DESTROYED event."""
    building_name = event_data.get('building_name', 'Unknown')
    building_id = event_data.get('building_id', 'Unknown')
    territory_id = event_data.get('territory_id', 'Unknown')
    display_name = building_name if building_name else building_id
    return f"💀 **{display_name} destroyed** in {territory_id} (durability depleted)"


def building_destroyed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for BUILDING_DESTROYED event."""
    building_id = event_data.get('building_id', 'Unknown')
    territory_id = event_data.get('territory_id', 'Unknown')
    return f"💀 {building_id} destroyed in {territory_id}"
