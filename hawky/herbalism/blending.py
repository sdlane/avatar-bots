"""
Core blending logic for the herbalism system.
"""

import asyncpg
from dataclasses import dataclass
from typing import Optional, List, Tuple, Union
import logging

from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend

logger = logging.getLogger(__name__)

# Valid product types
VALID_PRODUCT_TYPES = {"tea", "salve", "tincture", "decoction", "bath", "incense"}

# Default sludge item number (fallback when no failed blend is found)
SLUDGE_ITEM_NUMBER = "6000"


@dataclass
class BlendResult:
    """Result of a blend operation."""
    success: bool
    product: Optional[Product] = None
    quantity: int = 1
    error_message: Optional[str] = None


@dataclass
class ChakraResult:
    """Result of chakra calculation."""
    primary_chakra: Optional[str] = None
    primary_magnitude: int = 0
    primary_is_boon: Optional[str] = None  # "boon" or "bane"
    secondary_chakra: Optional[str] = None
    secondary_magnitude: int = 0
    secondary_is_boon: Optional[str] = None  # "boon" or "bane"
    tier: int = 0


def validate_product_type(product_type: str, caller: str) -> bool:
    """
    Validate that the product type is valid.
    Logs an error if invalid.
    """
    if product_type.lower() not in VALID_PRODUCT_TYPES:
        logger.error(f"{caller}: Invalid product type '{product_type}'")
        return False
    return True


def all_have_property(ingredients: List[Ingredient], property_name: str) -> bool:
    """
    Check if all ingredients have the specified property.
    """
    if not ingredients:
        return False
    return all(ing.has_property(property_name) for ing in ingredients)


def none_have_property(ingredients: List[Ingredient], property_name: str) -> bool:
    """
    Check if none of the ingredients have the specified property.
    """
    if not ingredients:
        return True
    return not any(ing.has_property(property_name) for ing in ingredients)


def has_property(ingredients: List[Ingredient], property_name: str) -> bool:
    """
    Check if at least one ingredient has the specified property.
    """
    if not ingredients:
        return False
    return any(ing.has_property(property_name) for ing in ingredients)


def count_property(ingredients: List[Ingredient], property_name: str) -> int:
    """
    Count how many ingredients have the specified property.
    """
    return sum(1 for ing in ingredients if ing.has_property(property_name))


async def fetch_ruined_product(conn: asyncpg.Connection, product_type: str) -> Product:
    """
    Fetch the ruined product for a given product type.
    Falls back to sludge if not found.
    """
    if not validate_product_type(product_type, "fetch_ruined_product"):
        return await _get_sludge(conn)

    failed_blend = await FailedBlend.fetch_by_type(conn, product_type.lower())
    if failed_blend is None:
        logger.error(f"fetch_ruined_product: No failed blend found for type '{product_type}'")
        return await _get_sludge(conn)

    product = await Product.fetch_by_item_number(conn, failed_blend.product_item_number)
    if product is None:
        logger.error(f"fetch_ruined_product: Product '{failed_blend.product_item_number}' not found")
        return await _get_sludge(conn)

    return product


async def _get_sludge(conn: asyncpg.Connection) -> Product:
    """
    Get the sludge product as a fallback.
    """
    product = await Product.fetch_by_item_number(conn, SLUDGE_ITEM_NUMBER)
    if product is None:
        # Create a default sludge product if it doesn't exist
        return Product(
            item_number=SLUDGE_ITEM_NUMBER,
            name="Sludge",
            product_type="salve",
            flavor_text="A goopy, unpleasant mess.",
            rules_text="This blend has failed. It has no useful properties."
        )
    return product


def calculate_chakras(ingredients: List[Ingredient]) -> ChakraResult:
    """
    Calculate the primary and secondary chakras and tier from ingredients.

    Rules:
    - Total positive and negative values for each chakra
    - Primary = highest magnitude chakra
    - Secondary = second highest magnitude chakra
    - Tier based on difference: >10=T3, 8-10=T2, 4-7=T1, <4=T0
    - No secondary adds +1 tier
    """
    if not ingredients:
        return ChakraResult()

    # Track totals for each chakra (positive and negative combined = net value)
    chakra_totals: dict = {}

    for ing in ingredients:
        # Primary chakra
        if ing.primary_chakra and ing.primary_chakra_strength is not None:
            chakra = ing.primary_chakra.lower()
            if chakra not in chakra_totals:
                chakra_totals[chakra] = 0
            chakra_totals[chakra] += ing.primary_chakra_strength

        # Secondary chakra
        if ing.secondary_chakra and ing.secondary_chakra_strength is not None:
            chakra = ing.secondary_chakra.lower()
            if chakra not in chakra_totals:
                chakra_totals[chakra] = 0
            chakra_totals[chakra] += ing.secondary_chakra_strength

    if not chakra_totals:
        return ChakraResult()

    # Sort chakras by absolute magnitude
    sorted_chakras = sorted(
        chakra_totals.items(),
        key=lambda x: abs(x[1]),
        reverse=True
    )

    result = ChakraResult()

    # Primary chakra (highest magnitude)
    if len(sorted_chakras) >= 1:
        result.primary_chakra = sorted_chakras[0][0]
        result.primary_magnitude = sorted_chakras[0][1]
        result.primary_is_boon = "boon" if sorted_chakras[0][1] > 0 else "bane"

    # Secondary chakra (second highest magnitude)
    if len(sorted_chakras) >= 2:
        result.secondary_chakra = sorted_chakras[1][0]
        result.secondary_magnitude = sorted_chakras[1][1]
        result.secondary_is_boon = "boon" if sorted_chakras[1][1] > 0 else "bane"

    # Calculate tier based on difference between primary and secondary magnitudes
    primary_abs = abs(result.primary_magnitude)
    secondary_abs = abs(result.secondary_magnitude) if result.secondary_chakra else 0
    diff = primary_abs - secondary_abs

    if diff > 10:
        result.tier = 3
    elif 8 <= diff <= 10:
        result.tier = 2
    elif 4 <= diff <= 7:
        result.tier = 1
    else:
        result.tier = 0

    # No secondary chakra adds +1 tier
    if result.secondary_chakra is None:
        result.tier += 1

    return result


async def calc_product_type(
    conn: asyncpg.Connection,
    ingredients: List[Ingredient]
) -> Union[Product, str]:
    """
    Determine the product type based on ingredients.

    Rules:
    - >2 alcohol -> ruined tincture
    - 2 alcohol + ingestible -> "tincture"
    - 2 alcohol (not ingestible) -> ruined tincture
    - 1 alcohol + ingestible -> "tincture"
    - 1 alcohol + aromatic -> "incense"
    - 1 alcohol -> "decoction"
    - ingestible -> "tea"
    - salt -> "bath"
    - default -> "salve"

    Returns either a Product (for ruined products) or a string (product type).
    """
    alcohol_count = count_property(ingredients, "alcohol")
    is_ingestible = all_have_property(ingredients, "ingestible")
    has_aromatic = has_property(ingredients, "aromatic")
    has_salt = has_property(ingredients, "salt")

    if alcohol_count > 2:
        # Too much alcohol - ruined tincture
        return await fetch_ruined_product(conn, "tincture")

    if alcohol_count == 2:
        if is_ingestible:
            return "tincture"
        else:
            # Not ingestible with 2 alcohol - ruined tincture
            return await fetch_ruined_product(conn, "tincture")

    if alcohol_count == 1:
        if is_ingestible:
            return "tincture"
        elif has_aromatic:
            return "incense"
        else:
            return "decoction"

    # No alcohol
    if is_ingestible:
        return "tea"
    elif has_salt:
        return "bath"
    else:
        return "salve"


async def calc_product(
    conn: asyncpg.Connection,
    product_type: str,
    ingredients: List[Ingredient]
) -> Tuple[Product, int]:
    """
    Calculate the resulting product based on product type and ingredients.

    Rules:
    1. Check SubsetRecipes (largest subset match wins)
    2. Calculate chakras/tier
    3. If tier is 0, return ruined product
    4. Check ConstraintRecipes (FIFO order)
    5. Return ruined product on no match

    Returns (Product, quantity).
    """
    # Get ingredient item numbers
    ingredient_numbers = [ing.item_number for ing in ingredients]

    # Check for subset recipe matches
    subset_recipes = await SubsetRecipe.fetch_matching_subsets(
        conn, ingredient_numbers, product_type.lower()
    )
    if subset_recipes:
        # First match is the largest subset (already sorted)
        best_recipe = subset_recipes[0]
        product = await Product.fetch_by_item_number(conn, best_recipe.product_item_number)
        if product:
            return (product, best_recipe.quantity_produced)
        else:
            logger.error(f"calc_product: Product '{best_recipe.product_item_number}' not found")

    # Calculate chakras and tier
    chakra_result = calculate_chakras(ingredients)

    # If tier is 0, return ruined product
    if chakra_result.tier == 0:
        ruined = await fetch_ruined_product(conn, product_type)
        return (ruined, 1)

    # Check constraint recipes
    constraint_recipes = await ConstraintRecipe.fetch_matching(
        conn,
        product_type.lower(),
        ingredient_numbers,
        chakra_result.primary_chakra,
        chakra_result.primary_is_boon,
        chakra_result.secondary_chakra,
        chakra_result.secondary_is_boon,
        chakra_result.tier
    )

    if not constraint_recipes:
        # No matching constraint recipe
        ruined = await fetch_ruined_product(conn, product_type)
        return (ruined, 1)

    # First matching recipe (FIFO order)
    best_recipe = constraint_recipes[0]
    product = await Product.fetch_by_item_number(conn, best_recipe.product_item_number)
    if product:
        return (product, best_recipe.quantity_produced)
    else:
        logger.error(f"calc_product: Product '{best_recipe.product_item_number}' not found")
        ruined = await fetch_ruined_product(conn, product_type)
        return (ruined, 1)


async def make_blend(
    conn: asyncpg.Connection,
    ingredient_numbers: List[str]
) -> BlendResult:
    """
    Main entry point for creating a blend.

    Input: List of ingredient item numbers (1-6 items)
    Output: BlendResult with success/failure, product, quantity, or error message
    """
    # Validate input count
    if not ingredient_numbers or len(ingredient_numbers) == 0:
        return BlendResult(
            success=False,
            error_message="At least one ingredient is required."
        )

    if len(ingredient_numbers) > 6:
        return BlendResult(
            success=False,
            error_message="Maximum of 6 ingredients allowed."
        )

    # Sort ingredients descending
    sorted_numbers = sorted(ingredient_numbers, reverse=True)

    # Fetch ingredients from database
    ingredients: List[Ingredient] = []
    invalid_numbers: List[str] = []

    for num in sorted_numbers:
        ing = await Ingredient.fetch_by_item_number(conn, num)
        if ing is None:
            invalid_numbers.append(num)
        else:
            ingredients.append(ing)

    # Report invalid item numbers
    if invalid_numbers:
        return BlendResult(
            success=False,
            error_message=f"The following item numbers cannot be used for herbalism: {', '.join(invalid_numbers)}"
        )

    # Calculate product type
    product_type_result = await calc_product_type(conn, ingredients)

    # If calc_product_type returned a Product (ruined), use it directly
    if isinstance(product_type_result, Product):
        return BlendResult(
            success=True,
            product=product_type_result,
            quantity=1
        )

    # Otherwise, calculate the final product
    product, quantity = await calc_product(conn, product_type_result, ingredients)

    return BlendResult(
        success=True,
        product=product,
        quantity=quantity
    )
