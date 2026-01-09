"""
Handlers for generating turn reports from historical turn log data.
"""
import asyncpg
from typing import Tuple, List, Dict, Optional
from db import Character, TurnLog, WargameConfig
from order_types import PHASE_ORDER
import logging

logger = logging.getLogger(__name__)


async def generate_character_report(
    conn: asyncpg.Connection,
    character: Character,
    guild_id: int,
    turn_number: int
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Generate a turn report for a specific character.

    Args:
        conn: Database connection
        character: Character object
        guild_id: Guild ID
        turn_number: Turn number to generate report for

    Returns:
        (success, message, data_dict)
        data_dict contains:
        - character: Character object
        - turn_number: int
        - events: List of TurnLog objects
    """
    # Fetch all turn logs for this turn
    turn_logs = await TurnLog.fetch_by_turn(conn, turn_number, guild_id)

    # Filter events relevant to this character using affected_character_ids
    character_events = []
    for log in turn_logs:
        event_data = log.event_data or {}
        affected_ids = event_data.get('affected_character_ids', [])

        if character.id in affected_ids:
            character_events.append(log)

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
        - events: List of TurnLog objects
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

    # Generate summary
    summary = {'total_events': len(turn_logs)}
    for phase in PHASE_ORDER:
        summary[f'{phase.lower()}_events'] = len([e for e in turn_logs if e.phase == phase])

    return True, "Report generated successfully.", {
        'turn_number': turn_number,
        'events': turn_logs,
        'summary': summary
    }
