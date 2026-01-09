"""
Handler functions for Iroh wargame bot commands.
These functions contain the business logic separated from Discord interactions.
"""

from .view_handlers import (
    view_territory,
    view_faction,
    view_unit,
    view_unit_type,
    view_resources,
    view_faction_membership,
    view_units_for_character,
    view_territories_for_character,
    view_victory_points,
    view_faction_victory_points,
)

from .faction_handlers import (
    create_faction,
    delete_faction,
    set_faction_leader,
    add_faction_member,
    remove_faction_member,
)

from .territory_handlers import (
    create_territory,
    edit_territory,
    delete_territory,
    set_territory_controller,
    add_adjacency,
    remove_adjacency,
)

from .unit_type_handlers import (
    create_unit_type,
    edit_unit_type,
    delete_unit_type,
)

from .unit_handlers import (
    create_unit,
    delete_unit,
    set_unit_commander,
)

from .resource_handlers import (
    modify_resources,
    modify_character_production,
    modify_character_vp,
)

from .list_handlers import (
    list_factions,
    list_territories,
    list_unit_types,
    list_units,
)

from .order_handlers import (
    submit_join_faction_order,
    submit_leave_faction_order,
    submit_kick_from_faction_order,
    submit_transit_order,
    submit_resource_transfer_order,
    submit_cancel_transfer_order,
    submit_assign_commander_order,
    submit_assign_victory_points_order,
    cancel_order,
    view_pending_orders,
    validate_path,
)

from .turn_handlers import *

from .config_handlers import (
    fetch_wargame_config,
)

from .report_handlers import (
    generate_character_report,
    generate_gm_report,
)

__all__ = [
    # View handlers
    'view_territory',
    'view_faction',
    'view_unit',
    'view_unit_type',
    'view_resources',
    'view_faction_membership',
    'view_units_for_character',
    'view_territories_for_character',
    'view_victory_points',
    'view_faction_victory_points',
    # Faction handlers
    'create_faction',
    'delete_faction',
    'set_faction_leader',
    'add_faction_member',
    'remove_faction_member',
    # Territory handlers
    'create_territory',
    'edit_territory',
    'delete_territory',
    'set_territory_controller',
    'add_adjacency',
    'remove_adjacency',
    # Unit type handlers
    'create_unit_type',
    'edit_unit_type',
    'delete_unit_type',
    # Unit handlers
    'create_unit',
    'delete_unit',
    'set_unit_commander',
    # Resource handlers
    'modify_resources',
    'modify_character_production',
    'modify_character_vp',
    # List handlers
    'list_factions',
    'list_territories',
    'list_unit_types',
    'list_units',
    # Order handlers
    'submit_join_faction_order',
    'submit_leave_faction_order',
    'submit_kick_from_faction_order',
    'submit_transit_order',
    'submit_resource_transfer_order',
    'submit_cancel_transfer_order',
    'submit_assign_commander_order',
    'submit_assign_victory_points_order',
    'cancel_order',
    'view_pending_orders',
    'validate_path',
    # Turn handlers
    'resolve_turn',
    'execute_beginning_phase',
    'execute_movement_phase',
    'execute_combat_phase',
    'execute_resource_collection_phase',
    'execute_resource_transfer_phase',
    'execute_encirclement_phase',
    'execute_upkeep_phase',
    'execute_organization_phase',
    'execute_construction_phase',
    'get_turn_status',
    # Config handlers
    'fetch_wargame_config',
    # Report handlers
    'generate_character_report',
    'generate_gm_report',
]
