"""
Helper functions for creating Discord embeds for turn resolution reports.
"""
import discord
from typing import List, Dict, Optional
from datetime import datetime
from order_types import PHASE_ORDER
from event_logging import EVENT_HANDLERS


def split_lines_into_chunks(lines: List[str], max_chars: int = 1000) -> List[str]:
    """Split a list of lines into chunks that fit within max_chars.

    Returns list of joined strings, each under max_chars.
    """
    if not lines:
        return []

    chunks = []
    current_chunk = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1  # +1 for newline

        if current_length + line_length > max_chars and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += line_length

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def create_orders_embed(character_name: str, orders: List[Dict]) -> discord.Embed:
    """
    Create an embed displaying a character's pending/ongoing orders.

    Args:
        character_name: Name of the character
        orders: List of order dicts with keys: order_id, order_type, status, turn_number, order_data, units

    Returns:
        Discord embed
    """
    embed = discord.Embed(
        title=f"📋 Orders for {character_name}",
        color=discord.Color.blue()
    )

    if not orders:
        embed.description = "No pending orders."
        return embed

    # Group by order type
    order_groups = {}
    for order in orders:
        order_type = order['order_type']
        if order_type not in order_groups:
            order_groups[order_type] = []
        order_groups[order_type].append(order)

    # Display each group
    for order_type, type_orders in order_groups.items():
        lines = []
        for order in type_orders:
            status_emoji = "⏳" if order['status'] == 'PENDING' else "🔄"
            line = f"{status_emoji} **{order['order_id']}** (Turn {order['turn_number']})"

            # Add type-specific details
            if order_type == 'JOIN_FACTION':
                target = order['order_data'].get('target_faction_id', 'Unknown')
                line += f" - Join `{target}`"
            elif order_type == 'LEAVE_FACTION':
                line += " - Leave faction"
            elif order_type == 'UNIT':
                units = order.get('units', [])
                path = order['order_data'].get('path', [])
                path_index = order['order_data'].get('path_index', 0)
                if units:
                    line += f"\n  Units: {', '.join(units)}"
                if path:
                    line += f"\n  Destination: Territory {path[-1]} ({path_index}/{len(path)-1} steps)"

            lines.append(line)

        embed.add_field(
            name=f"{order_type.replace('_', ' ').title()}",
            value="\n".join(lines),
            inline=False
        )

    return embed


def create_turn_status_embed(status_data: Dict) -> discord.Embed:
    """
    Create an embed displaying current turn status.

    Args:
        status_data: Dict with keys: current_turn, last_turn_time, turn_resolution_enabled,
                     pending_orders (dict by phase), total_pending

    Returns:
        Discord embed
    """
    embed = discord.Embed(
        title="🎮 Turn Status",
        color=discord.Color.gold()
    )

    # Current turn
    embed.add_field(
        name="Current Turn",
        value=str(status_data['current_turn']),
        inline=True
    )

    # Last turn time
    last_turn = status_data.get('last_turn_time')
    if last_turn:
        try:
            dt = datetime.fromisoformat(last_turn)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            time_str = last_turn
    else:
        time_str = "Never"

    embed.add_field(
        name="Last Turn Resolved",
        value=time_str,
        inline=True
    )

    # Turn resolution enabled
    enabled = status_data.get('turn_resolution_enabled', False)
    embed.add_field(
        name="Auto-Resolution",
        value="✅ Enabled" if enabled else "❌ Disabled",
        inline=True
    )

    # Pending orders by phase
    pending_orders = status_data.get('pending_orders', {})
    total_pending = status_data.get('total_pending', 0)

    if total_pending > 0:
        lines = []
        for phase, count in pending_orders.items():
            if count > 0:
                lines.append(f"• {phase}: {count}")

        embed.add_field(
            name=f"Pending Orders (Total: {total_pending})",
            value="\n".join(lines) if lines else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Pending Orders",
            value="None",
            inline=False
        )

    return embed


def create_character_turn_report_embeds(
    character_name: str,
    turn_number: int,
    events: List[Dict],
    character_id: Optional[int] = None
) -> List[discord.Embed]:
    """
    Create embeds with a character's turn report.

    Args:
        character_name: Name of the character
        turn_number: Turn number
        events: List of event dicts relevant to this character
        character_id: ID of the viewing character (for context-aware formatting)

    Returns:
        List of Discord embeds (multiple if content exceeds limits)
    """
    embed_color = discord.Color.blue()
    base_title = f"Turn {turn_number} Report: {character_name}"

    if not events:
        embed = discord.Embed(
            title=f"📊 {base_title}",
            color=embed_color,
            timestamp=datetime.now()
        )
        embed.description = "No events this turn."
        return [embed]

    # Group events by phase
    phases = {}
    for event in events:
        phase = event.phase or 'UNKNOWN'
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(event)

    embeds = []
    current_embed = discord.Embed(
        title=f"📊 {base_title}",
        color=embed_color,
        timestamp=datetime.now()
    )
    current_embed_size = 100  # Base size for title/timestamp
    field_count = 0

    for phase in PHASE_ORDER:
        if phase not in phases:
            continue

        phase_events = phases[phase]
        lines = []

        # Format ALL events (no limit)
        for event in phase_events:
            event_type = event.event_type or 'UNKNOWN'
            event_data = event.event_data or {}

            if event_type in EVENT_HANDLERS:
                handler = EVENT_HANDLERS[event_type]
                line = handler.get_character_line(event_data, character_id)
                if line:
                    lines.append(line)

        if not lines:
            continue

        # Split into chunks if needed
        chunks = split_lines_into_chunks(lines, 1000)
        phase_name = phase.replace('_', ' ').title()

        for i, chunk in enumerate(chunks):
            field_name = f"📌 {phase_name} Phase"
            if i > 0:
                field_name += f" (cont. {i+1})"

            field_size = len(field_name) + len(chunk) + 10

            # Check if we need a new embed
            if current_embed_size + field_size > 5500 or field_count >= 24:
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title=f"📊 {base_title} (continued)",
                    color=embed_color
                )
                current_embed_size = 100
                field_count = 0

            current_embed.add_field(name=field_name, value=chunk, inline=False)
            current_embed_size += field_size
            field_count += 1

    # Add the last embed if it has content or is the only one
    if field_count > 0 or not embeds:
        embeds.append(current_embed)

    return embeds


def create_gm_turn_report_embeds(
    turn_number: int,
    events: List[Dict],
    summary: Dict
) -> List[discord.Embed]:
    """
    Create embeds with the GM's comprehensive turn report.

    Args:
        turn_number: Turn number
        events: All events from the turn
        summary: Summary statistics dict

    Returns:
        List of Discord embeds (multiple if content exceeds limits)
    """
    embed_color = discord.Color.purple()
    base_title = f"GM Turn {turn_number} Report"

    embeds = []
    current_embed = discord.Embed(
        title=f"👑 {base_title}",
        description="Complete turn resolution summary",
        color=embed_color,
        timestamp=datetime.now()
    )
    current_embed_size = 150  # Base size for title/description/timestamp
    field_count = 0

    # Executive summary
    summary_lines = []
    if summary.get('total_events', 0) > 0:
        summary_lines.append(f"📊 Total Events: {summary['total_events']}")

    for phase in PHASE_ORDER:
        count = summary.get(f'{phase.lower()}_events', 0)
        if count > 0:
            phase_name = phase.replace('_', ' ').title()
            summary_lines.append(f"• {phase_name}: {count}")

    if summary_lines:
        summary_value = "\n".join(summary_lines)
        current_embed.add_field(
            name="📈 Executive Summary",
            value=summary_value,
            inline=False
        )
        current_embed_size += len("📈 Executive Summary") + len(summary_value) + 10
        field_count += 1

    # Group events by phase
    phases = {}
    for event in events:
        phase = event.phase or 'UNKNOWN'
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(event)

    # Display each phase
    for phase in PHASE_ORDER:
        if phase not in phases:
            continue

        phase_events = phases[phase]
        lines = []

        # Format ALL events (no limit)
        for event in phase_events:
            event_type = event.event_type or 'UNKNOWN'
            event_data = event.event_data or {}

            if event_type in EVENT_HANDLERS:
                handler = EVENT_HANDLERS[event_type]
                line = handler.get_gm_line(event_data)
                if line:
                    lines.append(line)

        if not lines:
            continue

        # Split into chunks if needed
        chunks = split_lines_into_chunks(lines, 1000)
        phase_name = phase.replace('_', ' ').title()
        event_count = len(phase_events)

        for i, chunk in enumerate(chunks):
            field_name = f"📌 {phase_name} ({event_count} events)"
            if i > 0:
                field_name = f"📌 {phase_name} (cont. {i+1})"

            field_size = len(field_name) + len(chunk) + 10

            # Check if we need a new embed
            if current_embed_size + field_size > 5500 or field_count >= 24:
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title=f"👑 {base_title} (continued)",
                    color=embed_color
                )
                current_embed_size = 100
                field_count = 0

            current_embed.add_field(name=field_name, value=chunk, inline=False)
            current_embed_size += field_size
            field_count += 1

    # Add footer to the last embed
    current_embed.set_footer(text=f"Turn {turn_number} completed at")

    # Add the last embed if it has content or is the only one
    if field_count > 0 or not embeds:
        embeds.append(current_embed)

    return embeds
