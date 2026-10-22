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
