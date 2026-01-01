"""
Event handlers for resource-related events.
"""
from typing import Dict, Any


def resource_collection_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for RESOURCE_COLLECTION event."""
    resources = event_data.get('resources', {})
    territory_name = event_data.get('territory_name', 'Unknown')
    resource_strs = []

    if resources.get('ore', 0) > 0:
        resource_strs.append(f"⛏️{resources['ore']}")
    if resources.get('lumber', 0) > 0:
        resource_strs.append(f"🪵{resources['lumber']}")
    if resources.get('coal', 0) > 0:
        resource_strs.append(f"⚫{resources['coal']}")
    if resources.get('rations', 0) > 0:
        resource_strs.append(f"🍖{resources['rations']}")
    if resources.get('cloth', 0) > 0:
        resource_strs.append(f"🧵{resources['cloth']}")

    if resource_strs:
        return f"💰 Collected from {territory_name}: {' '.join(resource_strs)}"
    return ""


def resource_collection_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_COLLECTION event."""
    leader = event_data.get('leader_name', 'Unknown')
    territory = event_data.get('territory_id', 'Unknown')
    return f"💰 T{territory} → {leader}"
