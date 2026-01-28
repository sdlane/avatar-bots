"""
Event handlers for resource-related events.
"""
from typing import Dict, Any, Optional


def resource_collection_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for RESOURCE_COLLECTION event."""
    resources = event_data.get('resources', {})
    war_bonus = event_data.get('war_bonus')
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
    if resources.get('platinum', 0) > 0:
        resource_strs.append(f"🪙{resources['platinum']}")

    if resource_strs:
        base_msg = f"💰 Collected resources: {' '.join(resource_strs)}"
        if war_bonus:
            return f"{base_msg} ⚔️ (includes first-war bonus)"
        return base_msg
    return ""


def resource_collection_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_COLLECTION event."""
    character_name = event_data.get('character_name', 'Unknown')
    resources = event_data.get('resources', {})
    war_bonus = event_data.get('war_bonus')
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
    if resources.get('platinum', 0) > 0:
        resource_strs.append(f"🪙{resources['platinum']}")

    if resource_strs:
        if war_bonus:
            faction_name = war_bonus.get('faction_name', 'Unknown')
            return f"💰 {character_name}: {' '.join(resource_strs)} ⚔️ ({faction_name} war bonus)"
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
    if resources.get('platinum', 0) > 0:
        resource_strs.append(f"🪙{resources['platinum']}")
    return ' '.join(resource_strs) if resource_strs else "nothing"


def _format_ongoing_status(event_data: Dict[str, Any]) -> str:
    """Helper to format ongoing transfer status."""
    is_ongoing = event_data.get('is_ongoing', False)
    if not is_ongoing:
        return ""

    term_completed = event_data.get('term_completed', False)
    if term_completed:
        return " [ongoing - COMPLETED]"

    turns_remaining = event_data.get('turns_remaining')
    if turns_remaining is None:
        return " [ongoing - indefinite]"
    else:
        return f" [ongoing - {turns_remaining} turns remaining]"


def resource_transfer_success_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for RESOURCE_TRANSFER_SUCCESS event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')
    transferred_resources = event_data.get('transferred_resources', {})

    resources_str = _format_resources(transferred_resources)
    ongoing_str = _format_ongoing_status(event_data)
    return f"📦 Transfer successful: {from_name} → {to_name} ({resources_str}){ongoing_str}"


def resource_transfer_success_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_TRANSFER_SUCCESS event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')
    transferred_resources = event_data.get('transferred_resources', {})

    resources_str = _format_resources(transferred_resources)
    ongoing_str = _format_ongoing_status(event_data)
    return f"📦 Transfer: {from_name} → {to_name} ({resources_str}){ongoing_str}"


def resource_transfer_partial_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for RESOURCE_TRANSFER_PARTIAL event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')
    requested_resources = event_data.get('requested_resources', {})
    transferred_resources = event_data.get('transferred_resources', {})

    requested_str = _format_resources(requested_resources)
    transferred_str = _format_resources(transferred_resources)
    ongoing_str = _format_ongoing_status(event_data)
    return f"⚠️ Transfer partially complete: {from_name} → {to_name} (requested: {requested_str}, transferred: {transferred_str}){ongoing_str}"


def resource_transfer_partial_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_TRANSFER_PARTIAL event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')
    requested_resources = event_data.get('requested_resources', {})
    transferred_resources = event_data.get('transferred_resources', {})

    requested_str = _format_resources(requested_resources)
    transferred_str = _format_resources(transferred_resources)
    ongoing_str = _format_ongoing_status(event_data)
    return f"⚠️ Partial transfer: {from_name} → {to_name} (requested: {requested_str}, sent: {transferred_str}){ongoing_str}"


def resource_transfer_failed_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for RESOURCE_TRANSFER_FAILED event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')
    reason = event_data.get('reason', 'Unknown reason')

    return f"❌ Transfer failed: {from_name} → {to_name} ({reason})"


def resource_transfer_failed_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for RESOURCE_TRANSFER_FAILED event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')
    reason = event_data.get('reason', 'Unknown reason')

    return f"❌ Transfer failed: {from_name} → {to_name} ({reason})"


def transfer_cancelled_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for TRANSFER_CANCELLED event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')

    return f"🚫 Transfer cancelled: {from_name} → {to_name}"


def transfer_cancelled_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TRANSFER_CANCELLED event."""
    from_name = event_data.get('from_name', 'Unknown')
    to_name = event_data.get('to_name', 'Unknown')

    return f"🚫 Transfer cancelled: {from_name} → {to_name}"


def faction_territory_production_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for FACTION_TERRITORY_PRODUCTION event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    resources = event_data.get('resources', {})
    resources_str = _format_resources(resources)
    return f"🏰 **{faction_name}** territory production: {resources_str}"


def faction_territory_production_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for FACTION_TERRITORY_PRODUCTION event."""
    faction_name = event_data.get('faction_name', 'Unknown')
    resources = event_data.get('resources', {})
    resources_str = _format_resources(resources)
    return f"🏰 {faction_name} territory: {resources_str}"


def war_bonus_production_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for WAR_BONUS_PRODUCTION event."""
    resources = event_data.get('resources', {})
    resources_str = _format_resources(resources)
    return f"⚔️ First-war bonus production: {resources_str}"


def war_bonus_production_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for WAR_BONUS_PRODUCTION event."""
    character_name = event_data.get('character_name', 'Unknown')
    faction_name = event_data.get('faction_name', 'Unknown')
    # Use total_resources (after doubling) for GM report
    total_resources = event_data.get('total_resources', event_data.get('resources', {}))
    resources_str = _format_resources(total_resources)
    return f"⚔️ {character_name} ({faction_name} war bonus): {resources_str}"
