"""
Pydantic Schemas for Business, NGO Dashboards, and Sustainability Impact Analytics (Milestone 3 Phase 3).
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CategoryImpact(BaseModel):
    """Category-specific sustainability impact aggregation."""
    category_id: str
    category_name: str
    rescued_kg: float = Field(0.0, description="Total mass rescued in kg")
    rescued_units: float = Field(0.0, description="Total discrete units/items rescued")
    value_rescued: float = Field(0.0, description="Total financial loss prevented ($)")
    co2e_avoided_kg: float = Field(0.0, description="Avoided greenhouse gas emissions (kg CO2e)")
    meals_provided: int = Field(0, description="Meal equivalents provided")


class EnvironmentalEquivalencies(BaseModel):
    """Tangible environmental equivalence metrics."""
    co2e_avoided_kg: float = Field(..., description="Avoided GHG emissions in kg CO2e")
    trees_planted_equivalent: float = Field(
        ...,
        description="Equivalent urban tree seedlings grown for 10 years (EPA: 21.77 kg CO2/tree/year)"
    )
    passenger_car_miles_avoided: float = Field(
        ...,
        description="Equivalent average passenger vehicle miles not driven (EPA: 0.393 kg CO2e/mile)"
    )


class SustainabilityMetrics(BaseModel):
    """
    Cumulative sustainability, social, and financial impact metrics
    derived from completed food redistribution workflows.
    """
    total_rescued_weight_kg: float = Field(0.0, description="Verified total food mass rescued in kilograms")
    total_rescued_units_count: float = Field(0.0, description="Total count of non-mass discrete units rescued")
    total_value_rescued: float = Field(0.0, description="Total financial value of food rescued ($)")
    co2e_avoided_kg: float = Field(0.0, description="Total GHG emissions avoided (kg CO2e) via EPA WARM v15 standard (2.5 kg CO2e/kg food)")
    total_meals_provided: int = Field(0, description="Estimated meal equivalents (USDA/Feeding America benchmark: 0.42 kg/meal)")
    completed_claims_count: int = Field(0, description="Number of fully completed donation claims")
    participating_businesses_count: int = Field(0, description="Count of distinct donor businesses contributing")
    participating_ngos_count: int = Field(0, description="Count of distinct recipient organizations benefiting")
    equivalencies: EnvironmentalEquivalencies
    category_breakdown: List[CategoryImpact] = Field(default_factory=list)
    methodology_notes: str = Field(
        "EPA WARM v15: 2.5 kg CO2e avoided per kg food rescued. Feeding America benchmark: 0.42 kg (1.2 lbs) per meal equivalent. Trees equivalent: 21.77 kg CO2/tree. Car miles: 0.393 kg CO2e/mile.",
        description="Standardized environmental and social conversion factors"
    )


class BusinessDashboardSummary(BaseModel):
    """Executive KPI summary for food businesses and commercial donors."""
    tenant_id: str
    tenant_name: str
    total_inventory_items: int = Field(0, description="Active items in stock")
    total_stock_value: float = Field(0.0, description="Total inventory cost value ($)")
    items_expiring_soon_count: int = Field(0, description="Items expiring within <= 3 days")
    at_risk_value: float = Field(0.0, description="Monetary value of inventory at risk of expiration")
    high_risk_items_count: int = Field(0, description="Items flagged HIGH or CRITICAL risk by ML waste model / expiry audit")
    active_surplus_listings_count: int = Field(0, description="Active surplus listings (AVAILABLE/RESERVED/CLAIMED)")
    pending_claims_count: int = Field(0, description="Incoming claim requests awaiting business review")
    upcoming_pickups_count: int = Field(0, description="Scheduled or in-progress pickups")
    completed_transfers_count: int = Field(0, description="Successfully completed surplus donations")
    cancelled_or_expired_listings_count: int = Field(0, description="Surplus listings expired or cancelled")
    total_value_rescued: float = Field(0.0, description="Cumulative financial value rescued via donations")
    total_food_rescued_kg: float = Field(0.0, description="Cumulative food mass donated (kg)")
    co2e_avoided_kg: float = Field(0.0, description="Cumulative avoided GHG emissions (kg CO2e)")
    meals_provided: int = Field(0, description="Total meal equivalents donated")
    recent_activity: List[Dict[str, Any]] = Field(default_factory=list)


class NgoDashboardSummary(BaseModel):
    """Operational KPI summary for recipient NGOs, food banks, and shelters."""
    tenant_id: str
    organization_name: str
    organization_type: str
    is_verified: bool
    service_radius_km: float
    accepted_categories: List[str] = Field(default_factory=list)
    storage_facilities: List[str] = Field(default_factory=list)
    eligible_surplus_listings_count: int = Field(0, description="Available surplus listings matching NGO criteria")
    pending_claims_count: int = Field(0, description="Claims submitted by this NGO awaiting donor review")
    accepted_claims_count: int = Field(0, description="Claims approved and ready for pickup scheduling")
    upcoming_pickups_count: int = Field(0, description="Scheduled collections upcoming")
    completed_collections_count: int = Field(0, description="Total successful collections completed")
    total_food_rescued_kg: float = Field(0.0, description="Total mass received in kilograms")
    total_food_rescued_units: float = Field(0.0, description="Total discrete units received")
    meals_provided: int = Field(0, description="Estimated meals served from rescued food")
    value_received: float = Field(0.0, description="Total estimated grocery value received ($)")
    recent_claims: List[Dict[str, Any]] = Field(default_factory=list)


class TimeSeriesPoint(BaseModel):
    """Single temporal milestone point for trend charts."""
    date: str = Field(..., description="Date formatted as YYYY-MM-DD or YYYY-MM")
    rescued_kg: float = Field(0.0, description="Food mass rescued (kg)")
    claims_count: int = Field(0, description="Number of completed claims")
    co2e_avoided_kg: float = Field(0.0, description="Avoided emissions (kg CO2e)")
    meals_provided: int = Field(0, description="Meal equivalents provided")
    value_rescued: float = Field(0.0, description="Financial value rescued ($)")


class TimeSeriesResponse(BaseModel):
    """Time-series aggregation payload for redistribution impact over time."""
    interval: str = Field("daily", description="'daily' or 'monthly'")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_points: int = 0
    points: List[TimeSeriesPoint] = Field(default_factory=list)
