"""
Herbalism module for Hawky bot.
Provides herb blending functionality for creating herbal products.
"""

from .blending import (
    BlendResult,
    ChakraResult,
    validate_product_type,
    all_have_property,
    none_have_property,
    has_property,
    count_property,
    calculate_chakras,
    calc_product_type,
    calc_product,
    make_blend,
    VALID_PRODUCT_TYPES,
    SLUDGE_ITEM_NUMBER,
)
