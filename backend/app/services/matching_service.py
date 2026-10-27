"""Explainable NGO Matching Engine (Milestone 3 - Phase 1).

Ranks recipient NGOs, community pantries, and shelters against surplus food listings
using multi-factor scoring:
  1. Food Category Compatibility (30%)
  2. Capacity Fit (25%)
  3. Storage & Cold-Chain Compatibility (20%)
  4. Proximity / Haversine Distance (15%)
  5. Shelf-Life Urgency (10%)
  6. Verified Organization Bonus (+5%)

Strict Food Safety & Integrity Rules:
  - Chilled/Frozen items REQUIRE cold storage capability. Incompatible profiles are eliminated.
  - Missing coordinates are NEVER fabricated. Neutral proximity score is assigned with
    an explicit explanation ('Distance unverified (coordinates not configured)').
  - Inactive NGO tenants are excluded.
"""

import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.category import Category
from backend.app.models.inventory import InventoryItem
from backend.app.models.surplus import NgoProfile, SurplusListing
from backend.app.models.tenant import BusinessType, Tenant
from backend.app.schemas.surplus import NgoMatchRecommendation, SurplusMatchesResponse


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two GPS coordinates in kilometers.
    Earth radius = 6371.0 km.
    """
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(radius * c, 2)


def parse_json_list(raw_val: Any) -> List[str]:
    """Helper to parse a list from string, JSON array, or list."""
    if isinstance(raw_val, list):
        return [str(x).strip().upper() for x in raw_val if x]
    if isinstance(raw_val, str):
        try:
            parsed = json.loads(raw_val)
            if isinstance(parsed, list):
                return [str(x).strip().upper() for x in parsed if x]
        except Exception:
            pass
        return [x.strip().upper() for x in raw_val.split(",") if x.strip()]
    return []


def evaluate_category_compatibility(
    category_name: str, accepted_categories: List[str]
) -> Tuple[float, Optional[str]]:
    """
    Category matching (30 points maximum).
    If accepted_categories is empty or includes 'ALL', receives full score.
    Otherwise matches category name (case-insensitive).
    """
    cat_upper = category_name.upper().strip()
    norm_accepted = [c.upper() for c in accepted_categories]

    if not norm_accepted or "ALL" in norm_accepted or "*" in norm_accepted:
        return 30.0, f"Accepts all food categories (including {category_name})"

    # Check direct match or substring
    for accepted in norm_accepted:
        if accepted == cat_upper or accepted in cat_upper or cat_upper in accepted:
            return 30.0, f"Explicitly accepts '{category_name}' category"

    # Category not accepted
    return 0.0, None


def evaluate_storage_compatibility(
    storage_req: str, storage_facilities: List[str]
) -> Tuple[float, bool, Optional[str]]:
    """
    Storage cold-chain check (20 points maximum).
    Returns (score, is_safe, reason).
    If storage requirement is violated for perishable food, is_safe = False.
    """
    req = storage_req.upper().strip()
    facilities = [f.upper() for f in storage_facilities]

    # Ambient items can be accepted anywhere
    if req in ("AMBIENT", "ROOM_TEMPERATURE", "DRY"):
        if facilities:
            return 20.0, True, f"Standard ambient storage supported ({', '.join(facilities)})"
        return 15.0, True, "Ambient storage accepted"

    # Cold chain requirements
    if req in ("CHILLED", "REFRIGERATED", "COLD"):
        if any(f in facilities for f in ("REFRIGERATED", "CHILLED", "COLD_ROOM", "FROZEN")):
            return 20.0, True, "Equipped with verified refrigeration/cold-storage"
        return 0.0, False, "Safety rejection: requires refrigeration but NGO lacks cold-chain storage"

    if req in ("FROZEN", "DEEP_FREEZE"):
        if any(f in facilities for f in ("FROZEN", "DEEP_FREEZE")):
            return 20.0, True, "Equipped with deep freeze storage"
        return 0.0, False, "Safety rejection: requires freezer but NGO lacks frozen storage"

    if req in ("WARM", "HEATED"):
        if any(f in facilities for f in ("WARM", "HEATED", "INSULATED_CONTAINERS")):
            return 20.0, True, "Equipped with insulated/heated transport"
        return 10.0, True, "Insulated container requested"

    # Default fallback
    return 15.0, True, f"Storage requirement: {req}"


def evaluate_capacity_fit(
    listing_qty: float, max_capacity: float
) -> Tuple[float, Optional[str]]:
    """
    Capacity compatibility (25 points maximum).
    Evaluates whether the NGO has adequate capacity to handle the donation batch.
    """
    if max_capacity <= 0:
        return 5.0, "Capacity unknown (rated default)"

    ratio = listing_qty / max_capacity

    if ratio <= 0.25:
        # Small batch, very easy to absorb
        return 25.0, f"Readily absorbs {listing_qty:.1f} units (under 25% of {max_capacity:.0f} max capacity)"
    elif ratio <= 0.75:
        # Good batch size
        return 22.0, f"Optimal batch size for {max_capacity:.0f} capacity ({ratio*100:.0f}% utilization)"
    elif ratio <= 1.0:
        # Near max capacity
        return 18.0, f"Accommodates full batch near capacity ceiling ({listing_qty:.1f}/{max_capacity:.0f} units)"
    elif ratio <= 1.5:
        # Slightly exceeds standard single-batch capacity
        return 10.0, f"Exceeds typical batch capacity ({listing_qty:.1f} vs {max_capacity:.0f} max) - requires coordination"
    else:
        # Extreme excess
        return 2.0, f"Batch size ({listing_qty:.1f}) exceeds NGO single-drop capacity ({max_capacity:.0f})"


def evaluate_proximity(
    origin_lat: Optional[float],
    origin_lon: Optional[float],
    ngo_lat: Optional[float],
    ngo_lon: Optional[float],
    service_radius_km: float,
) -> Tuple[float, Optional[float], str]:
    """
    Proximity scoring (15 points maximum).
    Rule: Never fabricate coordinates if missing.
    """
    if (
        origin_lat is None
        or origin_lon is None
        or ngo_lat is None
        or ngo_lon is None
    ):
        return 7.5, None, "Distance unverified (coordinates not configured)"

    dist = haversine_distance(origin_lat, origin_lon, ngo_lat, ngo_lon)

    if dist <= service_radius_km:
        # Proximity score scales inversely with distance
        scaled_score = 15.0 * max(0.1, 1.0 - (dist / service_radius_km))
        return (
            round(scaled_score, 1),
            dist,
            f"Within service range ({dist} km <= {service_radius_km} km radius)",
        )
    else:
        return (
            0.0,
            dist,
            f"Outside service radius ({dist} km > {service_radius_km} km radius)",
        )


def evaluate_urgency(days_to_expiry: float) -> Tuple[float, str]:
    """
    Shelf-life urgency scoring (10 points maximum).
    Prioritizes items on the verge of expiration for immediate rescue.
    """
    if days_to_expiry <= 1.0:
        return 10.0, "Critical rescue urgency (≤24 hours to expiry)"
    elif days_to_expiry <= 2.0:
        return 8.0, "High urgency (≤48 hours to expiry)"
    elif days_to_expiry <= 4.0:
        return 6.0, "Moderate rescue window (≤4 days to expiry)"
    else:
        return 4.0, f"Stable shelf life ({days_to_expiry:.1f} days remaining)"


def calculate_ngo_matches(
    db: Session,
    listing: SurplusListing,
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
) -> SurplusMatchesResponse:
    """
    Executes the multi-factor NGO matching algorithm for a given surplus listing.
    Ranks compatible recipient organizations and attaches human-readable match explanations.
    """
    # 1. Fetch item and category details
    item = listing.item
    category_name = item.category.name if item and item.category else "Uncategorized"
    storage_req = listing.storage_requirement or (item.storage_requirement if item else "AMBIENT")

    today = datetime.now(timezone.utc).date()
    days_to_expiry = max(0.0, float((listing.expiry_date - today).days))

    # 2. Query all active NGO tenants
    ngo_tenants = (
        db.execute(
            select(Tenant)
            .where(
                Tenant.is_active == True,
                Tenant.business_type == BusinessType.NGO_RECIPIENT.value,
            )
        )
        .scalars()
        .all()
    )

    total_candidates = len(ngo_tenants)
    recommendations: List[NgoMatchRecommendation] = []

    for tenant in ngo_tenants:
        profile: Optional[NgoProfile] = tenant.ngo_profile

        # Fallback profile defaults if profile record hasn't been explicitly populated
        if profile:
            org_type = profile.organization_type
            is_verified = profile.is_verified
            max_capacity = float(profile.max_capacity_units)
            service_radius = float(profile.service_radius_km)
            accepted_cats = parse_json_list(profile.accepted_categories)
            storage_facs = parse_json_list(profile.storage_facilities)
            ngo_lat = float(profile.latitude) if profile.latitude is not None else None
            ngo_lon = float(profile.longitude) if profile.longitude is not None else None
        else:
            org_type = "COMMUNITY_PANTRY"
            is_verified = False
            max_capacity = 250.0
            service_radius = 25.0
            accepted_cats = ["ALL"]
            storage_facs = ["AMBIENT"]
            ngo_lat = None
            ngo_lon = None

        match_reasons: List[str] = []

        # A. Storage / Cold-Chain Gate
        storage_score, is_safe, storage_reason = evaluate_storage_compatibility(
            storage_req, storage_facs
        )
        if not is_safe:
            # Cold chain safety violation: exclude from recommendations
            continue
        if storage_reason:
            match_reasons.append(storage_reason)

        # B. Category Compatibility Gate
        cat_score, cat_reason = evaluate_category_compatibility(category_name, accepted_cats)
        if cat_score == 0.0 and accepted_cats:
            # Explicit category rejection: exclude
            continue
        if cat_reason:
            match_reasons.append(cat_reason)

        # C. Capacity Scoring
        cap_score, cap_reason = evaluate_capacity_fit(float(listing.quantity), max_capacity)
        if cap_reason:
            match_reasons.append(cap_reason)

        # D. Proximity / Distance Scoring
        prox_score, dist_km, prox_reason = evaluate_proximity(
            origin_lat, origin_lon, ngo_lat, ngo_lon, service_radius
        )
        match_reasons.append(prox_reason)

        # E. Urgency Scoring
        urgency_score, urgency_reason = evaluate_urgency(days_to_expiry)
        match_reasons.append(urgency_reason)

        # F. Verification Bonus (+5%)
        bonus = 5.0 if is_verified else 0.0
        if is_verified:
            match_reasons.append("Verified community recipient bonus (+5.0 pts)")

        # Total Aggregate Score (0 to 100)
        total_score = round(
            min(100.0, cat_score + cap_score + storage_score + prox_score + urgency_score + bonus),
            1,
        )

        recommendations.append(
            NgoMatchRecommendation(
                ngo_tenant_id=tenant.id,
                ngo_name=tenant.name,
                organization_type=org_type,
                is_verified=is_verified,
                match_score=total_score,
                distance_km=dist_km,
                max_capacity_units=max_capacity,
                storage_facilities=storage_facs,
                match_reasons=match_reasons,
            )
        )

    # Sort candidates descending by match score
    recommendations.sort(key=lambda r: r.match_score, reverse=True)

    return SurplusMatchesResponse(
        listing_id=listing.id,
        product_name=item.name if item else "Unknown Item",
        quantity=float(listing.quantity),
        unit=listing.unit,
        storage_requirement=storage_req,
        days_to_expiry=days_to_expiry,
        total_candidates_evaluated=total_candidates,
        matching_recommendations=recommendations,
    )
