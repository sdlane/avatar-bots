"""
Helper functions for creating Discord embeds for turn resolution reports.
"""
import discord
from typing import List, Dict, Optional
from datetime import datetime
from order_types import PHASE_ORDER


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
            elif order_type == 'TRANSIT':
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


def create_character_turn_report_embed(
    character_name: str,
    turn_number: int,
    events: List[Dict]
) -> discord.Embed:
    """
    Create an embed with a character's turn report.

    Args:
        character_name: Name of the character
        turn_number: Turn number
        events: List of event dicts relevant to this character

    Returns:
        Discord embed
    """
    embed = discord.Embed(
        title=f"📊 Turn {turn_number} Report: {character_name}",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )

    if not events:
        embed.description = "No events this turn."
        return embed

    # Group events by phase
    phases = {}
    for event in events:
        phase = event.get('phase', 'UNKNOWN')
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(event)

    # Display each phase
    for phase in PHASE_ORDER:
        if phase not in phases:
            continue

        phase_events = phases[phase]
        lines = []

        for event in phase_events:
            event_type = event.get('event_type', 'UNKNOWN')
            event_data = event.get('event_data', {})

            if event_type == 'JOIN_FACTION':
                faction_name = event_data.get('faction_name', 'Unknown')
                lines.append(f"✅ Joined faction: **{faction_name}**")

            elif event_type == 'JOIN_FACTION_COMPLETED':
                char_name = event_data.get('character_name', 'Unknown')
                faction_name = event_data.get('faction_name', 'Unknown')
                lines.append(f"✅ **{char_name}** joined faction: **{faction_name}**")

            elif event_type == 'JOIN_FACTION_PENDING':
                faction_name = event_data.get('faction_name', 'Unknown')
                waiting_for = event_data.get('waiting_for', 'approval')
                lines.append(f"⏳ Join request for **{faction_name}** submitted (waiting for {waiting_for})")

            elif event_type == 'LEAVE_FACTION':
                char_name = event_data.get('character_name', 'Unknown')
                faction_name = event_data.get('faction_name', 'Unknown')
                lines.append(f"❌ **{char_name}** left faction: **{faction_name}**")

            elif event_type == 'KICK_FROM_FACTION':
                char_name = event_data.get('character_name', 'Unknown')
                faction_name = event_data.get('faction_name', 'Unknown')
                lines.append(f"🚫 **{char_name}** was removed from faction: **{faction_name}**")

            elif event_type == 'ORDER_FAILED':
                order_type = event_data.get('order_type', 'Unknown')
                error = event_data.get('error', 'Unknown error')
                lines.append(f"❌ Order failed: **{order_type}** - {error}")

            elif event_type == 'TRANSIT_COMPLETE':
                units = event_data.get('units', [])
                final_territory = event_data.get('final_territory', 'Unknown')
                lines.append(f"🎯 Units arrived: {', '.join(units)} → Territory {final_territory}")

            elif event_type == 'TRANSIT_PROGRESS':
                units = event_data.get('units', [])
                current_territory = event_data.get('current_territory', 'Unknown')
                path_index = event_data.get('path_index', 0)
                total_steps = event_data.get('total_steps', 0)
                lines.append(f"🚶 Units moving: {', '.join(units)} → Territory {current_territory} ({path_index}/{total_steps})")

            elif event_type == 'RESOURCE_COLLECTION':
                resources = event_data.get('resources', {})
                territory_name = event_data.get('territory_name', 'Unknown')
                resource_strs = []
                if resources.get('ore', 0) > 0:
                    resource_strs.append(f"⛏️{resources['ore']}")
                if resources.get('lumber', 0) > 0:
                    resource_strs.append(f"🪵{resources['lumber']}")
                if resources.get('coal', 0) > 0:
                    resource_strs.append(f"⚫{resources['coal']}")
                if resources.get('rations', 0) > 0:
                    resource_strs.append(f"🍖{resources['rations']}")
                if resources.get('cloth', 0) > 0:
                    resource_strs.append(f"🧵{resources['cloth']}")
                if resource_strs:
                    lines.append(f"💰 Collected from {territory_name}: {' '.join(resource_strs)}")

            elif event_type == 'UPKEEP_PAID':
                unit_id = event_data.get('unit_id', 'Unknown')
                lines.append(f"✅ Upkeep paid for {unit_id}")

            elif event_type == 'UPKEEP_DEFICIT':
                unit_id = event_data.get('unit_id', 'Unknown')
                penalty = event_data.get('organization_penalty', 0)
                new_org = event_data.get('new_organization', 0)
                deficit = event_data.get('resources_deficit', {})
                deficit_strs = [f"{k}:{v}" for k, v in deficit.items() if v > 0]
                lines.append(f"⚠️ {unit_id}: Insufficient upkeep (missing {', '.join(deficit_strs)}) - Organization -{penalty} → {new_org}")

            elif event_type == 'UNIT_DISSOLVED':
                unit_id = event_data.get('unit_id', 'Unknown')
                lines.append(f"💀 **{unit_id} dissolved** (organization depleted)")

        if lines:
            phase_name = phase.replace('_', ' ').title()
            embed.add_field(
                name=f"📌 {phase_name} Phase",
                value="\n".join(lines),
                inline=False
            )

    return embed


def create_gm_turn_report_embed(
    turn_number: int,
    events: List[Dict],
    summary: Dict
) -> discord.Embed:
    """
    Create an embed with the GM's comprehensive turn report.

    Args:
        turn_number: Turn number
        events: All events from the turn
        summary: Summary statistics dict

    Returns:
        Discord embed
    """
    embed = discord.Embed(
        title=f"👑 GM Turn {turn_number} Report",
        description="Complete turn resolution summary",
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )

    # Executive summary
    summary_lines = []
    if summary.get('total_events', 0) > 0:
        summary_lines.append(f"📊 Total Events: {summary['total_events']}")

    for phase in ['BEGINNING', 'MOVEMENT', 'RESOURCE_COLLECTION', 'UPKEEP']:
        count = summary.get(f'{phase.lower()}_events', 0)
        if count > 0:
            phase_name = phase.replace('_', ' ').title()
            summary_lines.append(f"• {phase_name}: {count}")

    if summary_lines:
        embed.add_field(
            name="📈 Executive Summary",
            value="\n".join(summary_lines),
            inline=False
        )

    # Group events by phase
    phases = {}
    for event in events:
        phase = event.get('phase', 'UNKNOWN')
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(event)

    # Display each phase (limited to avoid embed size limits)
    phase_order = ['BEGINNING', 'MOVEMENT', 'RESOURCE_COLLECTION', 'RESOURCE_TRANSFER', 'UPKEEP']

    for phase in phase_order:
        if phase not in phases:
            continue

        phase_events = phases[phase]
        lines = []

        # Limit to first 10 events per phase to avoid embed limits
        for event in phase_events[:10]:
            event_type = event.get('event_type', 'UNKNOWN')
            event_data = event.get('event_data', {})

            if event_type == 'JOIN_FACTION':
                char = event_data.get('character_name', 'Unknown')
                faction = event_data.get('faction_name', 'Unknown')
                lines.append(f"✅ {char} → {faction}")

            elif event_type == 'JOIN_FACTION_COMPLETED':
                char = event_data.get('character_name', 'Unknown')
                faction = event_data.get('faction_name', 'Unknown')
                lines.append(f"✅ {char} → {faction}")

            elif event_type == 'JOIN_FACTION_PENDING':
                char = event_data.get('character_name', 'Unknown')
                faction = event_data.get('faction_name', 'Unknown')
                waiting_for = event_data.get('waiting_for', '?')
                lines.append(f"⏳ {char} → {faction} (pending: {waiting_for})")

            elif event_type == 'LEAVE_FACTION':
                char = event_data.get('character_name', 'Unknown')
                faction = event_data.get('faction_name', 'Unknown')
                lines.append(f"❌ {char} ← {faction}")

            elif event_type == 'KICK_FROM_FACTION':
                char = event_data.get('character_name', 'Unknown')
                faction = event_data.get('faction_name', 'Unknown')
                lines.append(f"🚫 {char} ← {faction} (kicked)")

            elif event_type == 'ORDER_FAILED':
                order_type = event_data.get('order_type', 'Unknown')
                error = event_data.get('error', 'Unknown')
                lines.append(f"❌ {order_type}: {error}")

            elif event_type == 'TRANSIT_COMPLETE':
                units = event_data.get('units', [])
                final_territory = event_data.get('final_territory', 'Unknown')
                lines.append(f"🎯 {', '.join(units)} → T{final_territory}")

            elif event_type == 'TRANSIT_PROGRESS':
                units = event_data.get('units', [])
                current_territory = event_data.get('current_territory', 'Unknown')
                lines.append(f"🚶 {', '.join(units)} → T{current_territory}")

            elif event_type == 'RESOURCE_COLLECTION':
                leader = event_data.get('leader_name', 'Unknown')
                territory = event_data.get('territory_id', 'Unknown')
                lines.append(f"💰 T{territory} → {leader}")

            elif event_type == 'UPKEEP_DEFICIT':
                unit_id = event_data.get('unit_id', 'Unknown')
                penalty = event_data.get('organization_penalty', 0)
                lines.append(f"⚠️ {unit_id} org -{penalty}")

            elif event_type == 'UNIT_DISSOLVED':
                unit_id = event_data.get('unit_id', 'Unknown')
                lines.append(f"💀 {unit_id} dissolved")

        if len(phase_events) > 10:
            lines.append(f"... and {len(phase_events) - 10} more events")

        if lines:
            phase_name = phase.replace('_', ' ').title()
            embed.add_field(
                name=f"📌 {phase_name} ({len(phase_events)} events)",
                value="\n".join(lines),
                inline=False
            )

    # Add footer
    embed.set_footer(text=f"Turn {turn_number} completed at")

    return embed
