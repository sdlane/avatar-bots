"""
Event handlers for resource-related events.
"""
from typing import Dict, Any


def resource_collection_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for RESOURCE_COLLECTION event."""
    resources = event_data.get('resources', {})
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
        return f"💰 Collected resources: {' '.join(resource_strs)}"
    return ""


def resource_collection_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_COLLECTION event."""
    character_name = event_data.get('character_name', 'Unknown')
    resources = event_data.get('resources', {})
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
        return f"💰 {character_name}: {' '.join(resource_strs)}"
    return f"💰 {character_name}"
