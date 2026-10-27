"""
Analytics & Sustainability Metrics Service (Milestone 3 Phase 3).
Calculates business KPIs, NGO operational summaries, environmental metrics, and sanitizes CSV exports.
"""

import csv
import io
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem, InventoryStatus
from backend.app.models.surplus import (
    ClaimStatus,
    NgoProfile,
    PickupSchedule,
    PickupScheduleStatus,
    SurplusClaim,
    SurplusListing,
    SurplusStatus,
)
from backend.app.models.tenant import Tenant
from backend.app.models.waste_risk import RiskTier, WasteRiskAssessmentRecord
from backend.app.schemas.analytics import (
    BusinessDashboardSummary,
    CategoryImpact,
    EnvironmentalEquivalencies,
    NgoDashboardSummary,
    SustainabilityMetrics,
    TimeSeriesPoint,
    TimeSeriesResponse,
)

# Standard environmental & social conversion factors (EPA WARM v15 & USDA / Feeding America)
CO2E_PER_KG_FOOD = 2.5            # kg CO2e avoided per kg food rescued
KG_PER_MEAL = 0.42                # 1 meal equivalent = 1.2 lbs ≈ 0.42 kg (Feeding America benchmark)
CO2_PER_TREE_YEAR = 21.77         # kg CO2 sequestered per urban tree seedling grown for 10 years
CO2_PER_PASSENGER_CAR_MILE = 0.393 # kg CO2e per average passenger vehicle mile not driven


def normalize_to_kg(quantity: float, unit: str) -> Tuple[float, bool]:
    """
    Normalizes recorded quantities to kilograms where physical mass conversion is standard.
    Returns (mass_kg, is_mass_unit).
    """
    u = (unit or "").strip().lower()
    if u in ("kg", "kilogram", "kilograms"):
        return float(quantity), True
    if u in ("g", "gram", "grams"):
        return float(quantity) / 1000.0, True
    if u in ("liters", "liter", "l"):
        # Standard assumption for food liquids (milk, juices, soups): 1 L ≈ 1 kg
        return float(quantity), True
    if u in ("ml", "milliliter", "milliliters"):
        return float(quantity) / 1000.0, True
    return 0.0, False


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes string inputs to protect against CSV / Excel Formula Injection (CWE-1236).
    Prepends a single apostrophe (') if string starts with dangerous characters: =, +, -, @, \\t, \\r.
    """
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def get_business_dashboard_summary(db: Session, tenant_id: str) -> BusinessDashboardSummary:
    """
    Gathers operational metrics and financial risk/rescue KPIs for a food business tenant.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant_name = tenant.name if tenant else "Unknown Business"

    # 1. Commercial Inventory metrics
    items = db.query(InventoryItem).filter(
        InventoryItem.tenant_id == tenant_id,
        InventoryItem.is_active == True,
    ).all()

    total_inventory_items = len(items)
    total_stock_value = sum(float(i.current_quantity) * float(i.cost_per_unit) for i in items)

    today = date.today()
    exp_threshold = today + timedelta(days=3)

    items_expiring_soon = [
        i for i in items
        if i.status in (InventoryStatus.EXPIRING_SOON.value, InventoryStatus.EXPIRED.value)
        or (i.expiry_date and i.expiry_date <= exp_threshold)
    ]
    items_expiring_soon_count = len(items_expiring_soon)
    at_risk_value = sum(float(i.current_quantity) * float(i.cost_per_unit) for i in items_expiring_soon)

    # 2. High Risk items from ML Waste Risk table or expiry audit
    high_risk_records = db.query(WasteRiskAssessmentRecord).filter(
        WasteRiskAssessmentRecord.tenant_id == tenant_id,
        WasteRiskAssessmentRecord.risk_tier.in_([RiskTier.HIGH.value, RiskTier.CRITICAL.value]),
    ).all()
    high_risk_items_count = len({r.item_id for r in high_risk_records})
    if high_risk_items_count == 0:
        high_risk_items_count = len([i for i in items_expiring_soon if i.expiry_date and i.expiry_date <= today + timedelta(days=2)])

    # 3. Surplus Listings metrics
    listings = db.query(SurplusListing).filter(SurplusListing.tenant_id == tenant_id).all()
    listing_ids = [l.id for l in listings]

    active_surplus_listings_count = sum(
        1 for l in listings
        if l.status in (SurplusStatus.AVAILABLE.value, SurplusStatus.RESERVED.value, SurplusStatus.CLAIMED.value)
    )
    cancelled_or_expired_listings_count = sum(
        1 for l in listings
        if l.status in (SurplusStatus.CANCELLED.value, SurplusStatus.EXPIRED.value)
    )

    # 4. Claims against this business's listings
    pending_claims_count = 0
    completed_transfers_count = 0
    total_value_rescued = 0.0
    total_food_rescued_kg = 0.0
    total_units_rescued = 0.0

    recent_activity: List[Dict[str, Any]] = []

    if listing_ids:
        claims = db.query(SurplusClaim).filter(SurplusClaim.listing_id.in_(listing_ids)).all()
        for c in claims:
            if c.status in (ClaimStatus.REQUESTED.value, ClaimStatus.PENDING.value):
                pending_claims_count += 1
            elif c.status == ClaimStatus.COMPLETED.value:
                completed_transfers_count += 1
                qty = float(c.claimed_quantity)
                mass_kg, is_mass = normalize_to_kg(qty, c.unit)
                if is_mass:
                    total_food_rescued_kg += mass_kg
                else:
                    total_units_rescued += qty

                # Financial value from listing item cost
                unit_cost = float(c.listing.item.cost_per_unit) if c.listing and c.listing.item else 0.0
                total_value_rescued += qty * unit_cost

            # Record in recent activity
            recent_activity.append({
                "type": "claim",
                "id": c.id,
                "listing_id": c.listing_id,
                "listing_title": c.listing.title if c.listing else "Surplus Item",
                "claimed_quantity": float(c.claimed_quantity),
                "unit": c.unit,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })

    # 5. Upcoming pickups
    upcoming_pickups_count = db.query(func.count(PickupSchedule.id)).filter(
        PickupSchedule.donor_tenant_id == tenant_id,
        PickupSchedule.status.in_([
            PickupScheduleStatus.SCHEDULED.value,
            PickupScheduleStatus.RESCHEDULED.value,
            PickupScheduleStatus.READY_FOR_COLLECTION.value,
        ]),
    ).scalar() or 0

    # Sort recent activity descending
    recent_activity.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    co2e_avoided_kg = round(total_food_rescued_kg * CO2E_PER_KG_FOOD, 2)
    meals_provided = int(total_food_rescued_kg / KG_PER_MEAL) if total_food_rescued_kg > 0 else int(total_units_rescued)

    return BusinessDashboardSummary(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        total_inventory_items=total_inventory_items,
        total_stock_value=round(total_stock_value, 2),
        items_expiring_soon_count=items_expiring_soon_count,
        at_risk_value=round(at_risk_value, 2),
        high_risk_items_count=high_risk_items_count,
        active_surplus_listings_count=active_surplus_listings_count,
        pending_claims_count=pending_claims_count,
        upcoming_pickups_count=upcoming_pickups_count,
        completed_transfers_count=completed_transfers_count,
        cancelled_or_expired_listings_count=cancelled_or_expired_listings_count,
        total_value_rescued=round(total_value_rescued, 2),
        total_food_rescued_kg=round(total_food_rescued_kg, 2),
        co2e_avoided_kg=co2e_avoided_kg,
        meals_provided=meals_provided,
        recent_activity=recent_activity[:10],
    )


def get_ngo_dashboard_summary(db: Session, ngo_tenant_id: str) -> NgoDashboardSummary:
    """
    Gathers operational metrics, incoming donations, claims status, and meals served for an NGO tenant.
    """
    tenant = db.query(Tenant).filter(Tenant.id == ngo_tenant_id).first()
    org_name = tenant.name if tenant else "Recipient NGO"

    profile = db.query(NgoProfile).filter(NgoProfile.tenant_id == ngo_tenant_id).first()
    org_type = profile.organization_type if profile else "FOOD_BANK"
    is_verified = profile.is_verified if profile else True
    service_radius = float(profile.service_radius_km) if profile else 25.0
    accepted_cats: List[str] = []
    storage_facilities: List[str] = ["AMBIENT"]
    if profile:
        try:
            accepted_cats = json.loads(profile.accepted_categories) if profile.accepted_categories else []
            storage_facilities = json.loads(profile.storage_facilities) if profile.storage_facilities else ["AMBIENT"]
        except Exception:
            pass

    # 1. Eligible Surplus Listings (status == AVAILABLE and window open)
    now_utc = datetime.now(timezone.utc)
    eligible_query = db.query(SurplusListing).filter(
        SurplusListing.status == SurplusStatus.AVAILABLE.value,
        SurplusListing.available_until >= now_utc,
    )
    eligible_surplus_listings_count = eligible_query.count()

    # 2. Claims made by this NGO
    claims = db.query(SurplusClaim).filter(SurplusClaim.ngo_tenant_id == ngo_tenant_id).all()

    pending_claims_count = 0
    accepted_claims_count = 0
    completed_collections_count = 0
    total_food_rescued_kg = 0.0
    total_food_rescued_units = 0.0
    value_received = 0.0

    recent_claims: List[Dict[str, Any]] = []

    for c in claims:
        if c.status in (ClaimStatus.REQUESTED.value, ClaimStatus.PENDING.value):
            pending_claims_count += 1
        elif c.status in (ClaimStatus.ACCEPTED.value, ClaimStatus.APPROVED.value, ClaimStatus.READY_FOR_PICKUP.value):
            accepted_claims_count += 1
        elif c.status == ClaimStatus.COMPLETED.value:
            completed_collections_count += 1
            qty = float(c.claimed_quantity)
            mass_kg, is_mass = normalize_to_kg(qty, c.unit)
            if is_mass:
                total_food_rescued_kg += mass_kg
            else:
                total_food_rescued_units += qty

            cost = float(c.listing.item.cost_per_unit) if c.listing and c.listing.item else 0.0
            value_received += qty * cost

        recent_claims.append({
            "claim_id": c.id,
            "listing_id": c.listing_id,
            "listing_title": c.listing.title if c.listing else "Surplus Donation",
            "quantity": float(c.claimed_quantity),
            "unit": c.unit,
            "status": c.status,
            "donor_tenant_id": c.listing.tenant_id if c.listing else None,
            "pickup_time": c.pickup_time.isoformat() if c.pickup_time else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    # 3. Upcoming Pickups
    upcoming_pickups_count = db.query(func.count(PickupSchedule.id)).filter(
        PickupSchedule.ngo_tenant_id == ngo_tenant_id,
        PickupSchedule.status.in_([
            PickupScheduleStatus.SCHEDULED.value,
            PickupScheduleStatus.RESCHEDULED.value,
            PickupScheduleStatus.READY_FOR_COLLECTION.value,
        ]),
    ).scalar() or 0

    recent_claims.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    meals_provided = int(total_food_rescued_kg / KG_PER_MEAL) if total_food_rescued_kg > 0 else int(total_food_rescued_units)

    return NgoDashboardSummary(
        tenant_id=ngo_tenant_id,
        organization_name=org_name,
        organization_type=org_type,
        is_verified=is_verified,
        service_radius_km=round(service_radius, 1),
        accepted_categories=accepted_cats,
        storage_facilities=storage_facilities,
        eligible_surplus_listings_count=eligible_surplus_listings_count,
        pending_claims_count=pending_claims_count,
        accepted_claims_count=accepted_claims_count,
        upcoming_pickups_count=upcoming_pickups_count,
        completed_collections_count=completed_collections_count,
        total_food_rescued_kg=round(total_food_rescued_kg, 2),
        total_food_rescued_units=round(total_food_rescued_units, 2),
        meals_provided=meals_provided,
        value_received=round(value_received, 2),
        recent_claims=recent_claims[:10],
    )


def get_sustainability_metrics(
    db: Session,
    tenant_id: Optional[str] = None,
    is_ngo: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> SustainabilityMetrics:
    """
    Computes verified environmental, social, and financial impact from COMPLETED surplus claims.
    """
    query = db.query(SurplusClaim).filter(SurplusClaim.status == ClaimStatus.COMPLETED.value)

    if tenant_id:
        if is_ngo:
            query = query.filter(SurplusClaim.ngo_tenant_id == tenant_id)
        else:
            query = query.join(SurplusListing).filter(SurplusListing.tenant_id == tenant_id)

    if date_from:
        dt_start = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        query = query.filter(SurplusClaim.updated_at >= dt_start)

    if date_to:
        dt_end = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
        query = query.filter(SurplusClaim.updated_at <= dt_end)

    claims = query.all()

    total_weight_kg = 0.0
    total_units_count = 0.0
    total_value = 0.0
    completed_claims_count = len(claims)

    participating_donors = set()
    participating_ngos = set()

    # Category breakdowns: cat_id -> {name, kg, units, value}
    category_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "name": "General Surplus",
        "kg": 0.0,
        "units": 0.0,
        "value": 0.0,
    })

    for c in claims:
        participating_ngos.add(c.ngo_tenant_id)
        if c.listing:
            participating_donors.add(c.listing.tenant_id)
            item = c.listing.item
            cat = item.category if item else None
            cat_id = cat.id if cat else "cat_general"
            cat_name = cat.name if cat else "Uncategorized"
            cost_per_unit = float(item.cost_per_unit) if item else 0.0
        else:
            cat_id = "cat_general"
            cat_name = "Uncategorized"
            cost_per_unit = 0.0

        qty = float(c.claimed_quantity)
        val = qty * cost_per_unit
        mass_kg, is_mass = normalize_to_kg(qty, c.unit)

        total_value += val
        category_map[cat_id]["name"] = cat_name
        category_map[cat_id]["value"] += val

        if is_mass:
            total_weight_kg += mass_kg
            category_map[cat_id]["kg"] += mass_kg
        else:
            total_units_count += qty
            category_map[cat_id]["units"] += qty

    co2e_avoided_kg = round(total_weight_kg * CO2E_PER_KG_FOOD, 2)
    meals_provided = int(total_weight_kg / KG_PER_MEAL) if total_weight_kg > 0 else int(total_units_count)

    trees_planted = round(co2e_avoided_kg / CO2_PER_TREE_YEAR, 2)
    car_miles = round(co2e_avoided_kg / CO2_PER_PASSENGER_CAR_MILE, 2)

    breakdown: List[CategoryImpact] = []
    for cid, data in sorted(category_map.items(), key=lambda x: x[1]["kg"] + x[1]["units"], reverse=True):
        cat_co2e = round(data["kg"] * CO2E_PER_KG_FOOD, 2)
        cat_meals = int(data["kg"] / KG_PER_MEAL) if data["kg"] > 0 else int(data["units"])
        breakdown.append(CategoryImpact(
            category_id=cid,
            category_name=data["name"],
            rescued_kg=round(data["kg"], 2),
            rescued_units=round(data["units"], 2),
            value_rescued=round(data["value"], 2),
            co2e_avoided_kg=cat_co2e,
            meals_provided=cat_meals,
        ))

    return SustainabilityMetrics(
        total_rescued_weight_kg=round(total_weight_kg, 2),
        total_rescued_units_count=round(total_units_count, 2),
        total_value_rescued=round(total_value, 2),
        co2e_avoided_kg=co2e_avoided_kg,
        total_meals_provided=meals_provided,
        completed_claims_count=completed_claims_count,
        participating_businesses_count=len(participating_donors),
        participating_ngos_count=len(participating_ngos),
        equivalencies=EnvironmentalEquivalencies(
            co2e_avoided_kg=co2e_avoided_kg,
            trees_planted_equivalent=trees_planted,
            passenger_car_miles_avoided=car_miles,
        ),
        category_breakdown=breakdown,
    )


def get_redistribution_time_series(
    db: Session,
    tenant_id: Optional[str] = None,
    is_ngo: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    interval: str = "daily",
) -> TimeSeriesResponse:
    """
    Generates chronological trend data points for chart visualizations.
    """
    if not date_from:
        date_from = date.today() - timedelta(days=30)
    if not date_to:
        date_to = date.today()

    query = db.query(SurplusClaim).filter(SurplusClaim.status == ClaimStatus.COMPLETED.value)

    if tenant_id:
        if is_ngo:
            query = query.filter(SurplusClaim.ngo_tenant_id == tenant_id)
        else:
            query = query.join(SurplusListing).filter(SurplusListing.tenant_id == tenant_id)

    dt_start = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc)
    dt_end = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
    query = query.filter(SurplusClaim.updated_at >= dt_start, SurplusClaim.updated_at <= dt_end)

    claims = query.all()

    # Bucketing
    buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: {
        "kg": 0.0,
        "units": 0.0,
        "claims_count": 0,
        "value": 0.0,
    })

    for c in claims:
        claim_dt = c.updated_at or c.created_at
        if interval == "monthly":
            bucket_key = claim_dt.strftime("%Y-%m")
        else:
            bucket_key = claim_dt.strftime("%Y-%m-%d")

        qty = float(c.claimed_quantity)
        mass_kg, is_mass = normalize_to_kg(qty, c.unit)
        cost = float(c.listing.item.cost_per_unit) if c.listing and c.listing.item else 0.0

        buckets[bucket_key]["claims_count"] += 1
        buckets[bucket_key]["value"] += qty * cost
        if is_mass:
            buckets[bucket_key]["kg"] += mass_kg
        else:
            buckets[bucket_key]["units"] += qty

    # Sort chronological
    points: List[TimeSeriesPoint] = []
    for key in sorted(buckets.keys()):
        data = buckets[key]
        co2e = round(data["kg"] * CO2E_PER_KG_FOOD, 2)
        meals = int(data["kg"] / KG_PER_MEAL) if data["kg"] > 0 else int(data["units"])
        points.append(TimeSeriesPoint(
            date=key,
            rescued_kg=round(data["kg"], 2),
            claims_count=int(data["claims_count"]),
            co2e_avoided_kg=co2e,
            meals_provided=meals,
            value_rescued=round(data["value"], 2),
        ))

    return TimeSeriesResponse(
        interval=interval,
        start_date=date_from.isoformat(),
        end_date=date_to.isoformat(),
        total_points=len(points),
        points=points,
    )


def generate_redistribution_csv(
    db: Session,
    tenant_id: Optional[str] = None,
    is_ngo: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> io.StringIO:
    """
    Builds a sanitized CSV report of completed food rescue activities.
    Every cell is screened through sanitize_csv_cell to neutralize formula injection attacks.
    """
    query = db.query(SurplusClaim).filter(SurplusClaim.status == ClaimStatus.COMPLETED.value)

    if tenant_id:
        if is_ngo:
            query = query.filter(SurplusClaim.ngo_tenant_id == tenant_id)
        else:
            query = query.join(SurplusListing).filter(SurplusListing.tenant_id == tenant_id)

    if date_from:
        dt_start = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        query = query.filter(SurplusClaim.updated_at >= dt_start)
    if date_to:
        dt_end = datetime.combine(date_to, datetime.max.time()).replace(tzinfo=timezone.utc)
        query = query.filter(SurplusClaim.updated_at <= dt_end)

    claims = query.order_by(SurplusClaim.updated_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Headers
    headers = [
        "Claim ID",
        "Completed Date",
        "Listing Title",
        "Category",
        "Donor Business",
        "Recipient Organization",
        "Claimed Quantity",
        "Unit",
        "Normalized Weight (kg)",
        "Estimated Value ($)",
        "Avoided CO2e (kg)",
        "Meal Equivalents",
        "Claim Status",
    ]
    writer.writerow([sanitize_csv_cell(h) for h in headers])

    for c in claims:
        completed_dt = (c.updated_at or c.created_at).strftime("%Y-%m-%d %H:%M:%S")
        listing_title = c.listing.title if c.listing else "Surplus Item"
        category_name = (
            c.listing.item.category.name
            if c.listing and c.listing.item and c.listing.item.category
            else "General"
        )
        donor_name = (
            c.listing.tenant.name
            if c.listing and c.listing.tenant
            else "Donor"
        )
        ngo_name = c.ngo_tenant.name if c.ngo_tenant else "Recipient NGO"

        qty = float(c.claimed_quantity)
        mass_kg, is_mass = normalize_to_kg(qty, c.unit)
        cost = float(c.listing.item.cost_per_unit) if c.listing and c.listing.item else 0.0
        val = qty * cost
        co2e = round(mass_kg * CO2E_PER_KG_FOOD, 2)
        meals = int(mass_kg / KG_PER_MEAL) if is_mass and mass_kg > 0 else int(qty)

        row = [
            c.id,
            completed_dt,
            listing_title,
            category_name,
            donor_name,
            ngo_name,
            f"{qty:.2f}",
            c.unit,
            f"{mass_kg:.2f}" if is_mass else "N/A",
            f"{val:.2f}",
            f"{co2e:.2f}",
            meals,
            c.status,
        ]
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    output.seek(0)
    return output
