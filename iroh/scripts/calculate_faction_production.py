#!/usr/bin/env python3
"""
Calculate net production for each faction.

Reads territory, building, and unit data from production_config.yaml and
calculates gross production, upkeep costs, and net production per faction.
"""

import sys
from pathlib import Path
from collections import defaultdict

import yaml

RESOURCES = ["ore", "lumber", "coal", "rations", "cloth", "platinum"]

# Building production bonuses (+2 to respective resource)
BUILDING_BONUSES = {
    "quarry": "ore",
    "foundry": "ore",
    "lumber-yard": "lumber",
    "lumber-processing": "lumber",
    "mine": "coal",
    "strip-mine": "coal",
    "granary": "rations",
    "factory-farm": "rations",
    "weavery": "cloth",
    "cloth-factory": "cloth",
    "mint": "platinum",
}

# Building upkeep costs
BUILDING_UPKEEP = {
    "shrine": {"ore": 1},
    "temple": {"ore": 1},
    "university": {"platinum": 1},
    "public-school": {"platinum": 1},
    "hospital": {"ore": 1, "platinum": 1},
    "quarry": {"lumber": 1},
    "lumber-yard": {"ore": 1},
    "mine": {"lumber": 1},
    "granary": {"lumber": 1},
    "weavery": {"lumber": 1},
    "mint": {"lumber": 1},
    "foundry": {"coal": 1},
    "lumber-processing": {"coal": 1},
    "strip-mine": {"lumber": 1},
    "factory-farm": {"lumber": 1},
    "cloth-factory": {"coal": 1},
    "reinforced-walls": {"ore": 1},
    "ballistae": {"lumber": 1},
    "bastion": {"ore": 1},
    "motte-and-bailey": {"ore": 1},
}

# Unit upkeep costs
UNIT_UPKEEP = {
    "infantry": {"rations": 1},
    "cavalry": {"rations": 1},
    "scout": {"rations": 1},
    "spy": {"rations": 1, "platinum": 1},
    "siege-engine": {"rations": 1, "ore": 1},
    "transport": {"lumber": 1, "ore": 1},
    "battleship": {"lumber": 2, "ore": 1, "cloth": 1},
    "frigate": {"lumber": 1, "ore": 1, "cloth": 1},
    # Water Tribe
    "water-bender-brigade": {"rations": 1, "cloth": 1},
    "water-tribe-marines": {"rations": 1, "cloth": 1},
    "water-tribe-sloop": {"rations": 1, "ore": 1},
    # Fire Nation
    "fire-bender-brigade": {"rations": 1, "coal": 1},
    "proto-tank": {"coal": 2, "ore": 1},
    "ironclad": {"coal": 2, "ore": 2},
    "fire-sage": {},  # No upkeep
    # Earth Kingdom
    "earth-bender-brigade": {"rations": 1, "ore": 1},
    "earth-combat-engineers": {"rations": 1, "ore": 1},
    "dai-li-squad": {},  # No upkeep
    "kyoshi-warriors": {"rations": 1, "cloth": 1},
    # Fifth Nation
    "mixed-bender-brigade": {"rations": 1, "cloth": 1},
    "fifth-nation-sloop": {"lumber": 1, "ore": 1, "cloth": 1},
}


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_territory_controller_map(config: dict) -> dict[str, str]:
    """Map territory_id -> controller faction."""
    mapping = {}
    for territory in config.get("territories", []):
        tid = territory.get("territory_id")
        controller = territory.get("controller")
        if tid and controller:
            mapping[tid] = controller
    return mapping


def calculate_territory_production(config: dict) -> dict[str, dict[str, int]]:
    """Calculate gross production per faction from territories."""
    faction_production = defaultdict(lambda: {r: 0 for r in RESOURCES})

    for territory in config.get("territories", []):
        controller = territory.get("controller")
        if not controller:
            continue

        # Skip sacred-land territories
        keywords = territory.get("keywords", [])
        if "sacred-land" in keywords:
            continue

        production = territory.get("production", {})
        for resource in RESOURCES:
            faction_production[controller][resource] += production.get(resource, 0)

    return dict(faction_production)


def calculate_building_effects(config: dict, territory_map: dict[str, str]) -> tuple[dict, dict]:
    """Calculate building bonuses and upkeep per faction."""
    faction_bonuses = defaultdict(lambda: {r: 0 for r in RESOURCES})
    faction_upkeep = defaultdict(lambda: {r: 0 for r in RESOURCES})

    for building in config.get("buildings", []):
        territory_id = building.get("territory_id")
        building_type = building.get("type")

        if not territory_id or not building_type:
            continue

        controller = territory_map.get(territory_id)
        if not controller:
            continue

        # Add production bonus
        if building_type in BUILDING_BONUSES:
            resource = BUILDING_BONUSES[building_type]
            faction_bonuses[controller][resource] += 2

        # Add upkeep
        if building_type in BUILDING_UPKEEP:
            for resource, cost in BUILDING_UPKEEP[building_type].items():
                faction_upkeep[controller][resource] += cost

    return dict(faction_bonuses), dict(faction_upkeep)


def calculate_unit_upkeep(config: dict) -> dict[str, dict[str, int]]:
    """Calculate unit upkeep per faction."""
    faction_upkeep = defaultdict(lambda: {r: 0 for r in RESOURCES})

    for unit in config.get("units", []):
        owner_faction = unit.get("owner_faction")
        unit_type = unit.get("type")

        if not owner_faction or not unit_type:
            continue

        if unit_type in UNIT_UPKEEP:
            for resource, cost in UNIT_UPKEEP[unit_type].items():
                faction_upkeep[owner_faction][resource] += cost

    return dict(faction_upkeep)


def count_units_by_faction(config: dict) -> dict[str, int]:
    """Count total units per faction."""
    counts = defaultdict(int)
    for unit in config.get("units", []):
        owner = unit.get("owner_faction")
        if owner:
            counts[owner] += 1
    return dict(counts)


def count_buildings_by_faction(config: dict, territory_map: dict[str, str]) -> dict[str, int]:
    """Count total buildings per faction."""
    counts = defaultdict(int)
    for building in config.get("buildings", []):
        territory_id = building.get("territory_id")
        if territory_id:
            controller = territory_map.get(territory_id)
            if controller:
                counts[controller] += 1
    return dict(counts)


def count_territories_by_faction(config: dict) -> dict[str, int]:
    """Count territories per faction (excluding sacred-land)."""
    counts = defaultdict(int)
    for territory in config.get("territories", []):
        controller = territory.get("controller")
        keywords = territory.get("keywords", [])
        if controller and "sacred-land" not in keywords:
            counts[controller] += 1
    return dict(counts)


def get_faction_spending(config: dict) -> dict[str, dict[str, int]]:
    """Get faction spending from faction definitions."""
    faction_spending = defaultdict(lambda: {r: 0 for r in RESOURCES})
    for faction in config.get("factions", []):
        faction_id = faction.get("faction_id")
        spending = faction.get("spending", {})
        if faction_id and spending:
            for resource in RESOURCES:
                faction_spending[faction_id][resource] = spending.get(resource, 0)
    return dict(faction_spending)


def print_faction_report(
    faction: str,
    territory_count: int,
    building_count: int,
    unit_count: int,
    production: dict[str, int],
    bonuses: dict[str, int],
    building_upkeep: dict[str, int],
    unit_upkeep: dict[str, int],
    spending: dict[str, int] = None,
):
    """Print production report for a single faction."""
    if spending is None:
        spending = {}

    print(f"\n{'='*70}")
    print(f" {faction.upper()}")
    print(f"{'='*70}")
    print(f"  Territories: {territory_count}  |  Buildings: {building_count}  |  Units: {unit_count}")

    # Calculate totals
    total_production = {r: production.get(r, 0) + bonuses.get(r, 0) for r in RESOURCES}
    total_upkeep = {r: building_upkeep.get(r, 0) + unit_upkeep.get(r, 0) + spending.get(r, 0) for r in RESOURCES}
    net = {r: total_production[r] - total_upkeep[r] for r in RESOURCES}

    # --- PRODUCTION BREAKDOWN ---
    print(f"\n  PRODUCTION")
    print(f"  {'-'*66}")
    print(f"  {'Resource':<10} {'Territory':>10} {'Buildings':>10} {'Total':>10}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    total_terr_prod = 0
    total_bldg_bonus = 0
    total_prod = 0
    for resource in RESOURCES:
        terr_prod = production.get(resource, 0)
        bldg_bonus = bonuses.get(resource, 0)
        total = total_production[resource]
        total_terr_prod += terr_prod
        total_bldg_bonus += bldg_bonus
        total_prod += total

        bldg_str = f"+{bldg_bonus}" if bldg_bonus > 0 else str(bldg_bonus) if bldg_bonus else "-"
        print(f"  {resource:<10} {terr_prod:>10} {bldg_str:>10} {total:>10}")

    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    print(f"  {'TOTAL':<10} {total_terr_prod:>10} {'+' + str(total_bldg_bonus):>10} {total_prod:>10}")

    # --- UPKEEP BREAKDOWN ---
    has_spending = any(spending.get(r, 0) > 0 for r in RESOURCES)
    print(f"\n  UPKEEP")
    print(f"  {'-'*66}")
    if has_spending:
        print(f"  {'Resource':<10} {'Buildings':>10} {'Units':>10} {'Spending':>10} {'Total':>10}")
        print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    else:
        print(f"  {'Resource':<10} {'Buildings':>10} {'Units':>10} {'Total':>10}")
        print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    total_bldg_upkeep = 0
    total_unit_upkeep = 0
    total_spending = 0
    total_upkeep_sum = 0
    for resource in RESOURCES:
        bldg_up = building_upkeep.get(resource, 0)
        unit_up = unit_upkeep.get(resource, 0)
        spend = spending.get(resource, 0)
        total_up = total_upkeep[resource]
        total_bldg_upkeep += bldg_up
        total_unit_upkeep += unit_up
        total_spending += spend
        total_upkeep_sum += total_up

        bldg_str = str(bldg_up) if bldg_up else "-"
        unit_str = str(unit_up) if unit_up else "-"
        spend_str = str(spend) if spend else "-"
        total_str = str(total_up) if total_up else "-"
        if has_spending:
            print(f"  {resource:<10} {bldg_str:>10} {unit_str:>10} {spend_str:>10} {total_str:>10}")
        else:
            print(f"  {resource:<10} {bldg_str:>10} {unit_str:>10} {total_str:>10}")

    if has_spending:
        print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        print(f"  {'TOTAL':<10} {total_bldg_upkeep:>10} {total_unit_upkeep:>10} {total_spending:>10} {total_upkeep_sum:>10}")
    else:
        print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        print(f"  {'TOTAL':<10} {total_bldg_upkeep:>10} {total_unit_upkeep:>10} {total_upkeep_sum:>10}")

    # --- NET PRODUCTION ---
    print(f"\n  NET PRODUCTION")
    print(f"  {'-'*66}")
    print(f"  {'Resource':<10} {'Production':>10} {'Upkeep':>10} {'Net':>10}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    for resource in RESOURCES:
        prod = total_production[resource]
        upkeep = total_upkeep[resource]
        net_val = net[resource]

        # Format net with sign and highlight deficits
        if net_val > 0:
            net_str = f"+{net_val}"
        elif net_val < 0:
            net_str = f"{net_val} ⚠"
        else:
            net_str = "0"

        print(f"  {resource:<10} {prod:>10} {'-' + str(upkeep) if upkeep else '-':>10} {net_str:>10}")

    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    net_total = total_prod - total_upkeep_sum
    net_str = f"+{net_total}" if net_total > 0 else str(net_total)
    print(f"  {'TOTAL':<10} {total_prod:>10} {'-' + str(total_upkeep_sum):>10} {net_str:>10}")

    # Print summary
    print()
    deficits = [r for r in RESOURCES if net[r] < 0]
    if deficits:
        print(f"  ⚠ DEFICITS: {', '.join(deficits)}")
    else:
        print(f"  ✓ No deficits")


def main():
    script_dir = Path(__file__).parent
    iroh_dir = script_dir.parent

    config_path = iroh_dir / "production_config.yaml"

    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading config from {config_path}...")
    config = load_config(config_path)

    # Build mappings
    territory_map = get_territory_controller_map(config)

    # Calculate all metrics
    territory_production = calculate_territory_production(config)
    building_bonuses, building_upkeep = calculate_building_effects(config, territory_map)
    unit_upkeep = calculate_unit_upkeep(config)
    faction_spending = get_faction_spending(config)

    # Count entities
    territory_counts = count_territories_by_faction(config)
    building_counts = count_buildings_by_faction(config, territory_map)
    unit_counts = count_units_by_faction(config)

    # Get all factions
    all_factions = set()
    all_factions.update(territory_production.keys())
    all_factions.update(building_bonuses.keys())
    all_factions.update(unit_upkeep.keys())
    all_factions.update(faction_spending.keys())

    # Print report for each faction
    for faction in sorted(all_factions):
        print_faction_report(
            faction,
            territory_counts.get(faction, 0),
            building_counts.get(faction, 0),
            unit_counts.get(faction, 0),
            territory_production.get(faction, {}),
            building_bonuses.get(faction, {}),
            building_upkeep.get(faction, {}),
            unit_upkeep.get(faction, {}),
            faction_spending.get(faction, {}),
        )

    print("\n" + "="*60)
    print(" SUMMARY")
    print("="*60)

    # Print summary table
    print(f"\n  {'Faction':<20} {'Units':>6} {'Bldgs':>6} {'Terrs':>6}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}")
    for faction in sorted(all_factions):
        print(f"  {faction:<20} {unit_counts.get(faction, 0):>6} {building_counts.get(faction, 0):>6} {territory_counts.get(faction, 0):>6}")

    print()


if __name__ == "__main__":
    main()
