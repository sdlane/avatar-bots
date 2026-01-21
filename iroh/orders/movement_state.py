"""
Movement state tracking for the movement phase.

This module contains the MovementUnitState dataclass used to track
in-memory state of units during tick-based movement resolution.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from db import Order, Unit


@dataclass
class MovementUnitState:
    """
    In-memory state for tracking a unit group's movement during turn resolution.

    This state is rebuilt each turn from the order's result_data and is not persisted
    directly - instead, relevant fields are saved back to result_data after processing.

    Attributes:
        units: List of Unit objects moving together
        order: The Order object controlling this movement
        total_movement_points: Base movement points for this turn (slowest unit + bonuses)
        remaining_mp: Movement points remaining this turn
        status: Current movement status (MOVING, ENGAGED, PATH_COMPLETE, OUT_OF_MP)
        current_territory_id: Where the units currently are
        path_index: Current position in the path (0 = starting position)
        action: Movement action type (transit, transport, patrol, raid, capture, siege)
        speed: Optional speed limit for patrol (total MP to expend per turn)
        territories_entered: List of territory IDs entered this turn
        blocked_at: Territory ID where movement was blocked (if any)
        mp_expended_this_turn: Total MP spent this turn (for patrol speed tracking)
    """
    units: List[Unit]
    order: Order
    total_movement_points: int
    remaining_mp: int
    status: str = "MOVING"  # MOVING, ENGAGED, PATH_COMPLETE, OUT_OF_MP
    current_territory_id: str = ""
    path_index: int = 0
    action: str = "transit"
    speed: Optional[int] = None
    territories_entered: List[str] = field(default_factory=list)
    blocked_at: Optional[str] = None
    mp_expended_this_turn: int = 0

    def get_path(self) -> List[str]:
        """Get the full path from the order data."""
        return self.order.order_data.get('path', [])

    def get_next_territory(self) -> Optional[str]:
        """Get the next territory in the path, or None if at end."""
        path = self.get_path()
        next_index = self.path_index + 1
        if next_index < len(path):
            return path[next_index]
        return None

    def is_path_complete(self) -> bool:
        """Check if the unit has reached the end of its path."""
        path = self.get_path()
        return self.path_index >= len(path) - 1

    def is_patrol(self) -> bool:
        """Check if this is a patrol order."""
        return self.action == "patrol"

    def can_continue_patrol(self) -> bool:
        """
        Check if a patrol unit can continue moving this turn.

        Patrol units have a speed parameter that limits total MP expended per turn.
        If speed is None, patrol can continue indefinitely (no limit).
        """
        if not self.is_patrol():
            return True
        if self.speed is None:
            return True
        return self.mp_expended_this_turn < self.speed


# Movement status constants
class MovementStatus:
    """Status values for movement state."""
    MOVING = "MOVING"              # Unit is actively moving
    ENGAGED = "ENGAGED"            # Unit is engaged in combat (placeholder)
    PATH_COMPLETE = "PATH_COMPLETE"  # Unit has reached end of path
    OUT_OF_MP = "OUT_OF_MP"        # Unit ran out of movement points this turn


# Movement action constants
class MovementAction:
    """Action types for movement orders."""
    TRANSIT = "transit"      # Standard movement, +1 MP bonus
    TRANSPORT = "transport"  # Transporting units, +1 MP bonus
    PATROL = "patrol"        # Looping patrol, no MP bonus
    RAID = "raid"           # Raiding action (future)
    CAPTURE = "capture"     # Territory capture (future)
    SIEGE = "siege"         # Siege action (future)

    # Actions that get +1 movement bonus
    BONUS_ACTIONS = [TRANSIT, TRANSPORT]
