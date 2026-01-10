"""
Order type enums and mappings for the wargame turn system.
"""
from enum import Enum
from typing import Dict

class OrderType(Enum):
    """Types of orders that can be submitted."""
    JOIN_FACTION = "JOIN_FACTION"
    LEAVE_FACTION = "LEAVE_FACTION"
    KICK_FROM_FACTION = "KICK_FROM_FACTION"
    ASSIGN_COMMANDER = "ASSIGN_COMMANDER"
    ASSIGN_VICTORY_POINTS = "ASSIGN_VICTORY_POINTS"
    MAKE_ALLIANCE = "MAKE_ALLIANCE"
    TRANSIT = "TRANSIT"
    RESOURCE_TRANSFER = "RESOURCE_TRANSFER"
    CANCEL_TRANSFER = "CANCEL_TRANSFER"


class TurnPhase(Enum):
    """Phases of turn resolution."""
    BEGINNING = "BEGINNING"
    MOVEMENT = "MOVEMENT"
    COMBAT = "COMBAT"
    RESOURCE_COLLECTION = "RESOURCE_COLLECTION"
    RESOURCE_TRANSFER = "RESOURCE_TRANSFER"
    ENCIRCLEMENT = "ENCIRCLEMENT"
    UPKEEP = "UPKEEP"
    ORGANIZATION = "ORGANIZATION"
    CONSTRUCTION = "CONSTRUCTION"


# Map each order type to the phase in which it executes
ORDER_PHASE_MAP: Dict[OrderType, TurnPhase] = {
    OrderType.JOIN_FACTION: TurnPhase.BEGINNING,
    OrderType.LEAVE_FACTION: TurnPhase.BEGINNING,
    OrderType.KICK_FROM_FACTION: TurnPhase.BEGINNING,
    OrderType.ASSIGN_COMMANDER: TurnPhase.BEGINNING,
    OrderType.ASSIGN_VICTORY_POINTS: TurnPhase.BEGINNING,
    OrderType.MAKE_ALLIANCE: TurnPhase.BEGINNING,
    OrderType.TRANSIT: TurnPhase.MOVEMENT,
    OrderType.RESOURCE_TRANSFER: TurnPhase.RESOURCE_TRANSFER,
    OrderType.CANCEL_TRANSFER: TurnPhase.RESOURCE_TRANSFER,
}


# Priority within each phase (lower = executes first within the phase)
ORDER_PRIORITY_MAP: Dict[OrderType, int] = {
    OrderType.LEAVE_FACTION: 0,   # Execute leaves before joins
    OrderType.KICK_FROM_FACTION: 0,   # Execute kicks at same priority as leaves
    OrderType.JOIN_FACTION: 1,
    OrderType.ASSIGN_COMMANDER: 2,  # After faction orders
    OrderType.ASSIGN_VICTORY_POINTS: 3,  # After commander assignments
    OrderType.MAKE_ALLIANCE: 4,  # After VP assignments, so faction membership is settled
    OrderType.TRANSIT: 0,          # All transit orders at same priority (FIFO by submitted_at)
    OrderType.CANCEL_TRANSFER: 0,  # Process cancellations first
    OrderType.RESOURCE_TRANSFER: 1, # Then resource transfers
}


# Order status values
class OrderStatus(Enum):
    """Status values for orders."""
    PENDING = "PENDING"          # Waiting to be executed
    ONGOING = "ONGOING"          # In progress (multi-turn orders)
    SUCCESS = "SUCCESS"          # Successfully completed
    FAILED = "FAILED"            # Failed to execute
    CANCELLED = "CANCELLED"      # Cancelled by player


# Unit status values
class UnitStatus(Enum):
    """Status values for units."""
    ACTIVE = "ACTIVE"            # Unit is active and operational
    DISBANDED = "DISBANDED"      # Unit has been disbanded (organization <= 0)


# Display each phase
PHASE_ORDER = [
    TurnPhase.BEGINNING.value,
    TurnPhase.MOVEMENT.value,
    TurnPhase.COMBAT.value,
    TurnPhase.RESOURCE_COLLECTION.value,
    TurnPhase.RESOURCE_TRANSFER.value,
    TurnPhase.ENCIRCLEMENT.value,
    TurnPhase.UPKEEP.value,
    TurnPhase.ORGANIZATION.value,
    TurnPhase.CONSTRUCTION.value]