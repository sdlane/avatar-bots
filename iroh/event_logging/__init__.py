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
)

from .movement_events import (
    transit_complete_character_line,
    transit_complete_gm_line,
    transit_progress_character_line,
    transit_progress_gm_line,
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

    # Movement events
    'TRANSIT_COMPLETE': EventHandler(
        get_character_line=transit_complete_character_line,
        get_gm_line=transit_complete_gm_line
    ),
    'TRANSIT_PROGRESS': EventHandler(
        get_character_line=transit_progress_character_line,
        get_gm_line=transit_progress_gm_line
    ),

    # Resource events
    'RESOURCE_COLLECTION': EventHandler(
        get_character_line=resource_collection_character_line,
        get_gm_line=resource_collection_gm_line
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
}


__all__ = ['EVENT_HANDLERS', 'EventHandler']
