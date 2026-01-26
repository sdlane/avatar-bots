import yaml
from typing import Dict, Any, List, Optional
import asyncpg
import logging
from db import (
    Territory, Faction, FactionMember, Unit, UnitType, BuildingType, Building,
    PlayerResources, TerritoryAdjacency, WargameConfig, Character,
    FactionResources, FactionPermission, VALID_PERMISSION_TYPES, SpiritNexus
)

logger = logging.getLogger(__name__)


class ConfigManager:
    """Handles import/export of wargame configuration via YAML"""

    @staticmethod
    async def export_config(conn: asyncpg.Connection, guild_id: int) -> str:
        """
        Export current wargame state to YAML string.

        Args:
            conn: Database connection
            guild_id: Guild ID to export

        Returns:
            YAML string representing the complete wargame state
        """
        config_dict = {}

        # Export WargameConfig
        wargame_config = await WargameConfig.fetch(conn, guild_id)
        if wargame_config:
            config_dict['wargame'] = {
                'turn': wargame_config.current_turn,
                'max_movement_stat': wargame_config.max_movement_stat,
                'turn_resolution_enabled': wargame_config.turn_resolution_enabled
            }
        else:
            config_dict['wargame'] = {
                'turn': 0,
                'max_movement_stat': 4,
                'turn_resolution_enabled': False
            }

        # Export Factions
        factions = await Faction.fetch_all(conn, guild_id)
        config_dict['factions'] = []
        for faction in factions:
            faction_dict = {
                'faction_id': faction.faction_id,
                'name': faction.name
            }

            # Include nation if set
            if faction.nation:
                faction_dict['nation'] = faction.nation

            # Get leader character identifier
            if faction.leader_character_id:
                leader = await Character.fetch_by_id(conn, faction.leader_character_id)
                if leader:
                    faction_dict['leader'] = leader.identifier

            # Get faction members
            members = await FactionMember.fetch_by_faction(conn, faction.id, guild_id)
            if members:
                member_identifiers = []
                for member in members:
                    char = await Character.fetch_by_id(conn, member.character_id)
                    if char:
                        member_identifiers.append(char.identifier)
                faction_dict['members'] = member_identifiers

            # Include spending if any values are non-zero
            if (faction.ore_spending or faction.lumber_spending or faction.coal_spending or
                faction.rations_spending or faction.cloth_spending or faction.platinum_spending):
                faction_dict['spending'] = {
                    'ore': faction.ore_spending,
                    'lumber': faction.lumber_spending,
                    'coal': faction.coal_spending,
                    'rations': faction.rations_spending,
                    'cloth': faction.cloth_spending,
                    'platinum': faction.platinum_spending
                }

            config_dict['factions'].append(faction_dict)

        # Export Player Resources
        # Get all characters first, then fetch their resources
        characters = await Character.fetch_all(conn, guild_id)
        config_dict['player_resources'] = []
        for character in characters:
            resources = await PlayerResources.fetch_by_character(conn, character.id, guild_id)
            if resources and (resources.ore or resources.lumber or resources.coal or
                            resources.rations or resources.cloth or resources.platinum):
                config_dict['player_resources'].append({
                    'character': character.identifier,
                    'resources': {
                        'ore': resources.ore,
                        'lumber': resources.lumber,
                        'coal': resources.coal,
                        'rations': resources.rations,
                        'cloth': resources.cloth,
                        'platinum': resources.platinum
                    }
                })

        # Export Character production and VP
        config_dict['characters'] = []
        for character in characters:
            has_production = (character.ore_production or character.lumber_production or
                            character.coal_production or character.rations_production or
                            character.cloth_production or character.platinum_production)
            if has_production or character.victory_points:
                char_dict = {'character': character.identifier}
                if has_production:
                    char_dict['production'] = {
                        'ore': character.ore_production,
                        'lumber': character.lumber_production,
                        'coal': character.coal_production,
                        'rations': character.rations_production,
                        'cloth': character.cloth_production,
                        'platinum': character.platinum_production
                    }
                if character.victory_points:
                    char_dict['victory_points'] = character.victory_points
                config_dict['characters'].append(char_dict)

        # Export Territories
        territories = await Territory.fetch_all(conn, guild_id)
        config_dict['territories'] = []
        for territory in territories:
            territory_dict = {
                'territory_id': territory.territory_id,
                'terrain_type': territory.terrain_type
            }

            if territory.name:
                territory_dict['name'] = territory.name

            if territory.original_nation:
                territory_dict['original_nation'] = territory.original_nation

            # Get controller - character or faction
            if territory.controller_character_id:
                controller = await Character.fetch_by_id(conn, territory.controller_character_id)
                if controller:
                    territory_dict['controller_character_identifier'] = controller.identifier
            elif territory.controller_faction_id:
                faction = await Faction.fetch_by_id(conn, territory.controller_faction_id)
                if faction:
                    territory_dict['controller_faction_id'] = faction.faction_id

            # Production
            territory_dict['production'] = {
                'ore': territory.ore_production,
                'lumber': territory.lumber_production,
                'coal': territory.coal_production,
                'rations': territory.rations_production,
                'cloth': territory.cloth_production,
                'platinum': territory.platinum_production
            }

            # Victory points
            if territory.victory_points > 0:
                territory_dict['victory_points'] = territory.victory_points

            # Siege defense
            if territory.siege_defense > 0:
                territory_dict['siege_defense'] = territory.siege_defense

            # Keywords
            if territory.keywords:
                territory_dict['keywords'] = territory.keywords

            # Adjacent territories
            adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory.territory_id, guild_id)
            if adjacent_ids:
                territory_dict['adjacent_to'] = sorted(adjacent_ids)

            config_dict['territories'].append(territory_dict)

        # Export Unit Types
        unit_types = await UnitType.fetch_all(conn, guild_id)
        config_dict['unit_types'] = []
        for unit_type in unit_types:
            unit_type_dict = {
                'type_id': unit_type.type_id,
                'name': unit_type.name
            }

            if unit_type.nation:
                unit_type_dict['nation'] = unit_type.nation

            unit_type_dict['stats'] = {
                'movement': unit_type.movement,
                'organization': unit_type.organization,
                'attack': unit_type.attack,
                'defense': unit_type.defense,
                'siege_attack': unit_type.siege_attack,
                'siege_defense': unit_type.siege_defense
            }

            if unit_type.size != 1:
                unit_type_dict['stats']['size'] = unit_type.size
            if unit_type.capacity != 0:
                unit_type_dict['stats']['capacity'] = unit_type.capacity
            if unit_type.is_naval:
                unit_type_dict['stats']['is_naval'] = unit_type.is_naval
            if unit_type.keywords:
                unit_type_dict['stats']['keywords'] = unit_type.keywords

            unit_type_dict['cost'] = {
                'ore': unit_type.cost_ore,
                'lumber': unit_type.cost_lumber,
                'coal': unit_type.cost_coal,
                'rations': unit_type.cost_rations,
                'cloth': unit_type.cost_cloth,
                'platinum': unit_type.cost_platinum
            }

            unit_type_dict['upkeep'] = {
                'ore': unit_type.upkeep_ore,
                'lumber': unit_type.upkeep_lumber,
                'coal': unit_type.upkeep_coal,
                'rations': unit_type.upkeep_rations,
                'cloth': unit_type.upkeep_cloth,
                'platinum': unit_type.upkeep_platinum
            }

            config_dict['unit_types'].append(unit_type_dict)

        # Export Building Types
        building_types = await BuildingType.fetch_all(conn, guild_id)
        config_dict['building_types'] = []
        for building_type in building_types:
            building_type_dict = {
                'type_id': building_type.type_id,
                'name': building_type.name
            }

            if building_type.description:
                building_type_dict['description'] = building_type.description

            building_type_dict['cost'] = {
                'ore': building_type.cost_ore,
                'lumber': building_type.cost_lumber,
                'coal': building_type.cost_coal,
                'rations': building_type.cost_rations,
                'cloth': building_type.cost_cloth,
                'platinum': building_type.cost_platinum
            }

            building_type_dict['upkeep'] = {
                'ore': building_type.upkeep_ore,
                'lumber': building_type.upkeep_lumber,
                'coal': building_type.upkeep_coal,
                'rations': building_type.upkeep_rations,
                'cloth': building_type.upkeep_cloth,
                'platinum': building_type.upkeep_platinum
            }

            # Keywords
            if building_type.keywords:
                building_type_dict['keywords'] = building_type.keywords

            config_dict['building_types'].append(building_type_dict)

        # Export Buildings
        buildings = await Building.fetch_all(conn, guild_id)
        config_dict['buildings'] = []
        for building in buildings:
            building_dict = {
                'building_id': building.building_id,
                'type': building.building_type
            }

            if building.name:
                building_dict['name'] = building.name

            if building.territory_id:
                building_dict['territory_id'] = building.territory_id

            if building.durability != 10:
                building_dict['durability'] = building.durability

            if building.status != 'ACTIVE':
                building_dict['status'] = building.status

            # Keywords (only if different from building type defaults)
            if building.keywords:
                building_dict['keywords'] = building.keywords

            config_dict['buildings'].append(building_dict)

        # Export Units
        units = await Unit.fetch_all(conn, guild_id)
        config_dict['units'] = []
        for unit in units:
            unit_dict = {
                'unit_id': unit.unit_id,
                'type': unit.unit_type
            }

            if unit.name:
                unit_dict['name'] = unit.name

            # Get owner - either character or faction
            if unit.owner_character_id:
                owner = await Character.fetch_by_id(conn, unit.owner_character_id)
                if owner:
                    unit_dict['owner'] = owner.identifier
            elif unit.owner_faction_id:
                owner_faction = await Faction.fetch_by_id(conn, unit.owner_faction_id)
                if owner_faction:
                    unit_dict['owner_faction'] = owner_faction.faction_id

            if unit.commander_character_id:
                commander = await Character.fetch_by_id(conn, unit.commander_character_id)
                if commander:
                    unit_dict['commander'] = commander.identifier

            # Get faction_id
            if unit.faction_id:
                faction = await Faction.fetch_by_id(conn, unit.faction_id)
                if faction:
                    unit_dict['faction_id'] = faction.faction_id

            if unit.current_territory_id is not None:
                unit_dict['current_territory_id'] = unit.current_territory_id

            # Only include non-default stats
            if unit.organization != unit.max_organization:
                unit_dict['current_organization'] = unit.organization

            config_dict['units'].append(unit_dict)

        # Export Faction Resources
        config_dict['faction_resources'] = []
        for faction in factions:
            resources = await FactionResources.fetch_by_faction(conn, faction.id, guild_id)
            if resources and (resources.ore or resources.lumber or resources.coal or
                            resources.rations or resources.cloth or resources.platinum):
                config_dict['faction_resources'].append({
                    'faction_id': faction.faction_id,
                    'resources': {
                        'ore': resources.ore,
                        'lumber': resources.lumber,
                        'coal': resources.coal,
                        'rations': resources.rations,
                        'cloth': resources.cloth,
                        'platinum': resources.platinum
                    }
                })

        # Export Faction Permissions
        config_dict['faction_permissions'] = []
        for faction in factions:
            permissions = await FactionPermission.fetch_by_faction(conn, faction.id, guild_id)
            for perm in permissions:
                char = await Character.fetch_by_id(conn, perm.character_id)
                if char:
                    config_dict['faction_permissions'].append({
                        'faction_id': faction.faction_id,
                        'character': char.identifier,
                        'permission_type': perm.permission_type
                    })

        # Export Spirit Nexuses
        spirit_nexuses = await SpiritNexus.fetch_all(conn, guild_id)
        config_dict['spirit_nexuses'] = []
        for nexus in spirit_nexuses:
            config_dict['spirit_nexuses'].append({
                'identifier': nexus.identifier,
                'territory_id': nexus.territory_id,
                'health': nexus.health
            })

        return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

    @staticmethod
    async def import_config(conn: asyncpg.Connection, guild_id: int, config_yaml: str) -> tuple[bool, str]:
        """
        Import YAML string and populate database.

        Args:
            conn: Database connection
            guild_id: Guild ID to import into
            config_yaml: YAML string to import

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            config_dict = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return False, f"Invalid YAML format: {e}"

        # Validate that all referenced characters exist
        character_identifiers_needed = set()

        # Collect all character identifiers from config
        if 'factions' in config_dict:
            for faction in config_dict['factions']:
                if 'leader' in faction:
                    character_identifiers_needed.add(faction['leader'])
                if 'members' in faction:
                    character_identifiers_needed.update(faction['members'])

        if 'player_resources' in config_dict:
            for player_res in config_dict['player_resources']:
                character_identifiers_needed.add(player_res['character'])

        if 'units' in config_dict:
            for unit in config_dict['units']:
                if 'owner' in unit:
                    character_identifiers_needed.add(unit['owner'])
                if 'commander' in unit:
                    character_identifiers_needed.add(unit['commander'])

        if 'territories' in config_dict:
            for territory in config_dict['territories']:
                if 'controller_character_identifier' in territory:
                    character_identifiers_needed.add(territory['controller_character_identifier'])

        if 'characters' in config_dict:
            for char_data in config_dict['characters']:
                character_identifiers_needed.add(char_data['character'])

        if 'faction_permissions' in config_dict:
            for perm in config_dict['faction_permissions']:
                character_identifiers_needed.add(perm['character'])

        # Validate characters exist
        missing_characters = []
        character_map = {}  # identifier -> Character object
        for identifier in character_identifiers_needed:
            char = await Character.fetch_by_identifier(conn, identifier, guild_id)
            if not char:
                missing_characters.append(identifier)
            else:
                character_map[identifier] = char

        if missing_characters:
            return False, f"Missing characters (create with hawky first): {', '.join(sorted(missing_characters))}"

        # Import WargameConfig
        if 'wargame' in config_dict:
            wargame = config_dict['wargame']
            wg_config = WargameConfig(
                guild_id=guild_id,
                current_turn=wargame.get('turn', 0),
                max_movement_stat=wargame.get('max_movement_stat', 4),
                turn_resolution_enabled=wargame.get('turn_resolution_enabled', False)
            )
            await wg_config.upsert(conn)

        # Import Factions (first pass - without leaders)
        faction_map = {}  # faction_id -> internal id
        if 'factions' in config_dict:
            for faction_data in config_dict['factions']:
                spending = faction_data.get('spending', {})
                faction = Faction(
                    faction_id=faction_data['faction_id'],
                    name=faction_data['name'],
                    nation=faction_data.get('nation'),
                    ore_spending=spending.get('ore', 0),
                    lumber_spending=spending.get('lumber', 0),
                    coal_spending=spending.get('coal', 0),
                    rations_spending=spending.get('rations', 0),
                    cloth_spending=spending.get('cloth', 0),
                    platinum_spending=spending.get('platinum', 0),
                    guild_id=guild_id
                )
                await faction.upsert(conn)

                # Fetch back to get internal ID
                faction_obj = await Faction.fetch_by_faction_id(conn, faction_data['faction_id'], guild_id)
                if faction_obj:
                    faction_map[faction_data['faction_id']] = faction_obj.id

        # Import Factions (second pass - set leaders)
        if 'factions' in config_dict:
            for faction_data in config_dict['factions']:
                if 'leader' in faction_data:
                    leader_char = character_map.get(faction_data['leader'])
                    if leader_char:
                        faction = await Faction.fetch_by_faction_id(conn, faction_data['faction_id'], guild_id)
                        if faction:
                            faction.leader_character_id = leader_char.id
                            await faction.upsert(conn)

        # Import Faction Members
        if 'factions' in config_dict:
            for faction_data in config_dict['factions']:
                faction_internal_id = faction_map.get(faction_data['faction_id'])
                if faction_internal_id and 'members' in faction_data:
                    wg_config = await WargameConfig.fetch(conn, guild_id)
                    current_turn = wg_config.current_turn if wg_config else 0

                    for member_identifier in faction_data['members']:
                        member_char = character_map.get(member_identifier)
                        if member_char:
                            faction_member = FactionMember(
                                faction_id=faction_internal_id,
                                character_id=member_char.id,
                                joined_turn=current_turn,
                                guild_id=guild_id
                            )
                            await faction_member.upsert(conn)

        # Collect all referenced faction IDs and validate they exist
        referenced_faction_ids = set()
        if 'territories' in config_dict:
            for territory in config_dict['territories']:
                if 'controller_faction_id' in territory:
                    referenced_faction_ids.add(territory['controller_faction_id'])
                elif 'controller' in territory:
                    referenced_faction_ids.add(territory['controller'])

        if 'units' in config_dict:
            for unit in config_dict['units']:
                if 'owner_faction' in unit:
                    referenced_faction_ids.add(unit['owner_faction'])
                if 'faction_id' in unit:
                    referenced_faction_ids.add(unit['faction_id'])

        if 'faction_resources' in config_dict:
            for fr in config_dict['faction_resources']:
                referenced_faction_ids.add(fr['faction_id'])

        if 'faction_permissions' in config_dict:
            for perm in config_dict['faction_permissions']:
                referenced_faction_ids.add(perm['faction_id'])

        # Validate all referenced faction IDs exist (either created in this import or pre-existing)
        missing_factions = []
        for faction_id in referenced_faction_ids:
            if faction_id not in faction_map:
                # Try to find in database
                faction_obj = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
                if faction_obj:
                    faction_map[faction_id] = faction_obj.id
                else:
                    missing_factions.append(faction_id)

        if missing_factions:
            return False, f"Missing factions: {', '.join(sorted(missing_factions))}"

        # Import Player Resources
        if 'player_resources' in config_dict:
            for player_res_data in config_dict['player_resources']:
                char = character_map.get(player_res_data['character'])
                if char:
                    resources = player_res_data.get('resources', {})
                    player_res = PlayerResources(
                        character_id=char.id,
                        ore=resources.get('ore', 0),
                        lumber=resources.get('lumber', 0),
                        coal=resources.get('coal', 0),
                        rations=resources.get('rations', 0),
                        cloth=resources.get('cloth', 0),
                        platinum=resources.get('platinum', 0),
                        guild_id=guild_id
                    )
                    await player_res.upsert(conn)

        # Import Faction Resources
        if 'faction_resources' in config_dict:
            for faction_res_data in config_dict['faction_resources']:
                faction_internal_id = faction_map.get(faction_res_data['faction_id'])
                if faction_internal_id:
                    resources = faction_res_data.get('resources', {})
                    faction_res = FactionResources(
                        faction_id=faction_internal_id,
                        ore=resources.get('ore', 0),
                        lumber=resources.get('lumber', 0),
                        coal=resources.get('coal', 0),
                        rations=resources.get('rations', 0),
                        cloth=resources.get('cloth', 0),
                        platinum=resources.get('platinum', 0),
                        guild_id=guild_id
                    )
                    await faction_res.upsert(conn)

        # Import Faction Permissions
        if 'faction_permissions' in config_dict:
            for perm_data in config_dict['faction_permissions']:
                faction_internal_id = faction_map.get(perm_data['faction_id'])
                char = character_map.get(perm_data['character'])
                permission_type = perm_data.get('permission_type', '')

                if faction_internal_id and char and permission_type in VALID_PERMISSION_TYPES:
                    # Validate character is a member of the faction
                    member = await FactionMember.fetch_by_character(conn, char.id, guild_id)
                    if member and member.faction_id == faction_internal_id:
                        perm = FactionPermission(
                            faction_id=faction_internal_id,
                            character_id=char.id,
                            permission_type=permission_type,
                            guild_id=guild_id
                        )
                        await perm.upsert(conn)
                    else:
                        logger.warning(f"Skipping permission for {perm_data['character']} - not a member of faction {perm_data['faction_id']}")

        # Import Character production and VP
        if 'characters' in config_dict:
            for char_data in config_dict['characters']:
                char = character_map.get(char_data['character'])
                if char:
                    production = char_data.get('production', {})
                    char.ore_production = production.get('ore', 0)
                    char.lumber_production = production.get('lumber', 0)
                    char.coal_production = production.get('coal', 0)
                    char.rations_production = production.get('rations', 0)
                    char.cloth_production = production.get('cloth', 0)
                    char.platinum_production = production.get('platinum', 0)
                    char.victory_points = char_data.get('victory_points', 0)
                    await char.upsert(conn)

        # Import Territories
        if 'territories' in config_dict:
            for territory_data in config_dict['territories']:
                controller_character_id = None
                controller_faction_id = None

                if 'controller_character_identifier' in territory_data:
                    character = character_map.get(territory_data['controller_character_identifier'])
                    if character:
                        controller_character_id = character.id
                elif 'controller_faction_id' in territory_data:
                    controller_faction_id = faction_map.get(territory_data['controller_faction_id'])
                elif 'controller' in territory_data:
                    # Support 'controller' as alias for 'controller_faction_id'
                    controller_faction_id = faction_map.get(territory_data['controller'])

                production = territory_data.get('production', {})
                territory = Territory(
                    territory_id=str(territory_data['territory_id']),
                    name=territory_data.get('name'),
                    terrain_type=territory_data['terrain_type'],
                    ore_production=production.get('ore', 0),
                    lumber_production=production.get('lumber', 0),
                    coal_production=production.get('coal', 0),
                    rations_production=production.get('rations', 0),
                    cloth_production=production.get('cloth', 0),
                    platinum_production=production.get('platinum', 0),
                    victory_points=territory_data.get('victory_points', 0),
                    siege_defense=territory_data.get('siege_defense', 0),
                    controller_character_id=controller_character_id,
                    controller_faction_id=controller_faction_id,
                    original_nation=territory_data.get('original_nation'),
                    keywords=territory_data.get('keywords', []),
                    guild_id=guild_id
                )
                await territory.upsert(conn)

                # Import adjacencies
                if 'adjacent_to' in territory_data:
                    for adjacent_id in territory_data['adjacent_to']:
                        adjacency = TerritoryAdjacency(
                            territory_a_id=str(territory_data['territory_id']),
                            territory_b_id=str(adjacent_id),
                            guild_id=guild_id
                        )
                        await adjacency.insert(conn)

        # Import Spirit Nexuses
        if 'spirit_nexuses' in config_dict:
            for nexus_data in config_dict['spirit_nexuses']:
                nexus = SpiritNexus(
                    identifier=nexus_data['identifier'],
                    territory_id=str(nexus_data['territory_id']),
                    health=nexus_data.get('health', 0),
                    guild_id=guild_id
                )
                await nexus.upsert(conn)

        # Import Unit Types
        if 'unit_types' in config_dict:
            for unit_type_data in config_dict['unit_types']:
                stats = unit_type_data.get('stats', {})
                cost = unit_type_data.get('cost', {})
                upkeep = unit_type_data.get('upkeep', {})

                unit_type = UnitType(
                    type_id=unit_type_data['type_id'],
                    name=unit_type_data['name'],
                    nation=unit_type_data.get('nation'),
                    movement=stats.get('movement', 1),
                    organization=stats.get('organization', 10),
                    attack=stats.get('attack', 0),
                    defense=stats.get('defense', 0),
                    siege_attack=stats.get('siege_attack', 0),
                    siege_defense=stats.get('siege_defense', 0),
                    size=stats.get('size', 1),
                    capacity=stats.get('capacity', 0),
                    is_naval=stats.get('is_naval', False),
                    keywords=stats.get('keywords', []),
                    cost_ore=cost.get('ore', 0),
                    cost_lumber=cost.get('lumber', 0),
                    cost_coal=cost.get('coal', 0),
                    cost_rations=cost.get('rations', 0),
                    cost_cloth=cost.get('cloth', 0),
                    cost_platinum=cost.get('platinum', 0),
                    upkeep_ore=upkeep.get('ore', 0),
                    upkeep_lumber=upkeep.get('lumber', 0),
                    upkeep_coal=upkeep.get('coal', 0),
                    upkeep_rations=upkeep.get('rations', 0),
                    upkeep_cloth=upkeep.get('cloth', 0),
                    upkeep_platinum=upkeep.get('platinum', 0),
                    guild_id=guild_id
                )
                await unit_type.upsert(conn)

        # Import Building Types
        if 'building_types' in config_dict:
            for building_type_data in config_dict['building_types']:
                cost = building_type_data.get('cost', {})
                upkeep = building_type_data.get('upkeep', {})

                building_type = BuildingType(
                    type_id=building_type_data['type_id'],
                    name=building_type_data['name'],
                    description=building_type_data.get('description'),
                    cost_ore=cost.get('ore', 0),
                    cost_lumber=cost.get('lumber', 0),
                    cost_coal=cost.get('coal', 0),
                    cost_rations=cost.get('rations', 0),
                    cost_cloth=cost.get('cloth', 0),
                    cost_platinum=cost.get('platinum', 0),
                    upkeep_ore=upkeep.get('ore', 0),
                    upkeep_lumber=upkeep.get('lumber', 0),
                    upkeep_coal=upkeep.get('coal', 0),
                    upkeep_rations=upkeep.get('rations', 0),
                    upkeep_cloth=upkeep.get('cloth', 0),
                    upkeep_platinum=upkeep.get('platinum', 0),
                    keywords=building_type_data.get('keywords', []),
                    guild_id=guild_id
                )
                await building_type.upsert(conn)

        # Import Buildings
        if 'buildings' in config_dict:
            for building_data in config_dict['buildings']:
                # Get building type to copy upkeep values
                building_type = await BuildingType.fetch_by_type_id(conn, building_data['type'], guild_id)
                if not building_type:
                    logger.warning(f"Building type {building_data['type']} not found, skipping building {building_data['building_id']}")
                    continue

                # Check for duplicate building type in territory
                territory_id_str = str(building_data['territory_id']) if building_data.get('territory_id') else None
                if territory_id_str:
                    existing = await Building.fetch_by_territory(conn, territory_id_str, guild_id)
                    if any(b.building_type == building_data['type'] for b in existing):
                        logger.warning(f"Territory {territory_id_str} already has building type {building_data['type']}, skipping")
                        continue

                # Check fortification city-only restriction
                if building_type.keywords and 'fortification' in [k.lower() for k in building_type.keywords]:
                    if territory_id_str:
                        territory = await Territory.fetch_by_territory_id(conn, territory_id_str, guild_id)
                        if territory and territory.terrain_type.lower() != 'city':
                            logger.warning(f"Fortification building {building_data['building_id']} can only be placed in cities, skipping (territory {territory_id_str} is {territory.terrain_type})")
                            continue

                # Keywords: use building_data keywords if provided, otherwise inherit from building_type
                if 'keywords' in building_data:
                    building_keywords = building_data['keywords']
                else:
                    building_keywords = building_type.keywords.copy() if building_type.keywords else []

                building = Building(
                    building_id=building_data['building_id'],
                    name=building_data.get('name'),
                    building_type=building_data['type'],
                    territory_id=str(building_data['territory_id']) if building_data.get('territory_id') else None,
                    durability=building_data.get('durability', 10),
                    status=building_data.get('status', 'ACTIVE'),
                    upkeep_ore=building_type.upkeep_ore,
                    upkeep_lumber=building_type.upkeep_lumber,
                    upkeep_coal=building_type.upkeep_coal,
                    upkeep_rations=building_type.upkeep_rations,
                    upkeep_cloth=building_type.upkeep_cloth,
                    upkeep_platinum=building_type.upkeep_platinum,
                    keywords=building_keywords,
                    guild_id=guild_id
                )
                await building.upsert(conn)

        # Import Units
        if 'units' in config_dict:
            for unit_data in config_dict['units']:
                # Determine owner - either character or faction
                owner_character_id = None
                owner_faction_id = None

                if 'owner' in unit_data:
                    owner_char = character_map.get(unit_data['owner'])
                    if not owner_char:
                        logger.warning(f"Owner character {unit_data['owner']} not found, skipping unit {unit_data['unit_id']}")
                        continue
                    owner_character_id = owner_char.id
                elif 'owner_faction' in unit_data:
                    owner_faction_id = faction_map.get(unit_data['owner_faction'])
                    if not owner_faction_id:
                        logger.warning(f"Owner faction {unit_data['owner_faction']} not found, skipping unit {unit_data['unit_id']}")
                        continue
                else:
                    logger.warning(f"Unit {unit_data['unit_id']} has no owner or owner_faction, skipping")
                    continue

                commander_char_id = None
                if 'commander' in unit_data:
                    commander_char = character_map.get(unit_data['commander'])
                    if commander_char:
                        commander_char_id = commander_char.id

                faction_internal_id = None
                if 'faction_id' in unit_data:
                    # Try to get from faction_map first (if factions were imported in same run)
                    faction_internal_id = faction_map.get(unit_data['faction_id'])

                    # If not in map, fetch from database
                    if not faction_internal_id:
                        faction_obj = await Faction.fetch_by_faction_id(conn, unit_data['faction_id'], guild_id)
                        if faction_obj:
                            faction_internal_id = faction_obj.id

                # For faction-owned units, the faction_id field should be the owning faction
                if owner_faction_id and not faction_internal_id:
                    faction_internal_id = owner_faction_id

                # Get unit type to determine stats
                unit_type = await UnitType.fetch_by_type_id(conn, unit_data['type'], guild_id)

                if not unit_type:
                    logger.warning(f"Unit type {unit_data['type']} not found, skipping unit {unit_data['unit_id']}")
                    continue

                current_org = unit_data.get('current_organization', unit_type.organization)

                unit = Unit(
                    unit_id=unit_data['unit_id'],
                    name=unit_data.get('name'),
                    unit_type=unit_data['type'],
                    owner_character_id=owner_character_id,
                    owner_faction_id=owner_faction_id,
                    commander_character_id=commander_char_id,
                    faction_id=faction_internal_id,
                    movement=unit_type.movement,
                    organization=current_org,
                    max_organization=unit_type.organization,
                    attack=unit_type.attack,
                    defense=unit_type.defense,
                    siege_attack=unit_type.siege_attack,
                    siege_defense=unit_type.siege_defense,
                    size=unit_type.size,
                    capacity=unit_type.capacity,
                    current_territory_id=str(unit_data['current_territory_id']) if unit_data.get('current_territory_id') is not None else None,
                    is_naval=unit_type.is_naval,
                    upkeep_ore=unit_type.upkeep_ore,
                    upkeep_lumber=unit_type.upkeep_lumber,
                    upkeep_coal=unit_type.upkeep_coal,
                    upkeep_rations=unit_type.upkeep_rations,
                    upkeep_cloth=unit_type.upkeep_cloth,
                    upkeep_platinum=unit_type.upkeep_platinum,
                    keywords=unit_type.keywords,
                    guild_id=guild_id
                )
                await unit.upsert(conn)

        logger.info(f"Successfully imported wargame config for guild {guild_id}")
        return True, "Configuration imported successfully"
