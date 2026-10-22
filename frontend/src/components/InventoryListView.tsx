import React, { useEffect, useState } from 'react';
import {
  Boxes,
  Clock,
  Filter,
  History,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react';
import { api } from '../services/api';
import { CategorySummary, InventoryItem, PaginationMeta } from '../types';

interface InventoryListViewProps {
  onSelectItem: (item: InventoryItem) => void;
  onOpenCreateItem: () => void;
  onEditItem: (item: InventoryItem) => void;
  onQuickAdjust: (item: InventoryItem) => void;
}

export const InventoryListView: React.FC<InventoryListViewProps> = ({
  onSelectItem,
  onOpenCreateItem,
  onEditItem,
  onQuickAdjust,
}) => {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [categories, setCategories] = useState<CategorySummary[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta>({
    page: 1,
    size: 15,
    total: 0,
    total_pages: 0,
    has_next: false,
    has_prev: false,
  });

  const [search, setSearch] = useState<string>('');
  const [categoryId, setCategoryId] = useState<string>('');
  const [storageReq, setStorageReq] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('expiry_date');
  const [sortOrder, setSortOrder] = useState<string>('asc');

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Load Categories for filter
  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => {});
  }, []);

  // Fetch Inventory on search/filter changes
  const fetchInventory = async (page = 1) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listInventory({
        page,
        size: pagination.size,
        search: search.trim() || undefined,
        category_id: categoryId || undefined,
        storage_requirement: storageReq || undefined,
        status: statusFilter || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setItems(res.data);
      setPagination(res.pagination);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch inventory');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInventory(1);
  }, [categoryId, storageReq, statusFilter, sortBy, sortOrder]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchInventory(1);
  };

  const handleDeleteItem = async (item: InventoryItem) => {
    if (!window.confirm(`Are you sure you want to deactivate item "${item.name}"?`)) return;
    try {
      await api.deleteInventoryItem(item.id);
      fetchInventory(pagination.page);
    } catch (err: any) {
      alert(`Deactivation failed: ${err.message}`);
    }
  };

  const getStatusBadge = (status: string, daysToExpiry: number) => {
    if (status === 'EXPIRED' || daysToExpiry <= 0) {
      return <span className="badge badge-expired">Expired</span>;
    } else if (daysToExpiry <= 1) {
      return <span className="badge badge-critical">Critical (≤24h)</span>;
    } else if (daysToExpiry <= 3) {
      return <span className="badge badge-warning">Warning (≤3d)</span>;
    } else if (daysToExpiry <= 7) {
      return <span className="badge badge-notice">Notice (≤7d)</span>;
    }
    return <span className="badge badge-fresh">Fresh</span>;
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>Inventory Management</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            Search, filter, track expiry horizons, and review double-entry audit ledgers.
          </p>
        </div>
        <button className="btn btn-primary" onClick={onOpenCreateItem}>
          <Plus size={16} /> Add New Item
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={16} color="var(--gray-500)" style={{ position: 'absolute', left: '12px', top: '12px' }} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, SKU, or barcode (e.g. Organic Milk, DAI-001)..."
              className="form-input"
              style={{ paddingLeft: '36px' }}
            />
          </div>
          <button type="submit" className="btn btn-secondary">
            Search
          </button>
          {search && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setSearch('');
                setTimeout(() => fetchInventory(1), 0);
              }}
            >
              Clear
            </button>
          )}
        </form>

        {/* Dropdown Filters */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px' }}>
          <div>
            <label className="form-label">Category</label>
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="form-select">
              <option value="">All Food Categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.perishability_tier})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="form-label">Storage Requirement</label>
            <select value={storageReq} onChange={(e) => setStorageReq(e.target.value)} className="form-select">
              <option value="">All Storage Types</option>
              <option value="REFRIGERATED">Refrigerated (0-4°C)</option>
              <option value="FROZEN">Frozen (≤ -18°C)</option>
              <option value="AMBIENT">Ambient (18-22°C)</option>
              <option value="DRY_PANTRY">Dry Pantry</option>
              <option value="CLIMATE_CONTROLLED">Climate Controlled</option>
            </select>
          </div>

          <div>
            <label className="form-label">Status Horizon</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="form-select">
              <option value="">All Item States</option>
              <option value="ACTIVE">Active (In Stock)</option>
              <option value="EXPIRING_SOON">Expiring Soon</option>
              <option value="EXPIRED">Expired</option>
            </select>
          </div>

          <div>
            <label className="form-label">Sort Order</label>
            <div style={{ display: 'flex', gap: '4px' }}>
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="form-select" style={{ flex: 1 }}>
                <option value="expiry_date">Expiry Date</option>
                <option value="current_quantity">Current Stock</option>
                <option value="name">Item Name</option>
                <option value="cost_per_unit">Unit Cost</option>
              </select>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ padding: '0 8px' }}
                onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              >
                {sortOrder.toUpperCase()}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div style={{ padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '16px' }}>
          {error}
        </div>
      )}

      {/* Inventory Table */}
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Item & Category</th>
              <th>SKU / Barcode</th>
              <th>Current Stock</th>
              <th>Expiry & Horizon</th>
              <th>Storage Location</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: 'var(--gray-500)' }}>
                  Loading inventory from database...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '40px' }}>
                  <Boxes size={32} color="var(--gray-300)" style={{ margin: '0 auto 8px' }} />
                  <p style={{ fontWeight: 600, color: 'var(--gray-700)' }}>No inventory items found</p>
                  <p style={{ fontSize: '0.8125rem', color: 'var(--gray-500)', marginBottom: '12px' }}>
                    Try clearing search filters or add a new inventory lot.
                  </p>
                  <button className="btn btn-primary" onClick={onOpenCreateItem}>
                    Add First Item
                  </button>
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--gray-900)' }}>{item.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                      {item.category?.name || 'Uncategorized'}
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '0.8125rem', fontFamily: 'monospace' }}>{item.sku || '—'}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{item.barcode || '—'}</div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--primary)' }}>
                      {item.current_quantity} <span style={{ fontSize: '0.75rem', fontWeight: 500 }}>{item.unit}</span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                      ${Number(item.cost_per_unit).toFixed(2)} / unit
                    </div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: '0.8125rem' }}>{item.expiry_date}</div>
                    <div style={{ marginTop: '2px' }}>
                      {getStatusBadge(item.status, item.days_to_expiry)}
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '0.8125rem' }}>{item.storage_location || 'General Storage'}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{item.storage_requirement}</div>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>{item.status}</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '6px' }}>
                      <button
                        title="View Details & Ledger History"
                        className="btn btn-secondary"
                        style={{ padding: '6px 10px', fontSize: '0.75rem' }}
                        onClick={() => onSelectItem(item)}
                      >
                        <History size={14} /> Details
                      </button>
                      <button
                        title="Quick Stock Adjustment"
                        className="btn btn-secondary"
                        style={{ padding: '6px 10px', fontSize: '0.75rem' }}
                        onClick={() => onQuickAdjust(item)}
                      >
                        Adjust
                      </button>
                      <button
                        title="Edit Item"
                        className="btn btn-secondary"
                        style={{ padding: '6px 8px' }}
                        onClick={() => onEditItem(item)}
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        title="Deactivate Item"
                        className="btn btn-secondary"
                        style={{ padding: '6px 8px', color: 'var(--danger)' }}
                        onClick={() => handleDeleteItem(item)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {pagination.total_pages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
          <div style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
            Showing page {pagination.page} of {pagination.total_pages} ({pagination.total} total items)
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn btn-secondary"
              disabled={!pagination.has_prev}
              onClick={() => fetchInventory(pagination.page - 1)}
            >
              Previous
            </button>
            <button
              className="btn btn-secondary"
              disabled={!pagination.has_next}
              onClick={() => fetchInventory(pagination.page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
