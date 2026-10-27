/**
 * Core Domain & API Types for Food Waste Management Platform Frontend.
 */

export type PerishabilityTier = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type StorageRequirement = 'AMBIENT' | 'REFRIGERATED' | 'FROZEN' | 'DRY_PANTRY' | 'CLIMATE_CONTROLLED';
export type InventoryStatus = 'ACTIVE' | 'EXPIRING_SOON' | 'EXPIRED' | 'DEPLETED' | 'DONATED' | 'DISCARDED';
export type ItemUnit = 'kg' | 'g' | 'liters' | 'ml' | 'units' | 'boxes' | 'packs';
export type AlertLevel = 'FRESH' | 'NOTICE' | 'WARNING' | 'CRITICAL' | 'EXPIRED';

export interface CategorySummary {
  id: string;
  name: string;
  slug: string;
  perishability_tier: PerishabilityTier;
  recommended_storage: StorageRequirement;
}

export interface InventoryItem {
  id: string;
  tenant_id: string;
  category_id: string;
  category?: CategorySummary;
  name: string;
  sku?: string;
  barcode?: string;
  current_quantity: number;
  unit: ItemUnit;
  cost_per_unit: number;
  selling_price?: number;
  purchase_date: string;
  expiry_date: string;
  days_to_expiry: number;
  batch_number?: string;
  storage_requirement: StorageRequirement;
  storage_location?: string;
  status: InventoryStatus;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InventoryItemCreatePayload {
  name: string;
  category_id: string;
  sku?: string;
  barcode?: string;
  initial_quantity: number;
  unit: string;
  cost_per_unit: number;
  selling_price?: number;
  purchase_date: string;
  expiry_date: string;
  batch_number?: string;
  storage_requirement: string;
  storage_location?: string;
}

export interface StockTransaction {
  id: string;
  tenant_id: string;
  item_id: string;
  transaction_type: string;
  quantity_change: number;
  quantity_before: number;
  quantity_after: number;
  reason?: string;
  reference_type?: string;
  reference_id?: string;
  created_by_user_id?: string;
  created_at: string;
}

export interface StockAdjustmentPayload {
  quantity_delta: number;
  adjustment_type: string;
  reason: string;
  reference_type?: string;
  reference_id?: string;
  idempotency_key?: string;
}

export interface PaginationMeta {
  page: number;
  size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  pagination: PaginationMeta;
}

export interface SuccessEnvelope<T> {
  success: boolean;
  data: T;
  meta?: Record<string, any>;
}

export interface CsvImportRowError {
  row_number: number;
  field_name?: string;
  invalid_value?: string;
  error_code: string;
  error_message: string;
}

export interface CsvImportSummary {
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  skipped_rows: number;
  duplicate_rows: number;
}

export interface CsvImportResponse {
  job_id: string;
  filename: string;
  dry_run: boolean;
  allow_partial: boolean;
  status: string;
  summary: CsvImportSummary;
  errors: CsvImportRowError[];
}

export interface ExpiryAlertItemSummary {
  item_id: string;
  name: string;
  sku?: string;
  category_name: string;
  current_quantity: number;
  unit: string;
  expiry_date: string;
  days_remaining: number;
  alert_level: AlertLevel;
  recommended_action: string;
  donation_eligible: boolean;
  status: string;
}

export interface ExpiryEvaluationSummary {
  total_evaluated: number;
  fresh_count: number;
  notice_count: number;
  warning_count: number;
  critical_count: number;
  expired_count: number;
  alerts_created: number;
  alerts_skipped_dedup: number;
  items_flagged_for_donation: number;
  total_at_risk_value: number;
}

export interface ExpirySchedulerDiagnostics {
  scheduler_mode: string;
  background_worker_active: boolean;
  missing_configurations: string[];
  recommendation: string;
}

export interface ExpiryEvaluationResponse {
  evaluated_at: string;
  tenant_id: string;
  tenant_timezone: string;
  dry_run: boolean;
  summary: ExpiryEvaluationSummary;
  items: ExpiryAlertItemSummary[];
  scheduler_diagnostics: ExpirySchedulerDiagnostics;
}

export interface TenantAlertConfig {
  id: string;
  tenant_id: string;
  critical_threshold_hours: number;
  warning_threshold_days: number;
  notice_threshold_days: number;
  auto_flag_for_donation: boolean;
  email_notifications_enabled: boolean;
  webhook_notification_url?: string;
  updated_at: string;
}

export interface ExpiryAlertHistory {
  id: string;
  tenant_id: string;
  item_id: string;
  item_name?: string;
  alert_level: string;
  days_remaining: number;
  acknowledged: boolean;
  acknowledged_by_user_id?: string;
  acknowledged_at?: string;
  action_taken?: string;
  created_at: string;
}

export interface PosIntegration {
  id: string;
  tenant_id: string;
  provider: string;
  integration_name: string;
  webhook_slug: string;
  webhook_url: string;
  webhook_signing_secret?: string;
  is_active: boolean;
  last_sync_at?: string;
  last_error_message?: string;
  created_at: string;
}

export interface PosSyncResponse {
  integration_id: string;
  provider: string;
  status: string;
  synced_items_count: number;
  adjusted_transactions_count: number;
  errors: string[];
  next_cursor?: string;
  audit_summary: string;
}

// -----------------------------------------------------------------------------
// Milestone 3 - Phase 1: Surplus Food Listings, Matching, and NGO Claims
// -----------------------------------------------------------------------------

export type SurplusStatus =
  | 'DRAFT'
  | 'AVAILABLE'
  | 'RESERVED'
  | 'CLAIMED'
  | 'COMPLETED'
  | 'PICKED_UP'
  | 'EXPIRED'
  | 'CANCELLED';

export type ClaimStatus =
  | 'REQUESTED'
  | 'PENDING'
  | 'APPROVED'
  | 'ACCEPTED'
  | 'READY_FOR_PICKUP'
  | 'PICKED_UP'
  | 'REJECTED'
  | 'CANCELLED'
  | 'EXPIRED'
  | 'COMPLETED';

export type PickupScheduleStatus =
  | 'SCHEDULED'
  | 'RESCHEDULED'
  | 'READY_FOR_COLLECTION'
  | 'COLLECTED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'MISSED';

export type OrganizationType =
  | 'FOOD_BANK'
  | 'SOUP_KITCHEN'
  | 'HOMELESS_SHELTER'
  | 'COMMUNITY_PANTRY'
  | 'CHARITY_RECIPIENT';

export interface SurplusListing {
  id: string;
  tenant_id: string;
  item_id: string;
  title?: string;
  product_name: string;
  category_name: string;
  category_id: string;
  sku?: string;
  quantity: number;
  remaining_claimable_quantity: number;
  unit: string;
  expiry_date: string;
  days_to_expiry: number;
  storage_requirement: string;
  status: SurplusStatus;
  pickup_address: string;
  pickup_instructions?: string;
  description?: string;
  available_from: string;
  available_until: string;
  claimed_by_tenant_id?: string;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
  claims_count: number;
}

export interface SurplusListingCreatePayload {
  item_id: string;
  title?: string;
  quantity: number;
  unit?: string;
  expiry_date?: string;
  storage_requirement?: string;
  pickup_address: string;
  pickup_instructions?: string;
  description?: string;
  available_from?: string;
  available_until: string;
  status?: string;
}

export interface SurplusClaim {
  id: string;
  listing_id: string;
  listing_title: string;
  ngo_tenant_id: string;
  ngo_name: string;
  claimed_by_user_id: string;
  claimed_by_user_name: string;
  claimed_quantity: number;
  unit: string;
  status: ClaimStatus;
  pickup_time?: string;
  notes?: string;
  rejection_reason?: string;
  reviewed_by_user_id?: string;
  pickup_schedule?: PickupSchedule;
  created_at: string;
  updated_at: string;
}

export interface PickupSchedule {
  id: string;
  claim_id: string;
  listing_id: string;
  listing_title: string;
  donor_tenant_id: string;
  donor_name: string;
  ngo_tenant_id: string;
  ngo_name: string;
  pickup_date: string;
  pickup_start_time: string;
  pickup_end_time: string;
  pickup_location: string;
  pickup_instructions?: string;
  vehicle_type?: string;
  driver_name?: string;
  driver_phone?: string;
  status: PickupScheduleStatus;
  scheduled_by_user_id: string;
  scheduled_by_user_name: string;
  rescheduled_count: number;
  rescheduled_reason?: string;
  cancellation_reason?: string;
  ready_at?: string;
  collected_at?: string;
  completed_at?: string;
  missed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface PickupScheduleCreatePayload {
  pickup_date: string;
  pickup_start_time: string;
  pickup_end_time: string;
  pickup_location?: string;
  pickup_instructions?: string;
  vehicle_type?: string;
  driver_name?: string;
  driver_phone?: string;
}

export interface PickupScheduleReschedulePayload {
  pickup_date: string;
  pickup_start_time: string;
  pickup_end_time: string;
  rescheduled_reason: string;
  pickup_location?: string;
  pickup_instructions?: string;
  vehicle_type?: string;
  driver_name?: string;
  driver_phone?: string;
}

export interface SurplusClaimCreatePayload {
  listing_id: string;
  claimed_quantity: number;
  pickup_time?: string;
  notes?: string;
}

export interface NgoMatchRecommendation {
  ngo_tenant_id: string;
  ngo_name: string;
  organization_type: string;
  is_verified: boolean;
  match_score: number;
  distance_km?: number | null;
  max_capacity_units: number;
  storage_facilities: string[];
  match_reasons: string[];
}

export interface SurplusMatchesResponse {
  listing_id: string;
  product_name: string;
  quantity: number;
  unit: string;
  storage_requirement: string;
  days_to_expiry: number;
  total_candidates_evaluated: number;
  matching_recommendations: NgoMatchRecommendation[];
}

export interface NgoProfile {
  id: string;
  tenant_id: string;
  organization_name: string;
  organization_type: string;
  is_verified: boolean;
  verification_date?: string;
  contact_person: string;
  contact_phone: string;
  contact_email: string;
  address: string;
  latitude?: number | null;
  longitude?: number | null;
  service_radius_km: number;
  accepted_categories: string[];
  storage_facilities: string[];
  max_capacity_units: number;
  operating_hours?: string;
  created_at: string;
  updated_at: string;
}

export interface SurplusNotification {
  id: string;
  tenant_id: string;
  user_id?: string;
  title: string;
  message: string;
  notification_type: string;
  reference_id?: string;
  is_read: boolean;
  created_at: string;
}

// -----------------------------------------------------------------------------
// Milestone 3 Phase 3: Analytics & Dashboards Types
// -----------------------------------------------------------------------------

export interface CategoryImpact {
  category_id: string;
  category_name: string;
  rescued_kg: number;
  rescued_units: number;
  value_rescued: number;
  co2e_avoided_kg: number;
  meals_provided: number;
}

export interface EnvironmentalEquivalencies {
  co2e_avoided_kg: number;
  trees_planted_equivalent: number;
  passenger_car_miles_avoided: number;
}

export interface SustainabilityMetrics {
  total_rescued_weight_kg: number;
  total_rescued_units_count: number;
  total_value_rescued: number;
  co2e_avoided_kg: number;
  total_meals_provided: number;
  completed_claims_count: number;
  participating_businesses_count: number;
  participating_ngos_count: number;
  equivalencies: EnvironmentalEquivalencies;
  category_breakdown: CategoryImpact[];
  methodology_notes: string;
}

export interface BusinessDashboardSummary {
  tenant_id: string;
  tenant_name: string;
  total_inventory_items: number;
  total_stock_value: number;
  items_expiring_soon_count: number;
  at_risk_value: number;
  high_risk_items_count: number;
  active_surplus_listings_count: number;
  pending_claims_count: number;
  upcoming_pickups_count: number;
  completed_transfers_count: number;
  cancelled_or_expired_listings_count: number;
  total_value_rescued: number;
  total_food_rescued_kg: number;
  co2e_avoided_kg: number;
  meals_provided: number;
  recent_activity: Array<{
    type: string;
    id: string;
    listing_id: string;
    listing_title: string;
    claimed_quantity: number;
    unit: string;
    status: string;
    created_at?: string;
  }>;
}

export interface NgoDashboardSummary {
  tenant_id: string;
  organization_name: string;
  organization_type: string;
  is_verified: boolean;
  service_radius_km: number;
  accepted_categories: string[];
  storage_facilities: string[];
  eligible_surplus_listings_count: number;
  pending_claims_count: number;
  accepted_claims_count: number;
  upcoming_pickups_count: number;
  completed_collections_count: number;
  total_food_rescued_kg: number;
  total_food_rescued_units: number;
  meals_provided: number;
  value_received: number;
  recent_claims: Array<{
    claim_id: string;
    listing_id: string;
    listing_title: string;
    quantity: number;
    unit: string;
    status: string;
    donor_tenant_id?: string;
    pickup_time?: string;
    created_at?: string;
  }>;
}

export interface TimeSeriesPoint {
  date: string;
  rescued_kg: number;
  claims_count: number;
  co2e_avoided_kg: number;
  meals_provided: number;
  value_rescued: number;
}

export interface TimeSeriesResponse {
  interval: string;
  start_date?: string;
  end_date?: string;
  total_points: number;
  points: TimeSeriesPoint[];
}

