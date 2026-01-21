"""
Event logging module for turn resolution reports.

This module provides a centralized registry of event handlers for generating
character and GM report lines for different event types.
"""
from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass

from .faction_events import (
    join_faction_character_line,
    join_faction_gm_line,
    join_faction_completed_character_line,
    join_faction_completed_gm_line,
    join_faction_pending_character_line,
    join_faction_pending_gm_line,
    leave_faction_character_line,
    leave_faction_gm_line,
    kick_from_faction_character_line,
    kick_from_faction_gm_line,
    order_failed_character_line,
    order_failed_gm_line,
    vp_assignment_started_character_line,
    vp_assignment_started_gm_line,
    vp_assignment_active_character_line,
    vp_assignment_active_gm_line,
    vp_assignment_cancelled_character_line,
    vp_assignment_cancelled_gm_line,
    alliance_pending_character_line,
    alliance_pending_gm_line,
    alliance_formed_character_line,
    alliance_formed_gm_line,
    alliance_dissolved_character_line,
    alliance_dissolved_gm_line,
    war_declared_character_line,
    war_declared_gm_line,
    war_joined_character_line,
    war_joined_gm_line,
    war_ally_dragged_in_character_line,
    war_ally_dragged_in_gm_line,
    war_production_bonus_character_line,
    war_production_bonus_gm_line,
)

from .movement_events import (
    transit_complete_character_line,
    transit_complete_gm_line,
    transit_progress_character_line,
    transit_progress_gm_line,
    movement_blocked_character_line,
    movement_blocked_gm_line,
    engagement_detected_character_line,
    engagement_detected_gm_line,
    unit_observed_character_line,
    unit_observed_gm_line,
)

from .resource_events import (
    resource_collection_character_line,
    resource_collection_gm_line,
    resource_transfer_success_character_line,
    resource_transfer_success_gm_line,
    resource_transfer_partial_character_line,
    resource_transfer_partial_gm_line,
    resource_transfer_failed_character_line,
    resource_transfer_failed_gm_line,
    transfer_cancelled_character_line,
    transfer_cancelled_gm_line,
    faction_territory_production_character_line,
    faction_territory_production_gm_line,
    war_bonus_production_character_line,
    war_bonus_production_gm_line,
)

from .upkeep_events import (
    upkeep_summary_character_line,
    upkeep_summary_gm_line,
    upkeep_total_deficit_character_line,
    upkeep_total_deficit_gm_line,
    upkeep_paid_character_line,
    upkeep_paid_gm_line,
    upkeep_deficit_character_line,
    upkeep_deficit_gm_line,
    unit_dissolved_character_line,
    unit_dissolved_gm_line,
    faction_spending_character_line,
    faction_spending_gm_line,
    faction_spending_partial_character_line,
    faction_spending_partial_gm_line,
)

from .unit_events import (
    commander_assigned_character_line,
    commander_assigned_gm_line,
)

from .organization_events import (
    unit_disbanded_character_line,
    unit_disbanded_gm_line,
    org_recovery_character_line,
    org_recovery_gm_line,
)

from .construction_events import (
    unit_mobilized_character_line,
    unit_mobilized_gm_line,
    mobilization_failed_character_line,
    mobilization_failed_gm_line,
    building_constructed_character_line,
    building_constructed_gm_line,
    construction_failed_character_line,
    construction_failed_gm_line,
)

from .building_upkeep_events import (
    building_upkeep_paid_character_line,
    building_upkeep_paid_gm_line,
    building_upkeep_deficit_character_line,
    building_upkeep_deficit_gm_line,
    building_destroyed_character_line,
    building_destroyed_gm_line,
)


@dataclass
class EventHandler:
    """Container for event handler functions."""
    get_character_line: Callable[[Dict[str, Any], Optional[int]], str]
    get_gm_line: Callable[[Dict[str, Any]], str]


# Registry of all event handlers
EVENT_HANDLERS: Dict[str, EventHandler] = {
    # Faction events
    'JOIN_FACTION': EventHandler(
        get_character_line=join_faction_character_line,
        get_gm_line=join_faction_gm_line
    ),
    'JOIN_FACTION_COMPLETED': EventHandler(
        get_character_line=join_faction_completed_character_line,
        get_gm_line=join_faction_completed_gm_line
    ),
    'JOIN_FACTION_PENDING': EventHandler(
        get_character_line=join_faction_pending_character_line,
        get_gm_line=join_faction_pending_gm_line
    ),
    'LEAVE_FACTION': EventHandler(
        get_character_line=leave_faction_character_line,
        get_gm_line=leave_faction_gm_line
    ),
    'KICK_FROM_FACTION': EventHandler(
        get_character_line=kick_from_faction_character_line,
        get_gm_line=kick_from_faction_gm_line
    ),
    'ORDER_FAILED': EventHandler(
        get_character_line=order_failed_character_line,
        get_gm_line=order_failed_gm_line
    ),
    'VP_ASSIGNMENT_STARTED': EventHandler(
        get_character_line=vp_assignment_started_character_line,
        get_gm_line=vp_assignment_started_gm_line
    ),
    'VP_ASSIGNMENT_ACTIVE': EventHandler(
        get_character_line=vp_assignment_active_character_line,
        get_gm_line=vp_assignment_active_gm_line
    ),
    'VP_ASSIGNMENT_CANCELLED': EventHandler(
        get_character_line=vp_assignment_cancelled_character_line,
        get_gm_line=vp_assignment_cancelled_gm_line
    ),

    # Alliance events
    'ALLIANCE_PENDING': EventHandler(
        get_character_line=alliance_pending_character_line,
        get_gm_line=alliance_pending_gm_line
    ),
    'ALLIANCE_FORMED': EventHandler(
        get_character_line=alliance_formed_character_line,
        get_gm_line=alliance_formed_gm_line
    ),
    'ALLIANCE_DISSOLVED': EventHandler(
        get_character_line=alliance_dissolved_character_line,
        get_gm_line=alliance_dissolved_gm_line
    ),

    # War events
    'WAR_DECLARED': EventHandler(
        get_character_line=war_declared_character_line,
        get_gm_line=war_declared_gm_line
    ),
    'WAR_JOINED': EventHandler(
        get_character_line=war_joined_character_line,
        get_gm_line=war_joined_gm_line
    ),
    'WAR_ALLY_DRAGGED_IN': EventHandler(
        get_character_line=war_ally_dragged_in_character_line,
        get_gm_line=war_ally_dragged_in_gm_line
    ),
    'WAR_PRODUCTION_BONUS': EventHandler(
        get_character_line=war_production_bonus_character_line,
        get_gm_line=war_production_bonus_gm_line
    ),

    # Movement events
    'TRANSIT_COMPLETE': EventHandler(
        get_character_line=transit_complete_character_line,
        get_gm_line=transit_complete_gm_line
    ),
    'TRANSIT_PROGRESS': EventHandler(
        get_character_line=transit_progress_character_line,
        get_gm_line=transit_progress_gm_line
    ),
    'MOVEMENT_BLOCKED': EventHandler(
        get_character_line=movement_blocked_character_line,
        get_gm_line=movement_blocked_gm_line
    ),
    'ENGAGEMENT_DETECTED': EventHandler(
        get_character_line=engagement_detected_character_line,
        get_gm_line=engagement_detected_gm_line
    ),
    'UNIT_OBSERVED': EventHandler(
        get_character_line=unit_observed_character_line,
        get_gm_line=unit_observed_gm_line
    ),

    # Resource events
    'RESOURCE_COLLECTION': EventHandler(
        get_character_line=resource_collection_character_line,
        get_gm_line=resource_collection_gm_line
    ),
    'TERRITORY_PRODUCTION': EventHandler(
        get_character_line=resource_collection_character_line,
        get_gm_line=resource_collection_gm_line
    ),
    'CHARACTER_PRODUCTION': EventHandler(
        get_character_line=resource_collection_character_line,
        get_gm_line=resource_collection_gm_line
    ),
    'FACTION_TERRITORY_PRODUCTION': EventHandler(
        get_character_line=faction_territory_production_character_line,
        get_gm_line=faction_territory_production_gm_line
    ),
    'RESOURCE_TRANSFER_SUCCESS': EventHandler(
        get_character_line=resource_transfer_success_character_line,
        get_gm_line=resource_transfer_success_gm_line
    ),
    'RESOURCE_TRANSFER_PARTIAL': EventHandler(
        get_character_line=resource_transfer_partial_character_line,
        get_gm_line=resource_transfer_partial_gm_line
    ),
    'RESOURCE_TRANSFER_FAILED': EventHandler(
        get_character_line=resource_transfer_failed_character_line,
        get_gm_line=resource_transfer_failed_gm_line
    ),
    'TRANSFER_CANCELLED': EventHandler(
        get_character_line=transfer_cancelled_character_line,
        get_gm_line=transfer_cancelled_gm_line
    ),
    'WAR_BONUS_PRODUCTION': EventHandler(
        get_character_line=war_bonus_production_character_line,
        get_gm_line=war_bonus_production_gm_line
    ),

    # Upkeep events
    'UPKEEP_SUMMARY': EventHandler(
        get_character_line=upkeep_summary_character_line,
        get_gm_line=upkeep_summary_gm_line
    ),
    'UPKEEP_TOTAL_DEFICIT': EventHandler(
        get_character_line=upkeep_total_deficit_character_line,
        get_gm_line=upkeep_total_deficit_gm_line
    ),
    'UPKEEP_PAID': EventHandler(
        get_character_line=upkeep_paid_character_line,
        get_gm_line=upkeep_paid_gm_line
    ),
    'UPKEEP_DEFICIT': EventHandler(
        get_character_line=upkeep_deficit_character_line,
        get_gm_line=upkeep_deficit_gm_line
    ),
    'UNIT_DISSOLVED': EventHandler(
        get_character_line=unit_dissolved_character_line,
        get_gm_line=unit_dissolved_gm_line
    ),
    'FACTION_SPENDING': EventHandler(
        get_character_line=faction_spending_character_line,
        get_gm_line=faction_spending_gm_line
    ),
    'FACTION_SPENDING_PARTIAL': EventHandler(
        get_character_line=faction_spending_partial_character_line,
        get_gm_line=faction_spending_partial_gm_line
    ),

    # Unit events
    'COMMANDER_ASSIGNED': EventHandler(
        get_character_line=commander_assigned_character_line,
        get_gm_line=commander_assigned_gm_line
    ),

    # Organization events
    'UNIT_DISBANDED': EventHandler(
        get_character_line=unit_disbanded_character_line,
        get_gm_line=unit_disbanded_gm_line
    ),
    'ORG_RECOVERY': EventHandler(
        get_character_line=org_recovery_character_line,
        get_gm_line=org_recovery_gm_line
    ),

    # Construction and mobilization events
    'UNIT_MOBILIZED': EventHandler(
        get_character_line=unit_mobilized_character_line,
        get_gm_line=unit_mobilized_gm_line
    ),
    'MOBILIZATION_FAILED': EventHandler(
        get_character_line=mobilization_failed_character_line,
        get_gm_line=mobilization_failed_gm_line
    ),
    'BUILDING_CONSTRUCTED': EventHandler(
        get_character_line=building_constructed_character_line,
        get_gm_line=building_constructed_gm_line
    ),
    'CONSTRUCTION_FAILED': EventHandler(
        get_character_line=construction_failed_character_line,
        get_gm_line=construction_failed_gm_line
    ),

    # Building upkeep events
    'BUILDING_UPKEEP_PAID': EventHandler(
        get_character_line=building_upkeep_paid_character_line,
        get_gm_line=building_upkeep_paid_gm_line
    ),
    'BUILDING_UPKEEP_DEFICIT': EventHandler(
        get_character_line=building_upkeep_deficit_character_line,
        get_gm_line=building_upkeep_deficit_gm_line
    ),
    'BUILDING_DESTROYED': EventHandler(
        get_character_line=building_destroyed_character_line,
        get_gm_line=building_destroyed_gm_line
    ),
}


__all__ = ['EVENT_HANDLERS', 'EventHandler']
