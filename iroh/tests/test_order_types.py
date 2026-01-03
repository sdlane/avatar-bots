"""
Test order types configuration.
"""
import pytest
from order_types import OrderType, TurnPhase, ORDER_PHASE_MAP, ORDER_PRIORITY_MAP, OrderStatus


# Test individual order types exist
def test_faction_order_types_exist():
    """Test that faction-related order types exist."""
    assert OrderType.JOIN_FACTION.value == "JOIN_FACTION"
    assert OrderType.LEAVE_FACTION.value == "LEAVE_FACTION"
    assert OrderType.KICK_FROM_FACTION.value == "KICK_FROM_FACTION"


def test_movement_order_types_exist():
    """Test that movement-related order types exist."""
    assert OrderType.TRANSIT.value == "TRANSIT"


def test_resource_transfer_order_types_exist():
    """Test that RESOURCE_TRANSFER and CANCEL_TRANSFER order types exist."""
    assert OrderType.RESOURCE_TRANSFER.value == "RESOURCE_TRANSFER"
    assert OrderType.CANCEL_TRANSFER.value == "CANCEL_TRANSFER"


# Test phase mappings
def test_faction_orders_phase_mapping():
    """Test that faction orders map to BEGINNING phase."""
    assert ORDER_PHASE_MAP[OrderType.JOIN_FACTION] == TurnPhase.BEGINNING
    assert ORDER_PHASE_MAP[OrderType.LEAVE_FACTION] == TurnPhase.BEGINNING
    assert ORDER_PHASE_MAP[OrderType.KICK_FROM_FACTION] == TurnPhase.BEGINNING


def test_movement_orders_phase_mapping():
    """Test that movement orders map to MOVEMENT phase."""
    assert ORDER_PHASE_MAP[OrderType.TRANSIT] == TurnPhase.MOVEMENT


def test_resource_transfer_phase_mapping():
    """Test that resource transfer orders map to RESOURCE_TRANSFER phase."""
    assert ORDER_PHASE_MAP[OrderType.RESOURCE_TRANSFER] == TurnPhase.RESOURCE_TRANSFER
    assert ORDER_PHASE_MAP[OrderType.CANCEL_TRANSFER] == TurnPhase.RESOURCE_TRANSFER


# Test priority orderings
def test_faction_orders_priority_ordering():
    """Test that LEAVE/KICK have higher priority than JOIN within BEGINNING phase."""
    assert ORDER_PRIORITY_MAP[OrderType.LEAVE_FACTION] == 0
    assert ORDER_PRIORITY_MAP[OrderType.KICK_FROM_FACTION] == 0
    assert ORDER_PRIORITY_MAP[OrderType.JOIN_FACTION] == 1
    # Leaves and kicks execute before joins
    assert ORDER_PRIORITY_MAP[OrderType.LEAVE_FACTION] < ORDER_PRIORITY_MAP[OrderType.JOIN_FACTION]
    assert ORDER_PRIORITY_MAP[OrderType.KICK_FROM_FACTION] < ORDER_PRIORITY_MAP[OrderType.JOIN_FACTION]


def test_movement_orders_priority():
    """Test that movement orders have priority 0 (FIFO ordering)."""
    assert ORDER_PRIORITY_MAP[OrderType.TRANSIT] == 0


def test_resource_transfer_priority_ordering():
    """Test that CANCEL_TRANSFER has higher priority (lower number) than RESOURCE_TRANSFER."""
    assert ORDER_PRIORITY_MAP[OrderType.CANCEL_TRANSFER] == 0
    assert ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER] == 1
    assert ORDER_PRIORITY_MAP[OrderType.CANCEL_TRANSFER] < ORDER_PRIORITY_MAP[OrderType.RESOURCE_TRANSFER]


# Test completeness
def test_all_order_types_have_phase_mapping():
    """Test that all order types have a phase mapping."""
    for order_type in OrderType:
        assert order_type in ORDER_PHASE_MAP, f"{order_type} missing from ORDER_PHASE_MAP"


def test_all_order_types_have_priority():
    """Test that all order types have a priority mapping."""
    for order_type in OrderType:
        assert order_type in ORDER_PRIORITY_MAP, f"{order_type} missing from ORDER_PRIORITY_MAP"


def test_total_order_type_count():
    """Test that we have the expected number of order types."""
    # JOIN_FACTION, LEAVE_FACTION, KICK_FROM_FACTION, TRANSIT, RESOURCE_TRANSFER, CANCEL_TRANSFER
    assert len(OrderType) == 6


# Test order status values
def test_order_status_values():
    """Test that all required order status values exist."""
    assert OrderStatus.PENDING.value == "PENDING"
    assert OrderStatus.ONGOING.value == "ONGOING"
    assert OrderStatus.SUCCESS.value == "SUCCESS"
    assert OrderStatus.FAILED.value == "FAILED"
    assert OrderStatus.CANCELLED.value == "CANCELLED"


def test_order_status_count():
    """Test that we have the expected number of order statuses."""
    assert len(OrderStatus) == 5


# Test turn phase values
def test_all_turn_phases_exist():
    """Test that all turn phases are defined."""
    assert TurnPhase.BEGINNING.value == "BEGINNING"
    assert TurnPhase.MOVEMENT.value == "MOVEMENT"
    assert TurnPhase.COMBAT.value == "COMBAT"
    assert TurnPhase.RESOURCE_COLLECTION.value == "RESOURCE_COLLECTION"
    assert TurnPhase.RESOURCE_TRANSFER.value == "RESOURCE_TRANSFER"
    assert TurnPhase.ENCIRCLEMENT.value == "ENCIRCLEMENT"
    assert TurnPhase.UPKEEP.value == "UPKEEP"
    assert TurnPhase.ORGANIZATION.value == "ORGANIZATION"
    assert TurnPhase.CONSTRUCTION.value == "CONSTRUCTION"


def test_turn_phase_count():
    """Test that we have the expected number of turn phases."""
    assert len(TurnPhase) == 9
