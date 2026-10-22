import React from 'react';
import {
  LayoutDashboard,
  Boxes,
  QrCode,
  AlertTriangle,
  UploadCloud,
  Layers,
  Building2,
  RefreshCw,
} from 'lucide-react';

export type ActiveTab = 'dashboard' | 'inventory' | 'scanner' | 'expiry' | 'csv' | 'pos';

interface NavigationProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  tenantSlug: string;
  setTenantSlug: (slug: string) => void;
  onRefreshData?: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  setActiveTab,
  tenantSlug,
  setTenantSlug,
  onRefreshData,
}) => {
  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div style={{ padding: '20px 16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '1.5rem' }}>🌱</span>
          <div>
            <h1 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--gray-900)' }}>
              Food Waste Rescue
            </h1>
            <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
              Surplus & Inventory Engine
            </p>
          </div>
        </div>

        {/* Tenant Context Selector */}
        <div style={{ marginTop: '16px' }}>
          <label style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
            Current Tenant Context
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
            <Building2 size={16} color="var(--gray-500)" />
            <select
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value)}
              className="form-select"
              style={{ fontSize: '0.8125rem', padding: '6px 8px' }}
            >
              <option value="green-grocer-downtown">Green Grocer (Tenant A)</option>
              <option value="artisan-bakery-uptown">Artisan Bakery (Tenant B)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Nav Items */}
      <nav style={{ padding: '16px 0', flex: 1 }}>
        <div
          className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          <LayoutDashboard size={18} />
          <span>Dashboard</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'inventory' ? 'active' : ''}`}
          onClick={() => setActiveTab('inventory')}
        >
          <Boxes size={18} />
          <span>Inventory Stock</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'scanner' ? 'active' : ''}`}
          onClick={() => setActiveTab('scanner')}
        >
          <QrCode size={18} />
          <span>Barcode & QR Scan</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'expiry' ? 'active' : ''}`}
          onClick={() => setActiveTab('expiry')}
        >
          <AlertTriangle size={18} />
          <span>Expiry & Alerts</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'csv' ? 'active' : ''}`}
          onClick={() => setActiveTab('csv')}
        >
          <UploadCloud size={18} />
          <span>CSV Bulk Import</span>
        </div>

        <div
          className={`nav-item ${activeTab === 'pos' ? 'active' : ''}`}
          onClick={() => setActiveTab('pos')}
        >
          <Layers size={18} />
          <span>POS Integrations</span>
        </div>
      </nav>

      {/* Footer Info */}
      <div style={{ padding: '16px', borderTop: '1px solid var(--border)', fontSize: '0.75rem', color: 'var(--gray-500)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span>Milestone 1 Verified</span>
          {onRefreshData && (
            <button
              onClick={onRefreshData}
              title="Refresh All Database Data"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--primary)' }}
            >
              <RefreshCw size={14} />
            </button>
          )}
        </div>
        <div>Strict Tenant Isolation • SQLite/Postgres</div>
      </div>
    </aside>
  );
};
