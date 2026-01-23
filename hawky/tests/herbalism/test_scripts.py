"""
Tests for herbalism scripts (loaders and clear functions).
"""
import pytest
from pathlib import Path
from hawky.herbalism.loaders import (
    load_ingredients,
    load_products,
    validate_products_unique,
    load_subset_recipes,
    load_constraint_recipes,
    load_failed_blends,
)
from hawky.herbalism.clear_data import (
    clear_herbal_data,
    clear_ingredients,
    clear_products,
    clear_subset_recipes,
    clear_constraint_recipes,
    clear_failed_blends,
)
from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend

# Path to test data
TEST_DATA_DIR = Path(__file__).parent.parent.parent / "herbalism" / "test_data"


class TestLoaders:
    """Tests for CSV loading functions."""

    def test_load_ingredients(self):
        """Test loading ingredients from CSV."""
        ingredients = load_ingredients(str(TEST_DATA_DIR / "test_ingredients.csv"))

        assert len(ingredients) > 0

        # Check a specific ingredient
        chamomile = next((i for i in ingredients if i.item_number == "5111"), None)
        assert chamomile is not None
        assert chamomile.name == "Calming Chamomile"
        assert chamomile.primary_chakra == "Earth"
        assert chamomile.primary_chakra_strength == 2
        assert chamomile.has_property("ingestible")

    def test_load_products(self):
        """Test loading products from CSV."""
        products = load_products(str(TEST_DATA_DIR / "test_products.csv"))

        assert len(products) > 0

        # Check sludge product
        sludge = next((p for p in products if p.item_number == "6000"), None)
        assert sludge is not None
        assert sludge.name == "Sludge"
        assert sludge.product_type == "salve"

    def test_validate_products_unique_no_duplicates(self):
        """Test validation passes when all products are unique."""
        products = [
            Product(item_number="001", product_type="tea"),
            Product(item_number="002", product_type="tea"),
            Product(item_number="001", product_type="salve"),  # same item_number, different type
        ]
        valid, error_msg = validate_products_unique(products)
        assert valid is True
        assert error_msg == ""

    def test_validate_products_unique_with_duplicates(self):
        """Test validation fails when duplicate (product_type, item_number) pairs exist."""
        products = [
            Product(item_number="001", product_type="tea"),
            Product(item_number="002", product_type="tea"),
            Product(item_number="001", product_type="tea"),  # duplicate
        ]
        valid, error_msg = validate_products_unique(products)
        assert valid is False
        assert "Duplicate products found" in error_msg
        assert "('tea', '001')" in error_msg
        assert "rows 2 and 4" in error_msg  # first at index 0 (row 2), dup at index 2 (row 4)

    def test_validate_products_unique_multiple_duplicates(self):
        """Test validation reports all duplicates."""
        products = [
            Product(item_number="001", product_type="tea"),
            Product(item_number="001", product_type="tea"),  # first dup
            Product(item_number="002", product_type="salve"),
            Product(item_number="002", product_type="salve"),  # second dup
        ]
        valid, error_msg = validate_products_unique(products)
        assert valid is False
        assert "('tea', '001')" in error_msg
        assert "('salve', '002')" in error_msg

    def test_load_subset_recipes(self):
        """Test loading subset recipes from CSV."""
        recipes = load_subset_recipes(str(TEST_DATA_DIR / "test_subset_recipes.csv"))

        assert len(recipes) > 0

        # Check that ingredients are sorted descending
        for recipe in recipes:
            sorted_ings = sorted(recipe.ingredients, reverse=True)
            assert recipe.ingredients == sorted_ings

    def test_load_constraint_recipes(self):
        """Test loading constraint recipes from CSV."""
        recipes = load_constraint_recipes(str(TEST_DATA_DIR / "test_constraint_recipes.csv"))

        assert len(recipes) > 0

        # Check a specific recipe
        earth_tea = next((r for r in recipes if r.product_item_number == "6111" and r.product_type == "tea"), None)
        assert earth_tea is not None
        assert earth_tea.primary_chakra == "earth"
        assert earth_tea.primary_is_boon == "boon"
        assert earth_tea.tier == 1

    def test_load_failed_blends(self):
        """Test loading failed blends from CSV."""
        failed_blends = load_failed_blends(str(TEST_DATA_DIR / "test_failed_blends.csv"))

        assert len(failed_blends) > 0

        # Check that all product types are covered
        types = {fb.product_type for fb in failed_blends}
        assert "tea" in types
        assert "salve" in types
        assert "tincture" in types


@pytest.mark.asyncio
class TestClearFunctions:
    """Tests for clear data functions."""

    async def test_clear_ingredients(self, db_conn, clean_herbalism_data):
        """Test clearing ingredients."""
        await Ingredient(item_number="test1", name="Test").upsert(db_conn)
        assert await Ingredient.fetch_by_item_number(db_conn, "test1") is not None

        await clear_ingredients(db_conn)
        assert await Ingredient.fetch_by_item_number(db_conn, "test1") is None

    async def test_clear_products(self, db_conn, clean_herbalism_data):
        """Test clearing products."""
        await Product(item_number="test1").upsert(db_conn)
        assert await Product.fetch_by_item_number(db_conn, "test1") is not None

        await clear_products(db_conn)
        assert await Product.fetch_by_item_number(db_conn, "test1") is None

    async def test_clear_subset_recipes(self, db_conn, clean_herbalism_data):
        """Test clearing subset recipes."""
        await SubsetRecipe(
            product_item_number="test1",
            product_type="tea",
            ingredients=["5111"]
        ).upsert(db_conn)
        assert len(await SubsetRecipe.fetch_all(db_conn)) > 0

        await clear_subset_recipes(db_conn)
        assert len(await SubsetRecipe.fetch_all(db_conn)) == 0

    async def test_clear_constraint_recipes(self, db_conn, clean_herbalism_data):
        """Test clearing constraint recipes."""
        await ConstraintRecipe(
            product_item_number="test1",
            product_type="tea"
        ).insert(db_conn)
        assert len(await ConstraintRecipe.fetch_all(db_conn)) > 0

        await clear_constraint_recipes(db_conn)
        assert len(await ConstraintRecipe.fetch_all(db_conn)) == 0

    async def test_clear_failed_blends(self, db_conn, clean_herbalism_data):
        """Test clearing failed blends."""
        await FailedBlend(
            product_item_number="test1",
            product_type="test"
        ).upsert(db_conn)
        assert len(await FailedBlend.fetch_all(db_conn)) > 0

        await clear_failed_blends(db_conn)
        assert len(await FailedBlend.fetch_all(db_conn)) == 0

    async def test_clear_herbal_data(self, db_conn, clean_herbalism_data):
        """Test clearing all herbal data."""
        # Insert some data
        await Ingredient(item_number="test1", name="Test").upsert(db_conn)
        await Product(item_number="test2").upsert(db_conn)
        await SubsetRecipe(product_item_number="test2", product_type="tea", ingredients=["test1"]).upsert(db_conn)
        await ConstraintRecipe(product_item_number="test2", product_type="tea").insert(db_conn)
        await FailedBlend(product_item_number="test2", product_type="test").upsert(db_conn)

        # Clear all
        await clear_herbal_data(db_conn)

        # Verify all cleared
        assert await Ingredient.fetch_by_item_number(db_conn, "test1") is None
        assert await Product.fetch_by_item_number(db_conn, "test2") is None
        assert len(await SubsetRecipe.fetch_all(db_conn)) == 0
        assert len(await ConstraintRecipe.fetch_all(db_conn)) == 0
        assert len(await FailedBlend.fetch_all(db_conn)) == 0
