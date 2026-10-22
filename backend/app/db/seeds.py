"""Standard Food Taxonomy and Initial Data Seeder."""

from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.category import Category, PerishabilityTier, StorageRequirement

STANDARD_CATEGORIES: List[Dict[str, Any]] = [
    {
        "id": "cat_dairy_eggs",
        "name": "Dairy & Eggs",
        "slug": "dairy-and-eggs",
        "perishability_tier": PerishabilityTier.HIGH.value,
        "recommended_storage": StorageRequirement.REFRIGERATED.value,
        "temp_min_celsius": 2.0,
        "temp_max_celsius": 4.0,
        "humidity_min_pct": None,
        "humidity_max_pct": None,
        "default_shelf_life_days": 14,
        "description": "Milk, butter, fresh yogurt, cream, pasteurized liquid and whole eggs.",
    },
    {
        "id": "cat_meat_poultry",
        "name": "Fresh Meat & Poultry",
        "slug": "fresh-meat-and-poultry",
        "perishability_tier": PerishabilityTier.CRITICAL.value,
        "recommended_storage": StorageRequirement.REFRIGERATED.value,
        "temp_min_celsius": 0.0,
        "temp_max_celsius": 2.0,
        "humidity_min_pct": None,
        "humidity_max_pct": None,
        "default_shelf_life_days": 3,
        "description": "Raw beef, pork, poultry, and ground meats requiring cold-chain management.",
    },
    {
        "id": "cat_seafood",
        "name": "Seafood & Fish",
        "slug": "seafood-and-fish",
        "perishability_tier": PerishabilityTier.CRITICAL.value,
        "recommended_storage": StorageRequirement.REFRIGERATED.value,
        "temp_min_celsius": 0.0,
        "temp_max_celsius": 2.0,
        "humidity_min_pct": None,
        "humidity_max_pct": None,
        "default_shelf_life_days": 2,
        "description": "Fresh fish fillets, whole finfish, shellfish, and crustaceans on ice.",
    },
    {
        "id": "cat_leafy_greens",
        "name": "Leafy Greens & Soft Produce",
        "slug": "leafy-greens-and-soft-produce",
        "perishability_tier": PerishabilityTier.CRITICAL.value,
        "recommended_storage": StorageRequirement.REFRIGERATED.value,
        "temp_min_celsius": 4.0,
        "temp_max_celsius": 7.0,
        "humidity_min_pct": 85.0,
        "humidity_max_pct": 95.0,
        "default_shelf_life_days": 5,
        "description": "Spinach, romaine, arugula, fresh herbs, berries, and delicate mushrooms.",
    },
    {
        "id": "cat_root_produce",
        "name": "Root Vegetables & Hard Fruits",
        "slug": "root-vegetables-and-hard-fruits",
        "perishability_tier": PerishabilityTier.MEDIUM.value,
        "recommended_storage": StorageRequirement.AMBIENT.value,
        "temp_min_celsius": 10.0,
        "temp_max_celsius": 15.0,
        "humidity_min_pct": 70.0,
        "humidity_max_pct": 85.0,
        "default_shelf_life_days": 14,
        "description": "Potatoes, onions, carrots, apples, citrus, and winter squashes.",
    },
    {
        "id": "cat_bakery",
        "name": "Fresh Bakery & Pastries",
        "slug": "fresh-bakery-and-pastries",
        "perishability_tier": PerishabilityTier.HIGH.value,
        "recommended_storage": StorageRequirement.AMBIENT.value,
        "temp_min_celsius": 18.0,
        "temp_max_celsius": 22.0,
        "humidity_min_pct": None,
        "humidity_max_pct": None,
        "default_shelf_life_days": 3,
        "description": "Artisan breads, baguettes, croissants, cakes, and unfilled pastries.",
    },
    {
        "id": "cat_prepared_meals",
        "name": "Prepared & Cooked Meals",
        "slug": "prepared-and-cooked-meals",
        "perishability_tier": PerishabilityTier.CRITICAL.value,
        "recommended_storage": StorageRequirement.REFRIGERATED.value,
        "temp_min_celsius": 2.0,
        "temp_max_celsius": 4.0,
        "humidity_min_pct": None,
        "humidity_max_pct": None,
        "default_shelf_life_days": 2,
        "description": "Pre-packaged sandwiches, cooked entrees, salads with dressing, deli foods.",
    },
    {
        "id": "cat_pantry_dry",
        "name": "Pantry & Dry Goods",
        "slug": "pantry-and-dry-goods",
        "perishability_tier": PerishabilityTier.LOW.value,
        "recommended_storage": StorageRequirement.DRY_PANTRY.value,
        "temp_min_celsius": 15.0,
        "temp_max_celsius": 24.0,
        "humidity_min_pct": None,
        "humidity_max_pct": 60.0,
        "default_shelf_life_days": 180,
        "description": "Rice, pasta, grains, dried legumes, flour, sugar, coffee, and spices.",
    },
    {
        "id": "cat_canned",
        "name": "Canned & Preserved Goods",
        "slug": "canned-and-preserved-goods",
        "perishability_tier": PerishabilityTier.LOW.value,
        "recommended_storage": StorageRequirement.DRY_PANTRY.value,
        "temp_min_celsius": 15.0,
        "temp_max_celsius": 24.0,
        "humidity_min_pct": None,
        "humidity_max_pct": None,
        "default_shelf_life_days": 365,
        "description": "Apertized canned vegetables, soups, preserved fruits, and sauces.",
    },
]


def seed_standard_categories(session: Session) -> int:
    """
    Idempotently seeds standard global food categories.
    Returns the count of newly inserted categories.
    """
    inserted = 0
    for cat_data in STANDARD_CATEGORIES:
        existing = session.execute(
            select(Category).where(Category.id == cat_data["id"])
        ).scalar_one_or_none()

        if not existing:
            category = Category(
                id=cat_data["id"],
                tenant_id=None,  # Global standard taxonomy
                name=cat_data["name"],
                slug=cat_data["slug"],
                perishability_tier=cat_data["perishability_tier"],
                recommended_storage=cat_data["recommended_storage"],
                temp_min_celsius=cat_data["temp_min_celsius"],
                temp_max_celsius=cat_data["temp_max_celsius"],
                humidity_min_pct=cat_data["humidity_min_pct"],
                humidity_max_pct=cat_data["humidity_max_pct"],
                default_shelf_life_days=cat_data["default_shelf_life_days"],
                description=cat_data["description"],
            )
            session.add(category)
            inserted += 1

    session.commit()
    return inserted
