"""
Order type enums and mappings for the wargame turn system.
"""
from enum import Enum
from typing import Dict

class OrderType(Enum):
    """Types of orders that can be submitted."""
    JOIN_FACTION = "JOIN_FACTION"
    LEAVE_FACTION = "LEAVE_FACTION"
    TRANSIT = "TRANSIT"


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
    OrderType.TRANSIT: TurnPhase.MOVEMENT,
}


# Priority within each phase (lower = executes first within the phase)
ORDER_PRIORITY_MAP: Dict[OrderType, int] = {
    OrderType.LEAVE_FACTION: 0,   # Execute leaves before joins
    OrderType.JOIN_FACTION: 1,
    OrderType.TRANSIT: 0,          # All transit orders at same priority (FIFO by submitted_at)
}


# Order status values
class OrderStatus(Enum):
    """Status values for orders."""
    PENDING = "PENDING"          # Waiting to be executed
    ONGOING = "ONGOING"          # In progress (multi-turn orders)
    SUCCESS = "SUCCESS"          # Successfully completed
    FAILED = "FAILED"            # Failed to execute
    CANCELLED = "CANCELLED"      # Cancelled by player