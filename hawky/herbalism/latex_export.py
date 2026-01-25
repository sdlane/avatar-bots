"""
LaTeX export functions for herbalism data.

Converts ingredients and products to GameTeX format for printing item cards.
"""

import sys
from pathlib import Path
from typing import List

# Handle both direct execution and module import
if __name__ == "__main__":
    # Add parent directories to path for direct execution
    # Script is in hawky/herbalism/
    herbalism_dir = Path(__file__).parent
    hawky_dir = herbalism_dir.parent
    avatar_bots_dir = hawky_dir.parent
    sys.path.insert(0, str(herbalism_dir))
    sys.path.insert(0, str(hawky_dir))
    sys.path.insert(0, str(avatar_bots_dir))

    from db import Ingredient, Product
    from loaders import load_ingredients, load_products
else:
    from db import Ingredient, Product
    from .loaders import load_ingredients, load_products

# --- Configuration ---
# Update these paths to point to your CSV files

INGREDIENTS_FILE = "production_data/herbal_ingredients.csv"
PRODUCTS_FILE = "production_data/herbal_ingredients.csv"
PRODUCTS_FILE = None


def convert_ingredient(ingredient: Ingredient) -> str:
    """
    Convert a single ingredient to GameTeX format.

    Returns an empty string if skip_export is True.
    """
    if ingredient.skip_export:
        return ""

    # Escape special LaTeX characters in text fields
    name = _escape_latex(ingredient.name or "")
    item_number = _escape_latex(ingredient.item_number or "")
    flavor_text = _escape_latex(ingredient.flavor_text or "")
    rules_text = ingredient.rules_text or ""
    macro = ingredient.macro or "Unknown"

    return f"""\\NEW{{Item}}{{\\i{macro}}}{{
  \\s\\MYname     {{Ingredient: {name}}}
  \\s\\MYnumber   {{{item_number}}}
  \\s\\MYtext     {{\\textit{{{flavor_text}}}

{rules_text}
}}
}}
"""


def convert_ingredients(ingredients: List[Ingredient]) -> str:
    """
    Convert a list of ingredients to GameTeX format.

    Sorts ingredients by rarity (common, uncommon, rare, spirit world, special),
    then alphabetically by macro within each rarity.
    """
    # Define rarity sort order
    rarity_order = {
        "common": 0,
        "uncommon": 1,
        "rare": 2,
        "spirit world": 3,
        "special": 4,
    }

    def rarity_sort_key(ingredient: Ingredient) -> tuple:
        rarity = (ingredient.rarity or "").lower()
        rarity_rank = rarity_order.get(rarity, 999)  # Unknown rarities sort last
        macro = (ingredient.macro or "").lower()
        return (rarity_rank, macro)

    sorted_ingredients = sorted(ingredients, key=rarity_sort_key)

    # Convert each ingredient, adding rarity headers
    parts = []
    current_rarity = None

    for ing in sorted_ingredients:
        # Skip if marked for skip
        if ing.skip_export:
            continue

        # Add rarity header comment if rarity changed
        rarity = (ing.rarity or "").lower()
        if rarity != current_rarity:
            current_rarity = rarity
            rarity_header = f"\n% ===== {rarity.upper()} =====\n"
            parts.append(rarity_header)

        converted = convert_ingredient(ing)
        if converted:
            parts.append(converted)

    return "\n".join(parts)


def convert_product(product: Product) -> str:
    """
    Convert a single product to GameTeX format.

    Returns an empty string if skip_export is True.
    """
    if product.skip_export:
        return ""

    # Escape special LaTeX characters in text fields
    product_type = _escape_latex((product.product_type or "").title())
    name = _escape_latex(product.name or "")
    item_number = _escape_latex(product.item_number or "")
    flavor_text = _escape_latex(product.flavor_text or "")
    rules_text = _escape_latex(product.rules_text or "")
    macro = product.macro or "Unknown"

    # Format: "Type: Name"
    display_name = f"{product_type}: {name}" if name else product_type

    return f"""\\NEW{{ItemFold}}{{\\i{macro}}}{{
  \\s\\MYname    {{{display_name}}}
  \\s\\MYnumber    {{{item_number}}}
  \\s\\MYtext    {{\\textit{{{flavor_text}}}}}
  \\s\\MYcontents    {{{rules_text}}}
}}
"""


def convert_products(products: List[Product]) -> str:
    """
    Convert a list of products to GameTeX format.

    Sorts products by type, then alphabetically by macro within each type.
    Inserts LaTeX comments between each new type of product.
    """
    # Sort by type, then by macro
    sorted_products = sorted(
        products,
        key=lambda p: ((p.product_type or "").lower(), (p.macro or "").lower())
    )

    parts = []
    current_type = None

    for prod in sorted_products:
        # Skip if marked for skip
        if prod.skip_export:
            continue

        # Add type header comment if type changed
        product_type = (prod.product_type or "").lower()
        if product_type != current_type:
            current_type = product_type
            type_header = f"\n% ===== {product_type.upper()} =====\n"
            parts.append(type_header)

        converted = convert_product(prod)
        if converted:
            parts.append(converted)

    return "\n".join(parts)


def convert_to_latex(
    ingredients_file: str = INGREDIENTS_FILE,
    products_file: str = PRODUCTS_FILE
):
    """
    Main function to convert CSV files to LaTeX.

    Reads ingredients and products from CSV files,
    converts them to GameTeX format, and saves to .tex files.
    """
    # Load and convert ingredients
    if ingredients_file:
        print(f"Loading ingredients from {ingredients_file}...")
        ingredients = load_ingredients(ingredients_file)
        print(f"Converting {len(ingredients)} ingredients...")
        ingredients_latex = convert_ingredients(ingredients)

        with open("ingredients.tex", "w", encoding="utf-8") as f:
            f.write(ingredients_latex)
        print("Saved ingredients.tex")

    # Load and convert products
    if products_file:
        print(f"Loading products from {products_file}...")
        products = load_products(products_file)
        print(f"Converting {len(products)} products...")
        products_latex = convert_products(products)

        with open("products.tex", "w", encoding="utf-8") as f:
            f.write(products_latex)
        print("Saved products.tex")

    print("LaTeX export complete!")


def _escape_latex(text: str) -> str:
    """
    Escape special LaTeX characters in text.
    """
    if not text:
        return ""

    # Characters that need escaping in LaTeX
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("$", "\\$"),
        ("&", "\\&"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("%", "\\%"),
        ("^", "\\textasciicircum{}"),
        ("~", "\\textasciitilde{}"),
    ]

    result = text
    for old, new in replacements:
        result = result.replace(old, new)

    return result


if __name__ == "__main__":
    convert_to_latex()
