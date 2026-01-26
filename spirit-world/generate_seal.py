#!/usr/bin/env python3
r"""
Spirit Seal Generator - Creates LaTeX \sSpiritSeal blocks
by pulling conditions and costs from conditions-and-costs.csv.
"""

import csv
import random
import math
import os
from pathlib import Path


def load_items(csv_path):
    """Load and parse items from the CSV file."""
    items = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            min_danger = row['Minimum Danger'].strip()
            items.append({
                'difficulty': row['Difficulty'].strip(),
                'can_be_trap': row['Can be Trap?'].strip().lower() == 'yes',
                'type': row['Condition or Cost'].strip(),
                'min_danger': int(min_danger) if min_danger else None,
                'text': row['Thing'].strip()
            })
    return items


def filter_by_danger(items, seal_danger):
    """Filter items by danger level."""
    return [
        item for item in items
        if item['min_danger'] is None or item['min_danger'] <= seal_danger
    ]


def get_difficulty_weights(difficulty):
    """Get weights for Easy/Medium/Hard based on seal difficulty."""
    weights = {
        1: {'Easy': 100, 'Medium': 0, 'Hard': 0},
        2: {'Easy': 100, 'Medium': 0, 'Hard': 0},
        3: {'Easy': 70, 'Medium': 30, 'Hard': 0},
        4: {'Easy': 70, 'Medium': 30, 'Hard': 0},
        5: {'Easy': 50, 'Medium': 45, 'Hard': 5},
        6: {'Easy': 30, 'Medium': 40, 'Hard': 30},
        7: {'Easy': 30, 'Medium': 40, 'Hard': 30},
        8: {'Easy': 15, 'Medium': 35, 'Hard': 50},
        9: {'Easy': 15, 'Medium': 35, 'Hard': 50},
        10: {'Easy': 10, 'Medium': 25, 'Hard': 65},
    }
    return weights.get(difficulty, weights[10])


def get_minimum_requirements(difficulty):
    """Get minimum item requirements per row based on difficulty."""
    requirements = []
    if difficulty <= 5:
        requirements.append('Easy')
    if difficulty >= 4:
        requirements.append('Medium')
    if difficulty >= 7:
        requirements.append('Hard')
    return requirements


def get_extra_rows(difficulty):
    """Get extra bonus rows for lower difficulties.

    Lower difficulty seals get extra rows above the minimum needed,
    giving players more options to choose from.
    """
    # Difficulty 1-2: +3, 3-4: +2, 5-6: +1, 7+: +0
    return max(0, 4 - math.ceil(difficulty / 2))


def weighted_random_choice(items, weights):
    """Select an item using weighted random selection based on difficulty tier."""
    weighted_items = []
    for item in items:
        tier = item['difficulty']
        weight = weights.get(tier, 0)
        if weight > 0:
            weighted_items.append((item, weight))

    if not weighted_items:
        # Fallback: equal weight for all items
        return random.choice(items) if items else None

    total = sum(w for _, w in weighted_items)
    r = random.uniform(0, total)
    cumulative = 0
    for item, weight in weighted_items:
        cumulative += weight
        if r <= cumulative:
            return item
    return weighted_items[-1][0]


def select_item_with_requirements(available_items, weights, required_tiers, used_items):
    """Select an item, ensuring required tiers are met if possible."""
    # Filter out already used items
    candidates = [i for i in available_items if i['text'] not in used_items]

    if not candidates:
        return None

    # Check if we need to fulfill any required tier
    for tier in required_tiers:
        tier_items = [i for i in candidates if i['difficulty'] == tier]
        if tier_items:
            selected = random.choice(tier_items)
            return selected

    # No required tiers left, use weighted selection
    return weighted_random_choice(candidates, weights)


def generate_row(conditions, costs, trap_costs, weights, min_requirements, is_trap_row, used_items):
    """Generate a single row with 3 columns.

    - Columns 1-2: Condition or Cost (at least 1 condition required)
    - Column 3: Cost only (trap if is_trap_row)
    """
    row = [None, None, None]
    row_used = set()
    remaining_requirements = min_requirements.copy()

    # Column 3: Cost (trap if needed)
    if is_trap_row:
        col3_candidates = [c for c in trap_costs if c['text'] not in used_items]
    else:
        col3_candidates = [c for c in costs if c['text'] not in used_items]

    if col3_candidates:
        col3_item = select_item_with_requirements(
            col3_candidates, weights, remaining_requirements, used_items
        )
        if col3_item:
            row[2] = col3_item
            row_used.add(col3_item['text'])
            if col3_item['difficulty'] in remaining_requirements:
                remaining_requirements.remove(col3_item['difficulty'])

    # We need at least 1 condition in columns 1-2
    # Strategy: randomly decide which column gets the condition (or both)
    condition_placement = random.choice(['col1', 'col2', 'both'])

    available_conditions = [c for c in conditions if c['text'] not in used_items and c['text'] not in row_used]
    available_costs = [c for c in costs if c['text'] not in used_items and c['text'] not in row_used]

    if condition_placement == 'col1':
        # Col1 = condition, Col2 = condition or cost
        if available_conditions:
            col1_item = select_item_with_requirements(
                available_conditions, weights, remaining_requirements, used_items | row_used
            )
            if col1_item:
                row[0] = col1_item
                row_used.add(col1_item['text'])
                if col1_item['difficulty'] in remaining_requirements:
                    remaining_requirements.remove(col1_item['difficulty'])

        # Col2 can be either
        col2_pool = [c for c in conditions + costs if c['text'] not in used_items and c['text'] not in row_used]
        if col2_pool:
            col2_item = select_item_with_requirements(
                col2_pool, weights, remaining_requirements, used_items | row_used
            )
            if col2_item:
                row[1] = col2_item
                row_used.add(col2_item['text'])

    elif condition_placement == 'col2':
        # Col1 = condition or cost, Col2 = condition
        col1_pool = [c for c in conditions + costs if c['text'] not in used_items and c['text'] not in row_used]
        if col1_pool:
            col1_item = select_item_with_requirements(
                col1_pool, weights, remaining_requirements, used_items | row_used
            )
            if col1_item:
                row[0] = col1_item
                row_used.add(col1_item['text'])
                if col1_item['difficulty'] in remaining_requirements:
                    remaining_requirements.remove(col1_item['difficulty'])

        available_conditions_now = [c for c in conditions if c['text'] not in used_items and c['text'] not in row_used]
        if available_conditions_now:
            col2_item = select_item_with_requirements(
                available_conditions_now, weights, remaining_requirements, used_items | row_used
            )
            if col2_item:
                row[1] = col2_item
                row_used.add(col2_item['text'])

    else:  # both
        # Both columns get conditions
        for col_idx in [0, 1]:
            available_conditions_now = [c for c in conditions if c['text'] not in used_items and c['text'] not in row_used]
            if available_conditions_now:
                item = select_item_with_requirements(
                    available_conditions_now, weights, remaining_requirements, used_items | row_used
                )
                if item:
                    row[col_idx] = item
                    row_used.add(item['text'])
                    if item['difficulty'] in remaining_requirements:
                        remaining_requirements.remove(item['difficulty'])

    # Verify we have at least 1 condition in columns 1-2
    has_condition = any(row[i] and row[i]['type'] == 'Condition' for i in [0, 1])

    # If no condition yet, force one
    if not has_condition:
        available_conditions_now = [c for c in conditions if c['text'] not in used_items and c['text'] not in row_used]
        if available_conditions_now:
            # Replace col1 or col2 with a condition
            replace_col = 0 if row[0] is None or random.random() < 0.5 else 1
            item = random.choice(available_conditions_now)
            if row[replace_col]:
                row_used.discard(row[replace_col]['text'])
            row[replace_col] = item
            row_used.add(item['text'])

    # Fill any None slots
    for col_idx in [0, 1]:
        if row[col_idx] is None:
            pool = [c for c in conditions + costs if c['text'] not in used_items and c['text'] not in row_used]
            if pool:
                item = weighted_random_choice(pool, weights)
                if item:
                    row[col_idx] = item
                    row_used.add(item['text'])

    if row[2] is None:
        pool = [c for c in costs if c['text'] not in used_items and c['text'] not in row_used]
        if is_trap_row:
            pool = [c for c in trap_costs if c['text'] not in used_items and c['text'] not in row_used]
        if pool:
            item = weighted_random_choice(pool, weights)
            if item:
                row[2] = item
                row_used.add(item['text'])

    return row, row_used


def format_latex_output(seal_name, rows_to_escape, rows_to_clear, rows, trap_row_indices):
    """Format the output as LaTeX."""
    lines = []
    lines.append(f"\\sSpiritSeal[\\small]{{{seal_name}}}")
    lines.append(f"            {{{rows_to_escape}}}{{{rows_to_clear}}}")
    lines.append("            {")

    for i, row in enumerate(rows):
        is_trap = i in trap_row_indices
        col1_text = row[0]['text'] if row[0] else "---"
        col2_text = row[1]['text'] if row[1] else "---"
        col3_text = row[2]['text'] if row[2] else "---"

        if is_trap:
            col3_text = f"\\textbf{{TRAP}} \\\\ {col3_text}"

        lines.append(f"            \\satrow{{{col1_text}}}")
        lines.append(f"                   {{{col2_text}}}")
        lines.append(f"                   {{{col3_text}}}")

    lines.append("            }")

    return "\n".join(lines)


def generate_seal(all_items, seal_name, difficulty, danger):
    """Generate a seal with the given parameters."""
    # Calculate derived values
    rows_to_clear = math.floor(difficulty / 2) + 2
    rows_to_escape = math.floor(danger / 3) + 1
    # Cap rows_to_escape at rows_to_clear - 1
    rows_to_escape = min(rows_to_escape, rows_to_clear - 1)

    # Extra rows for lower difficulties (bonus options above the minimum)
    extra_rows = get_extra_rows(difficulty)
    total_rows = rows_to_clear + extra_rows

    print(f"\nGenerating seal with {total_rows} total rows ({rows_to_clear} to clear, {extra_rows} bonus, {rows_to_escape} trap rows)...\n")

    # Filter items by danger
    filtered_items = filter_by_danger(all_items, danger)

    # Separate conditions and costs
    conditions = [i for i in filtered_items if i['type'] == 'Condition']
    costs = [i for i in filtered_items if i['type'] == 'Cost']
    trap_costs = [i for i in costs if i['can_be_trap']]

    if not conditions:
        print("Error: No conditions available for this danger level.")
        return None
    if not costs:
        print("Error: No costs available for this danger level.")
        return None
    if rows_to_escape > 0 and not trap_costs:
        print("Warning: No trap costs available, using regular costs for traps.")
        trap_costs = costs

    # Get weights and requirements
    weights = get_difficulty_weights(difficulty)
    min_requirements = get_minimum_requirements(difficulty)

    # Generate rows
    rows = []
    used_items = set()

    # Trap rows are at the bottom (within the rows_to_clear portion)
    # Extra rows are at the top, then non-trap rows, then trap rows at bottom
    trap_row_indices = set(range(total_rows - rows_to_escape, total_rows))

    for row_idx in range(total_rows):
        is_trap_row = row_idx in trap_row_indices
        row, row_used = generate_row(
            conditions, costs, trap_costs, weights,
            min_requirements.copy(), is_trap_row, used_items
        )
        rows.append(row)
        used_items.update(row_used)

    # Generate output
    return format_latex_output(seal_name, rows_to_escape, rows_to_clear, rows, trap_row_indices)


def main():
    # Find the CSV file
    script_dir = Path(__file__).parent
    csv_path = script_dir / "conditions-and-costs.csv"

    if not csv_path.exists():
        print(f"Error: Could not find {csv_path}")
        return

    # Load items
    all_items = load_items(csv_path)

    # Get user input
    print("=== Spirit Seal Generator ===\n")

    seal_name = input("Seal name: ").strip()
    if not seal_name:
        seal_name = "Unnamed Seal"

    while True:
        try:
            difficulty = int(input("Seal difficulty (1-10): ").strip())
            if 1 <= difficulty <= 10:
                break
            print("Please enter a number between 1 and 10.")
        except ValueError:
            print("Please enter a valid integer.")

    while True:
        try:
            danger = int(input("Seal danger (1-8): ").strip())
            if 1 <= danger <= 8:
                break
            print("Please enter a number between 1 and 8.")
        except ValueError:
            print("Please enter a valid integer.")

    # Generate and display seal, with option to regenerate
    while True:
        output = generate_seal(all_items, seal_name, difficulty, danger)
        if output is None:
            return

        print("=" * 60)
        print(output)
        print("=" * 60)

        regenerate = input("\nRegenerate? (y/n): ").strip().lower()
        if regenerate != 'y':
            break


if __name__ == "__main__":
    main()
