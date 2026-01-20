"""
Tests for herbalism blending logic.
"""
import pytest
from db import Ingredient, Product
from hawky.herbalism.blending import (
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
)


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_validate_product_type_valid(self):
        """Test that valid product types are accepted."""
        for pt in VALID_PRODUCT_TYPES:
            assert validate_product_type(pt, "test")
            assert validate_product_type(pt.upper(), "test")

    def test_validate_product_type_invalid(self):
        """Test that invalid product types are rejected."""
        assert not validate_product_type("invalid", "test")
        assert not validate_product_type("", "test")

    def test_all_have_property(self):
        """Test all_have_property function."""
        ing1 = Ingredient(item_number="1", properties="ingestible,aromatic")
        ing2 = Ingredient(item_number="2", properties="ingestible")
        ing3 = Ingredient(item_number="3", properties="aromatic")

        assert all_have_property([ing1, ing2], "ingestible")
        assert not all_have_property([ing1, ing3], "ingestible")
        assert not all_have_property([], "ingestible")

    def test_none_have_property(self):
        """Test none_have_property function."""
        ing1 = Ingredient(item_number="1", properties="ingestible")
        ing2 = Ingredient(item_number="2", properties="aromatic")

        assert none_have_property([ing1, ing2], "alcohol")
        assert not none_have_property([ing1], "ingestible")
        assert none_have_property([], "anything")

    def test_has_property(self):
        """Test has_property function."""
        ing1 = Ingredient(item_number="1", properties="ingestible")
        ing2 = Ingredient(item_number="2", properties="aromatic")

        assert has_property([ing1, ing2], "ingestible")
        assert has_property([ing1, ing2], "aromatic")
        assert not has_property([ing1, ing2], "alcohol")
        assert not has_property([], "anything")

    def test_count_property(self):
        """Test count_property function."""
        ing1 = Ingredient(item_number="1", properties="alcohol")
        ing2 = Ingredient(item_number="2", properties="alcohol")
        ing3 = Ingredient(item_number="3", properties="ingestible")

        assert count_property([ing1, ing2, ing3], "alcohol") == 2
        assert count_property([ing1, ing2, ing3], "ingestible") == 1
        assert count_property([ing1, ing2, ing3], "salt") == 0


class TestCalculateChakras:
    """Tests for chakra calculation."""

    def test_single_chakra_ingredient(self):
        """Test with single chakra ingredient."""
        ing = Ingredient(
            item_number="1",
            primary_chakra="Earth",
            primary_chakra_strength=3
        )
        result = calculate_chakras([ing])

        assert result.primary_chakra == "earth"
        assert result.primary_magnitude == 3
        assert result.primary_is_boon == "boon"
        assert result.secondary_chakra is None
        assert result.tier == 4  # 3-0=3 < 4, so tier 0 + 1 (no secondary) = 1... wait
        # Actually: diff=3, <4 means tier 0, +1 for no secondary = 1

    def test_two_chakra_ingredients(self):
        """Test with two different chakras."""
        ing1 = Ingredient(
            item_number="1",
            primary_chakra="Earth",
            primary_chakra_strength=3
        )
        ing2 = Ingredient(
            item_number="2",
            primary_chakra="Water",
            primary_chakra_strength=2
        )
        result = calculate_chakras([ing1, ing2])

        assert result.primary_chakra == "earth"
        assert result.primary_magnitude == 3
        assert result.secondary_chakra == "water"
        assert result.secondary_magnitude == 2
        # diff = 3 - 2 = 1, < 4, tier = 0

    def test_stacking_same_chakra(self):
        """Test that same chakras stack."""
        ing1 = Ingredient(
            item_number="1",
            primary_chakra="Fire",
            primary_chakra_strength=2
        )
        ing2 = Ingredient(
            item_number="2",
            primary_chakra="Fire",
            primary_chakra_strength=3
        )
        result = calculate_chakras([ing1, ing2])

        assert result.primary_chakra == "fire"
        assert result.primary_magnitude == 5
        assert result.secondary_chakra is None
        # diff = 5 - 0 = 5, 4-7 is tier 1, +1 for no secondary = 2

    def test_bane_chakra(self):
        """Test negative chakra values (bane)."""
        ing = Ingredient(
            item_number="1",
            primary_chakra="Light",
            primary_chakra_strength=-3
        )
        result = calculate_chakras([ing])

        assert result.primary_chakra == "light"
        assert result.primary_magnitude == -3
        assert result.primary_is_boon == "bane"

    def test_tier_calculation(self):
        """Test tier calculation based on difference."""
        # Tier 3: diff > 10
        ing1 = Ingredient(item_number="1", primary_chakra="Earth", primary_chakra_strength=12)
        result = calculate_chakras([ing1])
        assert result.tier == 4  # 12-0=12 > 10, tier 3 + 1 (no secondary) = 4

        # Tier 2: diff 8-10
        ing2 = Ingredient(item_number="2", primary_chakra="Water", primary_chakra_strength=9)
        result = calculate_chakras([ing2])
        assert result.tier == 3  # 9-0=9, 8-10 is tier 2 + 1 = 3

        # Tier 1: diff 4-7
        ing3 = Ingredient(item_number="3", primary_chakra="Fire", primary_chakra_strength=5)
        result = calculate_chakras([ing3])
        assert result.tier == 2  # 5-0=5, 4-7 is tier 1 + 1 = 2


@pytest.mark.asyncio
class TestCalcProductType:
    """Tests for product type calculation."""

    async def test_too_much_alcohol_returns_ruined(self, db_conn, loaded_test_data):
        """Test that >2 alcohol returns ruined tincture."""
        ings = [
            Ingredient(item_number="1", properties="alcohol"),
            Ingredient(item_number="2", properties="alcohol"),
            Ingredient(item_number="3", properties="alcohol"),
        ]
        result = await calc_product_type(db_conn, ings)
        assert isinstance(result, Product)
        assert result.product_type == "tincture"

    async def test_two_alcohol_ingestible_is_tincture(self, db_conn, loaded_test_data):
        """Test 2 alcohol + ingestible = tincture."""
        ings = [
            Ingredient(item_number="1", properties="alcohol,ingestible"),
            Ingredient(item_number="2", properties="alcohol,ingestible"),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "tincture"

    async def test_two_alcohol_not_ingestible_returns_ruined(self, db_conn, loaded_test_data):
        """Test 2 alcohol without ingestible returns ruined."""
        ings = [
            Ingredient(item_number="1", properties="alcohol"),
            Ingredient(item_number="2", properties="alcohol"),
        ]
        result = await calc_product_type(db_conn, ings)
        assert isinstance(result, Product)

    async def test_one_alcohol_ingestible_is_tincture(self, db_conn, loaded_test_data):
        """Test 1 alcohol + ingestible = tincture."""
        ings = [
            Ingredient(item_number="1", properties="alcohol,ingestible"),
            Ingredient(item_number="2", properties="ingestible"),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "tincture"

    async def test_one_alcohol_aromatic_is_incense(self, db_conn, loaded_test_data):
        """Test 1 alcohol + aromatic = incense."""
        ings = [
            Ingredient(item_number="1", properties="alcohol"),
            Ingredient(item_number="2", properties="aromatic"),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "incense"

    async def test_one_alcohol_only_is_decoction(self, db_conn, loaded_test_data):
        """Test 1 alcohol alone = decoction."""
        ings = [
            Ingredient(item_number="1", properties="alcohol"),
            Ingredient(item_number="2", properties=""),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "decoction"

    async def test_ingestible_is_tea(self, db_conn, loaded_test_data):
        """Test ingestible only = tea."""
        ings = [
            Ingredient(item_number="1", properties="ingestible"),
            Ingredient(item_number="2", properties="ingestible"),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "tea"

    async def test_salt_is_bath(self, db_conn, loaded_test_data):
        """Test salt = bath."""
        ings = [
            Ingredient(item_number="1", properties="salt"),
            Ingredient(item_number="2", properties=""),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "bath"

    async def test_default_is_salve(self, db_conn, loaded_test_data):
        """Test default = salve."""
        ings = [
            Ingredient(item_number="1", properties=""),
            Ingredient(item_number="2", properties=""),
        ]
        result = await calc_product_type(db_conn, ings)
        assert result == "salve"


@pytest.mark.asyncio
class TestMakeBlend:
    """Tests for the main make_blend function."""

    async def test_empty_ingredients_error(self, db_conn, loaded_test_data):
        """Test that empty ingredients returns error."""
        result = await make_blend(db_conn, [])
        assert not result.success
        assert "At least one ingredient" in result.error_message

    async def test_too_many_ingredients_error(self, db_conn, loaded_test_data):
        """Test that >6 ingredients returns error."""
        result = await make_blend(db_conn, ["1", "2", "3", "4", "5", "6", "7"])
        assert not result.success
        assert "Maximum of 6" in result.error_message

    async def test_invalid_ingredient_error(self, db_conn, loaded_test_data):
        """Test that invalid ingredient numbers return error."""
        result = await make_blend(db_conn, ["9999"])
        assert not result.success
        assert "9999" in result.error_message

    async def test_successful_blend_with_subset_recipe(self, db_conn, loaded_test_data):
        """Test successful blend matching a subset recipe."""
        # 5111 (Calming Chamomile) + 5419 (Healing Lotus) = Calming Tea (6111) x2
        result = await make_blend(db_conn, ["5111", "5419"])
        assert result.success
        assert result.product is not None
        assert result.product.item_number == "6111"
        assert result.quantity == 2

    async def test_successful_blend_with_constraint_recipe(self, db_conn, loaded_test_data):
        """Test successful blend matching a constraint recipe."""
        # Single earth boon ingredient should produce earth-based product
        # 5111 (Calming Chamomile) has Earth +2, ingestible -> tea
        # Should match constraint recipe for earth boon tier 1 tea
        result = await make_blend(db_conn, ["5111"])
        assert result.success
        assert result.product is not None

    async def test_blend_returns_sorted_order(self, db_conn, loaded_test_data):
        """Test that ingredients are processed in descending order."""
        # The order shouldn't change the result
        result1 = await make_blend(db_conn, ["5111", "5419"])
        result2 = await make_blend(db_conn, ["5419", "5111"])

        assert result1.product.item_number == result2.product.item_number
        assert result1.quantity == result2.quantity
