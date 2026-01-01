"""
Event handlers for upkeep-related events.
"""
from typing import Dict, Any


def upkeep_paid_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for UPKEEP_PAID event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"✅ Upkeep paid for {unit_id}"


def upkeep_paid_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UPKEEP_PAID event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"✅ {unit_id} upkeep paid"


def upkeep_deficit_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for UPKEEP_DEFICIT event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    penalty = event_data.get('organization_penalty', 0)
    new_org = event_data.get('new_organization', 0)
    deficit = event_data.get('resources_deficit', {})
    deficit_strs = [f"{k}:{v}" for k, v in deficit.items() if v > 0]
    return f"⚠️ {unit_id}: Insufficient upkeep (missing {', '.join(deficit_strs)}) - Organization -{penalty} → {new_org}"


def upkeep_deficit_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UPKEEP_DEFICIT event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    penalty = event_data.get('organization_penalty', 0)
    return f"⚠️ {unit_id} org -{penalty}"


def unit_dissolved_character_line(event_data: Dict[str, Any]) -> str:
    """Generate character report line for UNIT_DISSOLVED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"💀 **{unit_id} dissolved** (organization depleted)"


def unit_dissolved_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for UNIT_DISSOLVED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    return f"💀 {unit_id} dissolved"
