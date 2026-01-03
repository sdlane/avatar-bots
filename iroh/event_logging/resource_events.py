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


def _format_resources(resources: Dict[str, int]) -> str:
    """Helper to format resource dict into emoji string."""
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
    return ' '.join(resource_strs) if resource_strs else "nothing"


def resource_transfer_success_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for RESOURCE_TRANSFER_SUCCESS event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')
    transferred_resources = event_data.get('transferred_resources', {})

    resources_str = _format_resources(transferred_resources)
    return f"📦 Transfer successful: {from_character_name} → {to_character_name} ({resources_str})"


def resource_transfer_success_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_TRANSFER_SUCCESS event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')
    transferred_resources = event_data.get('transferred_resources', {})

    resources_str = _format_resources(transferred_resources)
    return f"📦 Transfer: {from_character_name} → {to_character_name} ({resources_str})"


def resource_transfer_partial_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for RESOURCE_TRANSFER_PARTIAL event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')
    requested_resources = event_data.get('requested_resources', {})
    transferred_resources = event_data.get('transferred_resources', {})

    requested_str = _format_resources(requested_resources)
    transferred_str = _format_resources(transferred_resources)
    return f"⚠️ Transfer partially complete: {from_character_name} → {to_character_name} (requested: {requested_str}, transferred: {transferred_str})"


def resource_transfer_partial_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_TRANSFER_PARTIAL event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')
    requested_resources = event_data.get('requested_resources', {})
    transferred_resources = event_data.get('transferred_resources', {})

    requested_str = _format_resources(requested_resources)
    transferred_str = _format_resources(transferred_resources)
    return f"⚠️ Partial transfer: {from_character_name} → {to_character_name} (requested: {requested_str}, sent: {transferred_str})"


def resource_transfer_failed_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for RESOURCE_TRANSFER_FAILED event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')
    reason = event_data.get('reason', 'Unknown reason')

    return f"❌ Transfer failed: {from_character_name} → {to_character_name} ({reason})"


def resource_transfer_failed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_TRANSFER_FAILED event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')
    reason = event_data.get('reason', 'Unknown reason')

    return f"❌ Transfer failed: {from_character_name} → {to_character_name} ({reason})"


def transfer_cancelled_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for TRANSFER_CANCELLED event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')

    return f"🚫 Transfer cancelled: {from_character_name} → {to_character_name}"


def transfer_cancelled_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TRANSFER_CANCELLED event."""
    from_character_name = event_data.get('from_character_name', 'Unknown')
    to_character_name = event_data.get('to_character_name', 'Unknown')

    return f"🚫 Transfer cancelled: {from_character_name} → {to_character_name}"
