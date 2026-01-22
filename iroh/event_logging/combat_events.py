"""
Event handlers for combat-related events.
"""
from typing import Dict, Any, Optional


def combat_started_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_STARTED event."""
    territory_name = event_data.get('territory_name', 'Unknown')
    faction_names = event_data.get('faction_names', [])
    sides_count = event_data.get('sides_count', 2)

    factions_str = ', '.join(faction_names) if faction_names else 'multiple factions'
    return f"Combat began in {territory_name} between {factions_str} ({sides_count} sides)"


def combat_started_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_STARTED event."""
    territory_id = event_data.get('territory_id', 'Unknown')
    faction_names = event_data.get('faction_names', [])
    participating_units = event_data.get('participating_units', [])

    factions_str = ', '.join(faction_names) if faction_names else 'unknown'
    return f"Combat at T{territory_id}: {factions_str} ({len(participating_units)} units)"


def combat_action_conflict_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_ACTION_CONFLICT event."""
    territory_id = event_data.get('territory_id', 'Unknown')
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    action_a = event_data.get('action_a', 'action')
    action_b = event_data.get('action_b', 'action')
    recommendation = event_data.get('recommendation', '')

    return (f"Action conflict in {territory_id}: {faction_a} ({action_a}) vs {faction_b} ({action_b}). "
            f"{recommendation}")


def combat_action_conflict_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_ACTION_CONFLICT event."""
    territory_id = event_data.get('territory_id', 'Unknown')
    faction_a = event_data.get('faction_a_name', 'Unknown')
    faction_b = event_data.get('faction_b_name', 'Unknown')
    action_a = event_data.get('action_a', 'action')
    action_b = event_data.get('action_b', 'action')

    return f"Action conflict at T{territory_id}: {faction_a}({action_a}) vs {faction_b}({action_b})"


def combat_org_damage_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_ORG_DAMAGE event."""
    unit_name = event_data.get('unit_name', event_data.get('unit_id', 'Unknown'))
    damage = event_data.get('damage', 0)
    new_org = event_data.get('new_organization', 0)
    territory_id = event_data.get('territory_id', 'Unknown')

    return f"{unit_name} took {damage} organization damage in combat at {territory_id} (org: {new_org})"


def combat_org_damage_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_ORG_DAMAGE event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    damage = event_data.get('damage', 0)
    new_org = event_data.get('new_organization', 0)

    return f"{unit_id}: -{damage} org -> {new_org}"


def combat_unit_disbanded_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_UNIT_DISBANDED event."""
    unit_name = event_data.get('unit_name', event_data.get('unit_id', 'Unknown'))
    territory_id = event_data.get('territory_id', 'Unknown')

    return f"{unit_name} was disbanded in combat at {territory_id}"


def combat_unit_disbanded_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_UNIT_DISBANDED event."""
    unit_id = event_data.get('unit_id', 'Unknown')
    territory_id = event_data.get('territory_id', 'Unknown')

    return f"{unit_id} disbanded at T{territory_id}"


def combat_retreat_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_RETREAT event."""
    units = event_data.get('units', [])
    from_territory = event_data.get('from_territory', 'Unknown')
    to_territory = event_data.get('to_territory', 'Unknown')
    faction_names = event_data.get('faction_names', [])

    units_str = ', '.join(units) if units else 'Units'
    factions_str = f" ({', '.join(faction_names)})" if faction_names else ''

    return f"{units_str}{factions_str} retreated from {from_territory} to {to_territory}"


def combat_retreat_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_RETREAT event."""
    units = event_data.get('units', [])
    from_territory = event_data.get('from_territory', 'Unknown')
    to_territory = event_data.get('to_territory', 'Unknown')

    units_str = ', '.join(units) if units else 'Units'
    return f"{units_str}: T{from_territory} -> T{to_territory} (retreat)"


def combat_ended_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_ENDED event."""
    territory_name = event_data.get('territory_name', 'Unknown')
    rounds = event_data.get('rounds', 1)
    victor_factions = event_data.get('victor_factions', [])

    if victor_factions:
        victor_str = ', '.join(victor_factions)
        return f"Combat ended in {territory_name} after {rounds} round(s). Victor: {victor_str}"
    else:
        return f"Combat ended in {territory_name} after {rounds} round(s). No clear victor."


def combat_ended_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_ENDED event."""
    territory_id = event_data.get('territory_id', 'Unknown')
    rounds = event_data.get('rounds', 1)
    victor_factions = event_data.get('victor_factions', [])
    remaining_units = event_data.get('remaining_units', [])

    victor_str = ', '.join(victor_factions) if victor_factions else 'none'
    return f"Combat ended T{territory_id}: {rounds}r, victor={victor_str}, {len(remaining_units)} units remain"


def combat_max_rounds_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for COMBAT_MAX_ROUNDS event."""
    territory_name = event_data.get('territory_name', 'Unknown')
    rounds = event_data.get('rounds', 10)
    warning = event_data.get('warning', '')

    return f"Combat in {territory_name} reached maximum rounds ({rounds}). {warning}"


def combat_max_rounds_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for COMBAT_MAX_ROUNDS event."""
    territory_id = event_data.get('territory_id', 'Unknown')
    rounds = event_data.get('rounds', 10)

    return f"WARNING: Combat at T{territory_id} hit max rounds ({rounds})"


def territory_captured_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for TERRITORY_CAPTURED event."""
    territory_name = event_data.get('territory_name', event_data.get('territory_id', 'Unknown'))
    new_controller_name = event_data.get('new_controller_name', 'Unknown')
    new_controller_type = event_data.get('new_controller_type', 'faction')

    return f"{territory_name} was captured by {new_controller_name}"


def territory_captured_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for TERRITORY_CAPTURED event."""
    territory_id = event_data.get('territory_id', 'Unknown')
    new_controller_name = event_data.get('new_controller_name', 'Unknown')
    capturing_units = event_data.get('capturing_units', [])

    units_str = ', '.join(capturing_units) if capturing_units else 'unknown units'
    return f"T{territory_id} captured by {new_controller_name} ({units_str})"


def building_combat_damage_character_line(event_data: Dict[str, Any], character_id: Optional[int] = None) -> str:
    """Generate character report line for BUILDING_COMBAT_DAMAGE event."""
    building_name = event_data.get('building_name', event_data.get('building_id', 'Unknown'))
    territory_id = event_data.get('territory_id', 'Unknown')
    old_durability = event_data.get('old_durability', 0)
    new_durability = event_data.get('new_durability', 0)
    damage_reason = event_data.get('damage_reason', 'combat')

    reason_str = "due to territory capture" if damage_reason == 'territory_capture' else "in combat"
    return f"{building_name} in {territory_id} lost 1 durability {reason_str} ({old_durability} -> {new_durability})"


def building_combat_damage_gm_line(event_data: Dict[str, Any]) -> str:
    """Generate GM report line for BUILDING_COMBAT_DAMAGE event."""
    building_id = event_data.get('building_id', 'Unknown')
    territory_id = event_data.get('territory_id', 'Unknown')
    new_durability = event_data.get('new_durability', 0)

    return f"Building {building_id} at T{territory_id}: durability -> {new_durability}"
