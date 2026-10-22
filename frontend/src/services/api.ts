/**
 * Unified Backend API Service.
 * Connects directly to FastAPI v1 endpoints with complete error handling.
 */

import {
  CategorySummary,
  CsvImportResponse,
  ExpiryAlertHistory,
  ExpiryEvaluationResponse,
  InventoryItem,
  InventoryItemCreatePayload,
  PaginatedResponse,
  PosIntegration,
  PosSyncResponse,
  StockAdjustmentPayload,
  StockTransaction,
  SuccessEnvelope,
  TenantAlertConfig,
} from '../types';

const API_BASE = '/api/v1';

// Token Management
export const getStoredToken = (): string => {
  return localStorage.getItem('auth_token') || '';
};

export const setStoredToken = (token: string): void => {
  localStorage.setItem('auth_token', token);
};

export const getAuthHeaders = (): Record<string, string> => {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  // Optional test user ID if testing without JWT
  const testUserId = localStorage.getItem('test_user_id');
  const testTenantId = localStorage.getItem('test_tenant_id');
  if (testUserId) headers['X-Test-User-Id'] = testUserId;
  if (testTenantId) headers['X-Test-Tenant-Id'] = testTenantId;

  return headers;
};

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}`;
    try {
      const errJson = await res.json();
      errorMsg = errJson.detail || errJson.error?.message || errJson.message || errorMsg;
    } catch {
      // Body not JSON
    }
    throw new Error(errorMsg);
  }
  return res.json();
}

export const api = {
  // 1. Categories
  async getCategories(tier?: string, storage?: string): Promise<CategorySummary[]> {
    const params = new URLSearchParams();
    if (tier) params.append('perishability_tier', tier);
    if (storage) params.append('recommended_storage', storage);
    const res = await fetch(`${API_BASE}/categories?${params.toString()}`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<CategorySummary[]> = await handleResponse(res);
    return json.data;
  },

  // 2. Inventory CRUD & Search
  async listInventory(params: {
    page?: number;
    size?: number;
    search?: string;
    category_id?: string;
    storage_requirement?: string;
    status?: string;
    sort_by?: string;
    sort_order?: string;
  }): Promise<PaginatedResponse<InventoryItem>> {
    const query = new URLSearchParams();
    if (params.page) query.append('page', String(params.page));
    if (params.size) query.append('size', String(params.size));
    if (params.search) query.append('search', params.search);
    if (params.category_id) query.append('category_id', params.category_id);
    if (params.storage_requirement) query.append('storage_requirement', params.storage_requirement);
    if (params.status) query.append('status', params.status);
    if (params.sort_by) query.append('sort_by', params.sort_by);
    if (params.sort_order) query.append('sort_order', params.sort_order);

    const res = await fetch(`${API_BASE}/inventory?${query.toString()}`, {
      headers: getAuthHeaders(),
    });
    return handleResponse<PaginatedResponse<InventoryItem>>(res);
  },

  async createInventoryItem(payload: InventoryItemCreatePayload): Promise<InventoryItem> {
    const res = await fetch(`${API_BASE}/inventory`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    const json: SuccessEnvelope<InventoryItem> = await handleResponse(res);
    return json.data;
  },

  async getInventoryItem(id: string): Promise<InventoryItem> {
    const res = await fetch(`${API_BASE}/inventory/${id}`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<InventoryItem> = await handleResponse(res);
    return json.data;
  },

  async updateInventoryItem(id: string, payload: Partial<InventoryItemCreatePayload>): Promise<InventoryItem> {
    const res = await fetch(`${API_BASE}/inventory/${id}`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    const json: SuccessEnvelope<InventoryItem> = await handleResponse(res);
    return json.data;
  },

  async deleteInventoryItem(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/inventory/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    await handleResponse(res);
  },

  // 3. Stock Adjustment & Transactions
  async adjustStock(
    itemId: string,
    payload: StockAdjustmentPayload
  ): Promise<{ item: InventoryItem; transaction: StockTransaction }> {
    const res = await fetch(`${API_BASE}/inventory/${itemId}/adjust`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    const json: SuccessEnvelope<{ item: InventoryItem; transaction: StockTransaction }> = await handleResponse(res);
    return json.data;
  },

  async getItemTransactions(itemId: string): Promise<StockTransaction[]> {
    const res = await fetch(`${API_BASE}/inventory/${itemId}/transactions`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<StockTransaction[]> = await handleResponse(res);
    return json.data;
  },

  // 4. Barcode / QR Lookup
  async lookupBarcode(code: string): Promise<any> {
    const res = await fetch(`${API_BASE}/inventory/lookup?code=${encodeURIComponent(code)}`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<any> = await handleResponse(res);
    return json.data;
  },

  // 5. Expiry Engine & Alerts
  async getExpiringInventory(statusFilter?: string, daysThreshold?: number): Promise<ExpiryEvaluationResponse> {
    const query = new URLSearchParams();
    if (statusFilter) query.append('status', statusFilter);
    if (daysThreshold !== undefined) query.append('days_threshold', String(daysThreshold));

    const res = await fetch(`${API_BASE}/inventory/expiring?${query.toString()}`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<ExpiryEvaluationResponse> = await handleResponse(res);
    return json.data;
  },

  async evaluateExpiry(dryRun = false): Promise<ExpiryEvaluationResponse> {
    const res = await fetch(`${API_BASE}/inventory/expiry/evaluate?dry_run=${dryRun}`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<ExpiryEvaluationResponse> = await handleResponse(res);
    return json.data;
  },

  async getAlertConfig(): Promise<TenantAlertConfig> {
    const res = await fetch(`${API_BASE}/alerts/config`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<TenantAlertConfig> = await handleResponse(res);
    return json.data;
  },

  async updateAlertConfig(payload: Partial<TenantAlertConfig>): Promise<TenantAlertConfig> {
    const res = await fetch(`${API_BASE}/alerts/config`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    const json: SuccessEnvelope<TenantAlertConfig> = await handleResponse(res);
    return json.data;
  },

  async getAlertHistory(alertLevel?: string, acknowledged?: boolean): Promise<ExpiryAlertHistory[]> {
    const query = new URLSearchParams();
    if (alertLevel) query.append('alert_level', alertLevel);
    if (acknowledged !== undefined) query.append('acknowledged', String(acknowledged));

    const res = await fetch(`${API_BASE}/alerts/history?${query.toString()}`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<ExpiryAlertHistory[]> = await handleResponse(res);
    return json.data;
  },

  async acknowledgeAlert(alertId: string, actionTaken?: string): Promise<ExpiryAlertHistory> {
    const res = await fetch(`${API_BASE}/alerts/${alertId}/acknowledge`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ action_taken: actionTaken }),
    });
    const json: SuccessEnvelope<ExpiryAlertHistory> = await handleResponse(res);
    return json.data;
  },

  // 6. CSV Bulk Ingestion
  async uploadCsv(file: File, dryRun = true, allowPartial = false): Promise<CsvImportResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const token = getStoredToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(
      `${API_BASE}/inventory/bulk-import/csv?dry_run=${dryRun}&allow_partial=${allowPartial}`,
      {
        method: 'POST',
        headers,
        body: formData,
      }
    );
    const json: SuccessEnvelope<CsvImportResponse> = await handleResponse(res);
    return json.data;
  },

  // 7. POS Integrations
  async getPosIntegrations(): Promise<PosIntegration[]> {
    const res = await fetch(`${API_BASE}/pos/integrations`, {
      headers: getAuthHeaders(),
    });
    const json: SuccessEnvelope<PosIntegration[]> = await handleResponse(res);
    return json.data;
  },

  async createPosIntegration(payload: {
    provider: string;
    integration_name: string;
    api_key?: string;
  }): Promise<PosIntegration> {
    const res = await fetch(`${API_BASE}/pos/integrations`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    const json: SuccessEnvelope<PosIntegration> = await handleResponse(res);
    return json.data;
  },

  async syncPosIntegration(id: string, since?: string, cursor?: string): Promise<PosSyncResponse> {
    const res = await fetch(`${API_BASE}/pos/integrations/${id}/sync`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ since, cursor }),
    });
    const json: SuccessEnvelope<PosSyncResponse> = await handleResponse(res);
    return json.data;
  },
};
