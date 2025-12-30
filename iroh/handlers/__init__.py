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
)

from .list_handlers import (
    list_factions,
    list_territories,
    list_unit_types,
    list_units,
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
    # List handlers
    'list_factions',
    'list_territories',
    'list_unit_types',
    'list_units',
]
