"""
Event handlers for upkeep-related events.
"""
from typing import Dict, Any, Optional


def _format_resources(resources: Dict[str, int]) -> str:
    """Helper to format resource dict into emoji string."""
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


def upkeep_summary_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UPKEEP_SUMMARY event."""
    character_name = event_data.get('character_name', 'Unknown')
    resources_spent = event_data.get('resources_spent', {})
    units_maintained = event_data.get('units_maintained', 0)
    resources_str = _format_resources(resources_spent)
    return f"💰 Upkeep paid: {resources_str} ({units_maintained} unit{'s' if units_maintained != 1 else ''})"


def upkeep_summary_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UPKEEP_SUMMARY event."""
    character_name = event_data.get('character_name', 'Unknown')
    resources_spent = event_data.get('resources_spent', {})
    units_maintained = event_data.get('units_maintained', 0)
    resources_str = _format_resources(resources_spent)
    return f"💰 {character_name}: {resources_str} ({units_maintained}u)"


def _format_deficit(deficit: Dict[str, int]) -> str:
    """Helper to format deficit dict into readable string like '2 cloth, 3 rations'."""
    deficit_strs = []
    if deficit.get('ore', 0) > 0:
        deficit_strs.append(f"{deficit['ore']} ore")
    if deficit.get('lumber', 0) > 0:
        deficit_strs.append(f"{deficit['lumber']} lumber")
    if deficit.get('coal', 0) > 0:
        deficit_strs.append(f"{deficit['coal']} coal")
    if deficit.get('rations', 0) > 0:
        deficit_strs.append(f"{deficit['rations']} rations")
    if deficit.get('cloth', 0) > 0:
        deficit_strs.append(f"{deficit['cloth']} cloth")
    if deficit.get('platinum', 0) > 0:
        deficit_strs.append(f"{deficit['platinum']} platinum")
    return ', '.join(deficit_strs) if deficit_strs else 'none'


def upkeep_total_deficit_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UPKEEP_TOTAL_DEFICIT event."""
    total_deficit = event_data.get('total_deficit', {})
    units_affected = event_data.get('units_affected', 0)
    deficit_str = _format_deficit(total_deficit)
    return f"⚠️ Total resources lacking: {deficit_str} ({units_affected} unit{'s' if units_affected != 1 else ''} affected)"


def upkeep_total_deficit_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UPKEEP_TOTAL_DEFICIT event (not shown in GM report)."""
    return ""


def upkeep_paid_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UPKEEP_PAID event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"✅ Upkeep paid for {unit_id}"


def upkeep_paid_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UPKEEP_PAID event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"✅ {unit_id} upkeep paid"


def upkeep_deficit_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UPKEEP_DEFICIT event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    penalty = event_data.get('organization_penalty', 0)
    new_org = event_data.get('new_organization', 0)
    deficit = event_data.get('resources_deficit', {})
    deficit_strs = [f"{k}:{v}" for k, v in deficit.items() if v > 0]

    owner_id = event_data.get('owner_character_id')
    owner_name = event_data.get('owner_name', 'Unknown')

    # Check if viewer is the owner or a commander
    if character_id and owner_id and character_id != owner_id:
        # Commander view - note the owner
        return f"⚠️ {unit_id} (owned by {owner_name}): Insufficient upkeep (missing {', '.join(deficit_strs)}) - Organization -{penalty} → {new_org}"
    else:
        # Owner view (existing format)
        return f"⚠️ {unit_id}: Insufficient upkeep (missing {', '.join(deficit_strs)}) - Organization -{penalty} → {new_org}"


def upkeep_deficit_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UPKEEP_DEFICIT event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    penalty = event_data.get('organization_penalty', 0)
    return f"⚠️ {unit_id} org -{penalty}"


def unit_dissolved_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for UNIT_DISSOLVED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"💀 **{unit_id} dissolved** (organization depleted)"


def unit_dissolved_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UNIT_DISSOLVED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"💀 {unit_id} dissolved"
