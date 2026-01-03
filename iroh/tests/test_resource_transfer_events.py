"""
Test resource transfer event handlers.
"""
import pytest
from event_logging.resource_events import (
    resource_transfer_success_character_line,
    resource_transfer_success_gm_line,
    resource_transfer_partial_character_line,
    resource_transfer_partial_gm_line,
    resource_transfer_failed_character_line,
    resource_transfer_failed_gm_line,
    transfer_cancelled_character_line,
    transfer_cancelled_gm_line,
)


# Test RESOURCE_TRANSFER_SUCCESS event handlers
def test_resource_transfer_success_character_line_full_resources():
    """Test success event with multiple resources."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'transferred_resources': {
            'ore': 10,
            'lumber': 5,
            'coal': 3,
            'rations': 8,
            'cloth': 2
        }
    }
    result = resource_transfer_success_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "⛏️10" in result
    assert "🪵5" in result
    assert "⚫3" in result
    assert "🍖8" in result
    assert "🧵2" in result


def test_resource_transfer_success_character_line_single_resource():
    """Test success event with single resource."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'transferred_resources': {
            'ore': 100
        }
    }
    result = resource_transfer_success_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "⛏️100" in result


def test_resource_transfer_success_character_line_zero_resources():
    """Test success event with zero resources."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'transferred_resources': {}
    }
    result = resource_transfer_success_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "nothing" in result


def test_resource_transfer_success_gm_line():
    """Test GM line for success event."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'transferred_resources': {
            'ore': 10,
            'lumber': 5
        }
    }
    result = resource_transfer_success_gm_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "⛏️10" in result
    assert "🪵5" in result


# Test RESOURCE_TRANSFER_PARTIAL event handlers
def test_resource_transfer_partial_character_line():
    """Test partial transfer showing requested vs transferred."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'requested_resources': {
            'ore': 100,
            'lumber': 50
        },
        'transferred_resources': {
            'ore': 30,
            'lumber': 10
        }
    }
    result = resource_transfer_partial_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "requested" in result
    assert "transferred" in result
    assert "⛏️100" in result  # requested
    assert "⛏️30" in result   # transferred


def test_resource_transfer_partial_gm_line():
    """Test GM line for partial transfer."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'requested_resources': {
            'ore': 100
        },
        'transferred_resources': {
            'ore': 30
        }
    }
    result = resource_transfer_partial_gm_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "requested" in result
    assert "sent" in result


def test_resource_transfer_partial_no_resources_transferred():
    """Test partial event when no resources were transferred."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'requested_resources': {
            'ore': 100
        },
        'transferred_resources': {}
    }
    result = resource_transfer_partial_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "nothing" in result  # no resources transferred


# Test RESOURCE_TRANSFER_FAILED event handlers
def test_resource_transfer_failed_character_line():
    """Test failed transfer with reason."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'reason': 'Sender character not found'
    }
    result = resource_transfer_failed_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "failed" in result
    assert "Sender character not found" in result


def test_resource_transfer_failed_gm_line():
    """Test GM line for failed transfer."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'reason': 'Recipient character not found'
    }
    result = resource_transfer_failed_gm_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "failed" in result
    assert "Recipient character not found" in result


def test_resource_transfer_failed_no_reason():
    """Test failed event with missing reason."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob'
    }
    result = resource_transfer_failed_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "Unknown reason" in result


# Test TRANSFER_CANCELLED event handlers
def test_transfer_cancelled_character_line():
    """Test cancelled transfer event."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob'
    }
    result = transfer_cancelled_character_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "cancelled" in result


def test_transfer_cancelled_gm_line():
    """Test GM line for cancelled transfer."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob'
    }
    result = transfer_cancelled_gm_line(event_data)
    assert "Alice" in result
    assert "Bob" in result
    assert "cancelled" in result


def test_transfer_cancelled_missing_names():
    """Test cancelled event with missing character names."""
    event_data = {}
    result = transfer_cancelled_character_line(event_data)
    assert "Unknown" in result


# Test character/GM line formatting differences
def test_character_vs_gm_line_format_difference():
    """Test that character and GM lines have different formatting."""
    event_data = {
        'from_character_name': 'Alice',
        'to_character_name': 'Bob',
        'transferred_resources': {
            'ore': 10
        }
    }
    character_line = resource_transfer_success_character_line(event_data)
    gm_line = resource_transfer_success_gm_line(event_data)

    # Both should contain the same basic info
    assert "Alice" in character_line and "Alice" in gm_line
    assert "Bob" in character_line and "Bob" in gm_line
    assert "⛏️10" in character_line and "⛏️10" in gm_line

    # But they should use different wording
    assert "successful" in character_line
    assert "successful" not in gm_line
