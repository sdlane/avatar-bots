"""
Tests for herbalism database models.
"""
import pytest
from db import Ingredient, Product, SubsetRecipe, ConstraintRecipe, FailedBlend


@pytest.mark.asyncio
async def test_ingredient_upsert_and_fetch(db_conn, clean_herbalism_data):
    """Test inserting and fetching an ingredient."""
    ingredient = Ingredient(
        item_number="5999",
        name="Test Herb",
        macro="TestHerb",
        rarity="Common",
        primary_chakra="Earth",
        primary_chakra_strength=2,
        properties="ingestible,aromatic",
        flavor_text="A test herb.",
        rules_text="Does test things."
    )
    await ingredient.upsert(db_conn)

    fetched = await Ingredient.fetch_by_item_number(db_conn, "5999")
    assert fetched is not None
    assert fetched.name == "Test Herb"
    assert fetched.primary_chakra == "Earth"
    assert fetched.primary_chakra_strength == 2


@pytest.mark.asyncio
async def test_ingredient_has_property(db_conn, clean_herbalism_data):
    """Test ingredient property checking."""
    ingredient = Ingredient(
        item_number="5998",
        name="Prop Test",
        properties="alcohol,ingestible,aromatic"
    )
    await ingredient.upsert(db_conn)

    fetched = await Ingredient.fetch_by_item_number(db_conn, "5998")
    assert fetched.has_property("alcohol")
    assert fetched.has_property("Ingestible")  # case insensitive
    assert fetched.has_property("aromatic")
    assert not fetched.has_property("salt")


@pytest.mark.asyncio
async def test_ingredient_get_properties_list(db_conn, clean_herbalism_data):
    """Test getting properties as a list."""
    ingredient = Ingredient(
        item_number="5997",
        name="List Test",
        properties="a, b, c"
    )
    props = ingredient.get_properties_list()
    assert len(props) == 3
    assert "a" in props
    assert "b" in props
    assert "c" in props


@pytest.mark.asyncio
async def test_product_upsert_and_fetch(db_conn, clean_herbalism_data):
    """Test inserting and fetching a product."""
    product = Product(
        item_number="6999",
        name="Test Tea",
        macro="TestTea",
        product_type="tea",
        flavor_text="A test tea.",
        rules_text="Drink to test."
    )
    await product.upsert(db_conn)

    fetched = await Product.fetch_by_item_number(db_conn, "6999")
    assert fetched is not None
    assert fetched.name == "Test Tea"
    assert fetched.product_type == "tea"


@pytest.mark.asyncio
async def test_product_fetch_by_type(db_conn, clean_herbalism_data):
    """Test fetching products by type."""
    await Product(item_number="6991", product_type="tea").upsert(db_conn)
    await Product(item_number="6992", product_type="tea").upsert(db_conn)
    await Product(item_number="6993", product_type="salve").upsert(db_conn)

    teas = await Product.fetch_by_type(db_conn, "tea")
    assert len(teas) == 2

    salves = await Product.fetch_by_type(db_conn, "salve")
    assert len(salves) == 1


@pytest.mark.asyncio
async def test_subset_recipe_matching(db_conn, clean_herbalism_data):
    """Test subset recipe matching."""
    recipe = SubsetRecipe(
        product_item_number="6111",
        product_type="tea",
        quantity_produced=2,
        ingredients=["5111", "5211"]
    )
    await recipe.upsert(db_conn)

    # Should match when all recipe ingredients are present
    matches = await SubsetRecipe.fetch_matching_subsets(
        db_conn, ["5111", "5211", "5312"], "tea"
    )
    assert len(matches) == 1
    assert matches[0].quantity_produced == 2

    # Should not match different product type
    matches = await SubsetRecipe.fetch_matching_subsets(
        db_conn, ["5111", "5211"], "salve"
    )
    assert len(matches) == 0

    # Should not match if missing ingredient
    matches = await SubsetRecipe.fetch_matching_subsets(
        db_conn, ["5111"], "tea"
    )
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_constraint_recipe_matching(db_conn, clean_herbalism_data):
    """Test constraint recipe matching."""
    recipe = ConstraintRecipe(
        product_item_number="6111",
        product_type="tea",
        primary_chakra="earth",
        primary_is_boon="boon",
        tier=1
    )
    await recipe.insert(db_conn)

    # Should match with correct constraints
    matches = await ConstraintRecipe.fetch_matching(
        db_conn, "tea", [],
        primary_chakra="earth", primary_is_boon="boon",
        secondary_chakra=None, secondary_is_boon=None,
        tier=1
    )
    assert len(matches) == 1

    # Should not match wrong tier
    matches = await ConstraintRecipe.fetch_matching(
        db_conn, "tea", [],
        primary_chakra="earth", primary_is_boon="boon",
        secondary_chakra=None, secondary_is_boon=None,
        tier=2
    )
    assert len(matches) == 0

    # Should not match wrong chakra
    matches = await ConstraintRecipe.fetch_matching(
        db_conn, "tea", [],
        primary_chakra="fire", primary_is_boon="boon",
        secondary_chakra=None, secondary_is_boon=None,
        tier=1
    )
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_constraint_recipe_wildcard_matching(db_conn, clean_herbalism_data):
    """Test constraint recipe with wildcard ingredients."""
    recipe = ConstraintRecipe(
        product_item_number="6111",
        product_type="tea",
        ingredients=["51*1"],  # Matches 5101, 5111, 5121, etc.
        tier=1
    )
    await recipe.insert(db_conn)

    # Should match 5111
    matches = await ConstraintRecipe.fetch_matching(
        db_conn, "tea", ["5111"],
        primary_chakra=None, primary_is_boon=None,
        secondary_chakra=None, secondary_is_boon=None,
        tier=1
    )
    assert len(matches) == 1

    # Should match 5121
    matches = await ConstraintRecipe.fetch_matching(
        db_conn, "tea", ["5121"],
        primary_chakra=None, primary_is_boon=None,
        secondary_chakra=None, secondary_is_boon=None,
        tier=1
    )
    assert len(matches) == 1

    # Should not match 5112 (wrong last digit)
    matches = await ConstraintRecipe.fetch_matching(
        db_conn, "tea", ["5112"],
        primary_chakra=None, primary_is_boon=None,
        secondary_chakra=None, secondary_is_boon=None,
        tier=1
    )
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_failed_blend_upsert_and_fetch(db_conn, clean_herbalism_data):
    """Test inserting and fetching failed blends."""
    fb = FailedBlend(
        product_item_number="6001",
        product_type="tea"
    )
    await fb.upsert(db_conn)

    fetched = await FailedBlend.fetch_by_type(db_conn, "tea")
    assert fetched is not None
    assert fetched.product_item_number == "6001"


@pytest.mark.asyncio
async def test_delete_all_models(db_conn, clean_herbalism_data):
    """Test deleting all entries for each model."""
    # Insert some data
    await Ingredient(item_number="5999", name="Test").upsert(db_conn)
    await Product(item_number="6999").upsert(db_conn)
    await SubsetRecipe(product_item_number="6999", product_type="tea", ingredients=["5999"]).upsert(db_conn)
    await ConstraintRecipe(product_item_number="6999", product_type="tea").insert(db_conn)
    await FailedBlend(product_item_number="6999", product_type="test").upsert(db_conn)

    # Verify data exists
    assert await Ingredient.fetch_by_item_number(db_conn, "5999") is not None
    assert await Product.fetch_by_item_number(db_conn, "6999") is not None
    assert len(await SubsetRecipe.fetch_all(db_conn)) >= 1
    assert len(await ConstraintRecipe.fetch_all(db_conn)) >= 1
    assert len(await FailedBlend.fetch_all(db_conn)) >= 1

    # Delete all
    await ConstraintRecipe.delete_all(db_conn)
    await SubsetRecipe.delete_all(db_conn)
    await FailedBlend.delete_all(db_conn)
    await Product.delete_all(db_conn)
    await Ingredient.delete_all(db_conn)

    # Verify deleted
    assert await Ingredient.fetch_by_item_number(db_conn, "5999") is None
    assert await Product.fetch_by_item_number(db_conn, "6999") is None
    assert len(await SubsetRecipe.fetch_all(db_conn)) == 0
    assert len(await ConstraintRecipe.fetch_all(db_conn)) == 0
    assert len(await FailedBlend.fetch_all(db_conn)) == 0
