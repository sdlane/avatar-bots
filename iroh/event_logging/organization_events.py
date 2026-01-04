"""
Event handlers for organization phase events.
"""
from typing import Dict, Any, Optional


def unit_disbanded_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UNIT_DISBANDED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    unit_name = event_data.get('unit_name', unit_id)
    owner_id = event_data.get('owner_character_id')
    owner_name = event_data.get('owner_name', 'Unknown')

    # Check if viewer is owner or commander
    if character_id and owner_id and character_id != owner_id:
        # Commander view
        return f"**{unit_name}** (`{unit_id}`) has disbanded due to depleted organization. (owned by {owner_name})"
    else:
        # Owner view
        return f"**{unit_name}** (`{unit_id}`) has disbanded due to depleted organization."


def unit_disbanded_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UNIT_DISBANDED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    owner_name = event_data.get('owner_name', 'Unknown')
    final_org = event_data.get('final_organization', 0)
    return f"DISBANDED: {unit_id} (owner: {owner_name}, final org: {final_org})"


def org_recovery_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for ORG_RECOVERY event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    unit_name = event_data.get('unit_name', unit_id)
    old_org = event_data.get('old_organization', 0)
    new_org = event_data.get('new_organization', 0)
    territory_id = event_data.get('territory_id', '?')

    return f"**{unit_name}** (`{unit_id}`) recovered organization in friendly territory {territory_id}: {old_org} -> {new_org}"


def org_recovery_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for ORG_RECOVERY event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    old_org = event_data.get('old_organization', 0)
    new_org = event_data.get('new_organization', 0)
    return f"ORG+: {unit_id} ({old_org}->{new_org})"
