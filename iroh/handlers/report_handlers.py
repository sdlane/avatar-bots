"""
Handlers for generating turn reports from historical turn log data.
"""
import asyncpg
from typing import Tuple, List, Dict, Optional
from db import Character, TurnLog, WargameConfig
import logging

logger = logging.getLogger(__name__)


async def generate_character_report(
    conn: asyncpg.Connection,
    user_id: int,
    guild_id: int,
    turn_number: Optional[int] = None
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Generate a turn report for a character.

    Args:
        conn: Database connection
        user_id: Discord user ID
        guild_id: Guild ID
        turn_number: Optional turn number (defaults to most recent turn)

    Returns:
        (success, message, data_dict)
        data_dict contains:
        - character: Character object
        - turn_number: int
        - events: List of event dicts
    """
    # Get character for this user
    character = await Character.fetch_by_user(conn, user_id, guild_id)
    if not character:
        return False, "You don't have a character in this wargame.", None

    # Get wargame config
    config = await WargameConfig.fetch(conn, guild_id)
    if not config:
        return False, "No wargame configuration found for this server.", None

    # Determine turn number
    if turn_number is None:
        turn_number = config.current_turn

    # Validate turn number
    if turn_number < 0 or turn_number > config.current_turn:
        return False, f"Invalid turn number. Must be between 0 and {config.current_turn}.", None

    # Fetch all turn logs for this turn
    turn_logs = await TurnLog.fetch_by_turn(conn, turn_number, guild_id)

    # Convert TurnLog objects to event dicts
    all_events = []
    for log in turn_logs:
        all_events.append({
            'phase': log.phase,
            'event_type': log.event_type,
            'entity_type': log.entity_type,
            'entity_id': log.entity_id,
            'event_data': log.event_data
        })

    # Filter events relevant to this character using affected_character_ids
    character_events = []
    for event in all_events:
        event_data = event.get('event_data', {})
        affected_ids = event_data.get('affected_character_ids', [])

        if character.id in affected_ids:
            character_events.append(event)

    return True, "Report generated successfully.", {
        'character': character,
        'turn_number': turn_number,
        'events': character_events
    }


async def generate_gm_report(
    conn: asyncpg.Connection,
    guild_id: int,
    turn_number: Optional[int] = None
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Generate a GM turn report.

    Args:
        conn: Database connection
        guild_id: Guild ID
        turn_number: Optional turn number (defaults to most recent turn)

    Returns:
        (success, message, data_dict)
        data_dict contains:
        - turn_number: int
        - events: List of event dicts
        - summary: Dict with event counts by phase
    """
    # Get wargame config
    config = await WargameConfig.fetch(conn, guild_id)
    if not config:
        return False, "No wargame configuration found for this server.", None

    # Determine turn number
    if turn_number is None:
        turn_number = config.current_turn

    # Validate turn number
    if turn_number < 0 or turn_number > config.current_turn:
        return False, f"Invalid turn number. Must be between 0 and {config.current_turn}.", None

    # Fetch all turn logs for this turn
    turn_logs = await TurnLog.fetch_by_turn(conn, turn_number, guild_id)

    # Convert TurnLog objects to event dicts
    all_events = []
    for log in turn_logs:
        all_events.append({
            'phase': log.phase,
            'event_type': log.event_type,
            'entity_type': log.entity_type,
            'entity_id': log.entity_id,
            'event_data': log.event_data
        })

    # Generate summary
    summary = {
        'total_events': len(all_events),
        'beginning_events': len([e for e in all_events if e['phase'] == 'BEGINNING']),
        'movement_events': len([e for e in all_events if e['phase'] == 'MOVEMENT']),
        'resource_collection_events': len([e for e in all_events if e['phase'] == 'RESOURCE_COLLECTION']),
        'upkeep_events': len([e for e in all_events if e['phase'] == 'UPKEEP'])
    }

    return True, "Report generated successfully.", {
        'turn_number': turn_number,
        'events': all_events,
        'summary': summary
    }
