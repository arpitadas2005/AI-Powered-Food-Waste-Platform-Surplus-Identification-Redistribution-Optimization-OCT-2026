import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  Clock,
  DollarSign,
  Plus,
  QrCode,
  RefreshCw,
  Upload,
} from 'lucide-react';
import { api } from '../services/api';
import { ExpiryEvaluationResponse, InventoryItem, StockTransaction } from '../types';

interface DashboardViewProps {
  onNavigate: (tab: any) => void;
  onOpenCreateItem: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate, onOpenCreateItem }) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [items, setItems] = useState<InventoryItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [expiryData, setExpiryData] = useState<ExpiryEvaluationResponse | null>(null);
  const [recentTransactions, setRecentTransactions] = useState<StockTransaction[]>([]);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch inventory items
      const invRes = await api.listInventory({ size: 100 });
      setItems(invRes.data);
      setTotalCount(invRes.pagination.total);

      // 2. Fetch expiring evaluation
      const expRes = await api.getExpiringInventory('ALL_AT_RISK');
      setExpiryData(expRes);

      // 3. Collect recent transactions from items
      const txPromises = invRes.data.slice(0, 5).map((item) =>
        api.getItemTransactions(item.id).catch(() => [])
      );
      const allTxLists = await Promise.all(txPromises);
      const flattened = allTxLists.flat().sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
      setRecentTransactions(flattened.slice(0, 6));
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Compute live aggregates from persisted items
  const totalValue = items.reduce(
    (acc, curr) => acc + Number(curr.current_quantity) * Number(curr.cost_per_unit),
    0
  );

  const atRiskValue = expiryData ? expiryData.summary.total_at_risk_value : 0;
  const criticalCount = expiryData ? expiryData.summary.critical_count : 0;
  const expiredCount = expiryData ? expiryData.summary.expired_count : 0;
  const warningCount = expiryData ? expiryData.summary.warning_count : 0;

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '300px', gap: '8px' }}>
        <RefreshCw className="animate-spin" size={24} color="var(--primary)" />
        <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>Querying persisted database metrics...</span>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>Inventory & Waste Dashboard</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            Real-time surplus monitoring and double-entry stock integrity metrics.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={loadDashboardData}>
            <RefreshCw size={16} /> Refresh
          </button>
          <button className="btn btn-primary" onClick={onOpenCreateItem}>
            <Plus size={16} /> Add Inventory Item
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div style={{ padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '16px' }}>
          <strong>Error loading dashboard:</strong> {error}
        </div>
      )}

      {/* Critical Alert Banner if expired or critical items exist */}
      {(criticalCount > 0 || expiredCount > 0) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px',
            background: 'var(--danger-bg)',
            border: '1px solid #fecaca',
            borderRadius: '12px',
            marginBottom: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <AlertCircle size={28} color="var(--danger)" />
            <div>
              <h4 style={{ fontWeight: 700, color: '#991b1b', fontSize: '0.9375rem' }}>
                Action Required: {criticalCount} Critical & {expiredCount} Expired Lots Detected
              </h4>
              <p style={{ fontSize: '0.8125rem', color: '#b91c1c' }}>
                Total at-risk food value is ${Number(atRiskValue).toFixed(2)}. Flag items for discount, donation hold, or compost.
              </p>
            </div>
          </div>
          <button className="btn btn-danger" onClick={() => onNavigate('expiry')}>
            Review At-Risk Stock
          </button>
        </div>
      )}

      {/* Metric Cards Grid */}
      <div className="grid-cols-4">
        {/* Total Stock */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
            <span>TOTAL ITEMS IN STOCK</span>
            <Boxes size={18} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--gray-900)' }}>
            {totalCount} <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-500)' }}>SKUs</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--success)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={12} /> Active & Tracked in Ledger
          </div>
        </div>

        {/* Valuation */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
            <span>TOTAL INVENTORY VALUE</span>
            <DollarSign size={18} color="var(--success)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--gray-900)' }}>
            ${totalValue.toFixed(2)}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
            Across all active categories
          </div>
        </div>

        {/* Expiring Soon */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
            <span>EXPIRING SOON</span>
            <Clock size={18} color="var(--warning)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--warning)' }}>
            {criticalCount + warningCount} <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>lots</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--warning)', marginTop: '4px' }}>
            {criticalCount} critical (≤24h), {warningCount} warning
          </div>
        </div>

        {/* Expired Stock */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
            <span>EXPIRED FOOD (WRITE-OFF)</span>
            <AlertTriangle size={18} color="var(--danger)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--danger)' }}>
            {expiredCount} <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>lots</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
            Ineligible for food donation
          </div>
        </div>
      </div>

      {/* Quick Action Bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '24px' }}>
        <button
          onClick={() => onNavigate('scanner')}
          className="card"
          style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', textAlign: 'left', border: '1px solid var(--border)' }}
        >
          <div style={{ background: 'var(--primary-light)', padding: '10px', borderRadius: '8px' }}>
            <QrCode size={20} color="var(--primary)" />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>Barcode / QR Scan</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Mobile camera & manual SKU</div>
          </div>
        </button>

        <button
          onClick={() => onNavigate('csv')}
          className="card"
          style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', textAlign: 'left', border: '1px solid var(--border)' }}
        >
          <div style={{ background: '#fef3c7', padding: '10px', borderRadius: '8px' }}>
            <Upload size={20} color="#b45309" />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>CSV Bulk Ingestion</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Preview & partial commit</div>
          </div>
        </button>

        <button
          onClick={() => onNavigate('expiry')}
          className="card"
          style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', textAlign: 'left', border: '1px solid var(--border)' }}
        >
          <div style={{ background: '#fee2e2', padding: '10px', borderRadius: '8px' }}>
            <Clock size={20} color="#b91c1c" />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>Expiry Engine</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Evaluate waste horizons</div>
          </div>
        </button>
      </div>

      {/* Recent Activity Ledger */}
      <div className="card">
        <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '12px' }}>
          Recent Stock Ledger Transactions
        </h3>
        {recentTransactions.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.875rem' }}>
            No stock adjustments recorded yet. Items will log double-entry transactions here.
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Transaction Type</th>
                  <th>Quantity Delta</th>
                  <th>Before $\rightarrow$ After</th>
                  <th>Reason & Reference</th>
                </tr>
              </thead>
              <tbody>
                {recentTransactions.map((tx) => (
                  <tr key={tx.id}>
                    <td style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                      {new Date(tx.created_at).toLocaleString()}
                    </td>
                    <td>
                      <span className="badge badge-notice">{tx.transaction_type}</span>
                    </td>
                    <td style={{ fontWeight: 700, color: tx.quantity_change >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                      {tx.quantity_change > 0 ? `+${tx.quantity_change}` : tx.quantity_change}
                    </td>
                    <td style={{ fontSize: '0.8125rem' }}>
                      {tx.quantity_before} $\rightarrow$ <strong>{tx.quantity_after}</strong>
                    </td>
                    <td style={{ fontSize: '0.8125rem', color: 'var(--gray-700)' }}>
                      {tx.reason || tx.reference_type || 'System adjustment'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
